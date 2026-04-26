"""LangGraph pipeline: ingest → detect → fix → validate → (optional) PR."""

from __future__ import annotations

import ast
import json
import operator
from typing import Annotated, Any, Literal, TypedDict

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.github_client import (
    commit_file_update,
    create_branch,
    fetch_file_text,
    get_default_branch_sha,
    get_repo_meta,
    list_root_paths,
    open_pull_request,
    parse_repo_input,
    select_text_files,
    unique_branch_name,
)


class IssueItem(TypedDict):
    file_path: str
    severity: str
    title: str
    description: str


class AgentState(TypedDict):
    repo_input: str
    github_token: str
    create_pr: bool
    owner: str
    repo: str
    default_branch: str
    files_snapshot: dict[str, str]
    file_shas: dict[str, str | None]
    issues: list[IssueItem]
    target_path: str
    fix_title: str
    fix_explanation: str
    new_content: str
    confidence: float
    validation_passed: bool
    validation_notes: str
    pr_url: str | None
    branch_name: str | None
    error: str | None
    stage_log: Annotated[list[str], operator.add]


def _append_log(state: AgentState, msg: str) -> dict[str, Any]:
    return {"stage_log": [msg]}


def _llm_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def _parse_llm_json_dict(content: Any) -> dict[str, Any]:
    """Parse a JSON object from model output; handles markdown fences and short preamble."""
    raw = _llm_message_text(content).strip()
    if not raw:
        raise json.JSONDecodeError("empty model output", "", 0)

    attempts: list[str] = []
    if raw.startswith("```"):
        inner = raw.removeprefix("```json").removeprefix("```").strip()
        if "```" in inner:
            inner = inner.split("```", 1)[0]
        attempts.append(inner.strip())
    attempts.append(raw)

    last_err: json.JSONDecodeError | None = None
    for blob in attempts:
        try:
            val = json.loads(blob)
        except json.JSONDecodeError as e:
            last_err = e
            continue
        if isinstance(val, dict):
            return val

    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        val = json.loads(raw[start : end + 1])
        if isinstance(val, dict):
            return val

    if last_err:
        raise last_err
    raise json.JSONDecodeError("expected a JSON object", raw, 0)


def _llm(settings_model: str, api_key: str) -> ChatOpenAI:
    return ChatOpenAI(model=settings_model, api_key=api_key, temperature=0.2)


def node_ingest(state: AgentState, *, model: str, openai_key: str) -> dict[str, Any]:
    _ = openai_key  # ingest is deterministic; key unused
    try:
        owner, repo = parse_repo_input(state["repo_input"])
    except ValueError as e:
        return {**_append_log(state, f"Ingest failed: {e}"), "error": str(e)}

    log: list[str] = ["Ingest: resolved repository coordinates."]
    try:
        with httpx.Client() as client:
            meta = get_repo_meta(client, state["github_token"], owner, repo)
            branch = str(meta.get("default_branch") or "main")
            paths = list_root_paths(client, state["github_token"], owner, repo, branch)
            chosen = select_text_files(paths, max_files=12)
            if not chosen:
                chosen = select_text_files(paths + [p for p in paths], max_files=5) or paths[:5]

            files: dict[str, str] = {}
            shas: dict[str, str | None] = {}
            for path in chosen:
                text, sha = fetch_file_text(client, state["github_token"], owner, repo, path, branch)
                if text:
                    cap = 12000
                    files[path] = text if len(text) <= cap else text[:cap] + "\n\n/* … truncated … */\n"
                    shas[path] = sha
    except httpx.HTTPStatusError as e:
        err = f"GitHub API error: {e.response.status_code} — {e.response.text[:300]}"
        return {"owner": owner, "repo": repo, "error": err, "stage_log": [err]}
    except Exception as e:  # noqa: BLE001
        return {"owner": owner, "repo": repo, "error": str(e), "stage_log": [f"Ingest error: {e}"]}

    log.append(f"Ingest: loaded {len(files)} text files from `{branch}`.")
    return {
        "owner": owner,
        "repo": repo,
        "default_branch": branch,
        "files_snapshot": files,
        "file_shas": shas,
        "stage_log": log,
        "error": None,
    }


def node_detect(state: AgentState, *, model: str, openai_key: str) -> dict[str, Any]:
    if state.get("error"):
        return {}
    if not state["files_snapshot"]:
        return {**_append_log(state, "Detect: no text files found."), "error": "No suitable files to analyze."}

    llm = _llm(model, openai_key)
    listing = "\n".join(f"- {p}" for p in state["files_snapshot"])
    sys = SystemMessage(
        content=(
            "You are a senior engineer reviewing a small slice of a repository. "
            "Identify high-confidence issues only: bugs, risky patterns, clear code smells, or documentation mismatches. "
            "Return strict JSON with key 'issues': array of objects "
            "{file_path, severity: 'low'|'medium'|'high', title, description}. "
            "file_path MUST be one of the provided paths. "
            "At most 5 issues; prefer 1–3. If nothing is convincing, return an empty issues array."
        )
    )
    human = HumanMessage(
        content=f"Available files:\n{listing}\n\nFile contents (may be truncated):\n"
        + "\n\n---\n\n".join(f"### {p}\n```\n{c}\n```" for p, c in state["files_snapshot"].items())
    )
    raw = llm.invoke([sys, human]).content
    try:
        data = _parse_llm_json_dict(raw)
    except json.JSONDecodeError:
        return {
            **_append_log(state, "Detect: model returned non-JSON; stopping."),
            "error": "Issue detection could not parse model output.",
        }

    issues = data.get("issues") if isinstance(data, dict) else None
    if not isinstance(issues, list):
        issues = []

    cleaned: list[IssueItem] = []
    allowed = set(state["files_snapshot"].keys())
    for item in issues:
        if not isinstance(item, dict):
            continue
        fp = str(item.get("file_path", "")).strip()
        if fp not in allowed:
            continue
        cleaned.append(
            {
                "file_path": fp,
                "severity": str(item.get("severity", "medium")),
                "title": str(item.get("title", "Issue"))[:200],
                "description": str(item.get("description", ""))[:2000],
            }
        )

    msg = f"Detect: found {len(cleaned)} issue(s)."
    if not cleaned:
        msg = "Detect: no high-confidence issues; pipeline will stop before fixing."
    return {"issues": cleaned, "stage_log": [msg], "error": None if cleaned else "No issues to fix."}


def _pick_issue(issues: list[IssueItem]) -> IssueItem | None:
    if not issues:
        return None
    rank = {"high": 3, "medium": 2, "low": 1}

    def score(i: IssueItem) -> int:
        return rank.get(str(i.get("severity", "medium")).lower(), 1)

    return sorted(issues, key=score, reverse=True)[0]


def node_fix(state: AgentState, *, model: str, openai_key: str) -> dict[str, Any]:
    if state.get("error"):
        return {}
    issue = _pick_issue(state["issues"])
    if not issue:
        return {**_append_log(state, "Fix: skipped (no issue)."), "error": state.get("error") or "No issue."}

    path = issue["file_path"]
    original = state["files_snapshot"][path]
    llm = _llm(model, openai_key)
    sys = SystemMessage(
        content=(
            "You fix code professionally. Output strict JSON with keys: "
            "explanation (why the fix works), fixed_content (full new file text), "
            "confidence (0.0-1.0), fix_title (short PR title). "
            "Apply a minimal, safe change addressing ONLY the described issue. "
            "Preserve style and public APIs unless the issue requires otherwise. "
            "fixed_content must be the complete file, not a diff."
        )
    )
    human = HumanMessage(
        content=(
            f"Issue ({issue['severity']}): {issue['title']}\n"
            f"{issue['description']}\n\n"
            f"File `{path}`:\n```\n{original}\n```"
        )
    )
    raw = llm.invoke([sys, human]).content
    try:
        data = _parse_llm_json_dict(raw)
    except json.JSONDecodeError:
        return {
            **_append_log(state, "Fix: invalid JSON from model."),
            "error": "Fix generation could not parse model output.",
        }

    fixed = str(data.get("fixed_content", ""))
    if not fixed.strip():
        return {**_append_log(state, "Fix: empty content."), "error": "Model returned empty fix."}

    return {
        "target_path": path,
        "fix_explanation": str(data.get("explanation", ""))[:8000],
        "fix_title": str(data.get("fix_title", "AutoHackFix: automated fix"))[:200],
        "new_content": fixed,
        "confidence": float(data.get("confidence", 0.7)),
        "stage_log": ["Fix: proposed minimal change for highest-severity issue."],
        "error": None,
    }


def node_validate(state: AgentState, *, model: str, openai_key: str) -> dict[str, Any]:
    _ = model, openai_key
    if state.get("error"):
        return {}
    path = state.get("target_path") or ""
    old = state["files_snapshot"].get(path, "")
    new = state.get("new_content", "")
    notes: list[str] = []

    if new == old:
        return {
            "validation_passed": False,
            "validation_notes": "No effective change after generation.",
            "stage_log": ["Validate: failed — identical content."],
            "error": "Validation failed: no diff.",
        }

    if len(new) > max(len(old) * 3, 500_000):
        return {
            "validation_passed": False,
            "validation_notes": "New file suspiciously large vs original.",
            "stage_log": ["Validate: failed — size sanity check."],
            "error": "Validation failed: size check.",
        }

    low = path.lower()
    if low.endswith(".py"):
        try:
            ast.parse(new)
            notes.append("Python AST parse OK.")
        except SyntaxError as e:
            return {
                "validation_passed": False,
                "validation_notes": f"Python syntax error: {e}",
                "stage_log": ["Validate: failed — Python syntax."],
                "error": "Validation failed: syntax.",
            }

    notes.append("Diff sanity checks passed.")
    return {
        "validation_passed": True,
        "validation_notes": " ".join(notes),
        "stage_log": ["Validate: passed basic checks."],
        "error": None,
    }


def node_pr(state: AgentState, *, model: str, openai_key: str) -> dict[str, Any]:
    _ = model, openai_key
    if state.get("error") or not state.get("validation_passed"):
        return {}
    if not state.get("create_pr"):
        return {"stage_log": ["PR: skipped (dry run / user disabled PR creation)."], "pr_url": None}

    owner, repo = state["owner"], state["repo"]
    path = state["target_path"]
    branch = unique_branch_name()
    base = state["default_branch"]
    try:
        with httpx.Client() as client:
            tip_sha = get_default_branch_sha(client, state["github_token"], owner, repo, base)
            create_branch(client, state["github_token"], owner, repo, branch, tip_sha)
            blob_sha = state["file_shas"].get(path)
            commit_file_update(
                client,
                state["github_token"],
                owner,
                repo,
                path,
                branch,
                f"fix: {state['fix_title']}",
                state["new_content"],
                blob_sha,
            )
            pr_body = (
                "## AutoHackFix\n\n"
                f"**What was wrong:** see issue targeting `{path}`.\n\n"
                f"**What we changed:** {state['fix_explanation']}\n\n"
                f"**Confidence:** {state['confidence']:.2f}\n\n"
                f"**Validation:** {state['validation_notes']}\n\n"
                "_Opened by AutoHackFix agent pipeline._"
            )
            url = open_pull_request(
                client,
                state["github_token"],
                owner,
                repo,
                state["fix_title"],
                pr_body,
                head=branch,
                base=base,
            )
    except httpx.HTTPStatusError as e:
        err = f"GitHub error creating PR: {e.response.status_code} — {e.response.text[:400]}"
        return {"stage_log": [err], "error": err, "pr_url": None, "branch_name": branch}
    except Exception as e:  # noqa: BLE001
        return {"stage_log": [f"PR failed: {e}"], "error": str(e), "pr_url": None}

    return {"pr_url": url, "branch_name": branch, "stage_log": [f"PR: opened {url}"]}


def route_after_ingest(state: AgentState) -> Literal["detect", "end"]:
    return "end" if state.get("error") else "detect"


def route_after_detect(state: AgentState) -> Literal["fix", "end"]:
    if state.get("error"):
        return "end"
    if not state.get("issues"):
        return "end"
    return "fix"


def route_after_fix(state: AgentState) -> Literal["validate", "end"]:
    return "end" if state.get("error") else "validate"


def route_after_validate(state: AgentState) -> Literal["pr", "end"]:
    if state.get("error") or not state.get("validation_passed"):
        return "end"
    return "pr"


def build_graph(model: str, openai_key: str):
    g = StateGraph(AgentState)

    g.add_node("ingest", lambda s: node_ingest(s, model=model, openai_key=openai_key))
    g.add_node("detect", lambda s: node_detect(s, model=model, openai_key=openai_key))
    g.add_node("fix", lambda s: node_fix(s, model=model, openai_key=openai_key))
    g.add_node("validate", lambda s: node_validate(s, model=model, openai_key=openai_key))
    g.add_node("pr", lambda s: node_pr(s, model=model, openai_key=openai_key))

    g.set_entry_point("ingest")
    g.add_conditional_edges("ingest", route_after_ingest, {"detect": "detect", "end": END})
    g.add_conditional_edges("detect", route_after_detect, {"fix": "fix", "end": END})
    g.add_conditional_edges("fix", route_after_fix, {"validate": "validate", "end": END})
    g.add_conditional_edges("validate", route_after_validate, {"pr": "pr", "end": END})
    g.add_edge("pr", END)

    return g.compile()


def run_pipeline(
    repo_input: str,
    github_token: str,
    *,
    create_pr: bool,
    model: str,
    openai_key: str,
) -> AgentState:
    initial: AgentState = {
        "repo_input": repo_input,
        "github_token": github_token,
        "create_pr": create_pr,
        "owner": "",
        "repo": "",
        "default_branch": "main",
        "files_snapshot": {},
        "file_shas": {},
        "issues": [],
        "target_path": "",
        "fix_title": "",
        "fix_explanation": "",
        "new_content": "",
        "confidence": 0.0,
        "validation_passed": False,
        "validation_notes": "",
        "pr_url": None,
        "branch_name": None,
        "error": None,
        "stage_log": [],
    }
    graph = build_graph(model, openai_key)
    return graph.invoke(initial)
