"""Minimal GitHub REST helpers for ingestion and PR creation."""

from __future__ import annotations

import base64
import re
import uuid
from typing import Any

import httpx

GITHUB_API = "https://api.github.com"

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".toml",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".cs",
    ".rb",
    ".php",
    ".html",
    ".css",
    ".scss",
    ".sh",
    ".sql",
}


def parse_repo_input(raw: str) -> tuple[str, str]:
    s = raw.strip().rstrip("/")
    if "github.com" in s:
        m = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", s)
        if not m:
            raise ValueError("Could not parse owner/repo from URL")
        return m.group("owner"), m.group("repo").removesuffix(".git")
    if "/" in s and s.count("/") == 1:
        owner, repo = s.split("/", 1)
        return owner.strip(), repo.strip().removesuffix(".git")
    raise ValueError("Use owner/repo or a github.com URL")


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_repo_meta(client: httpx.Client, token: str, owner: str, repo: str) -> dict[str, Any]:
    r = client.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=_headers(token), timeout=60.0)
    r.raise_for_status()
    return r.json()


def get_default_branch_sha(client: httpx.Client, token: str, owner: str, repo: str, branch: str) -> str:
    r = client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{branch}",
        headers=_headers(token),
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()["object"]["sha"]


def list_root_paths(client: httpx.Client, token: str, owner: str, repo: str, branch: str) -> list[str]:
    r = client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/",
        headers=_headers(token),
        params={"ref": branch},
        timeout=60.0,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return []
    paths: list[str] = []
    for item in data:
        if item.get("type") == "file":
            paths.append(item["path"])
        elif item.get("type") == "dir" and item["name"] in {
            "src",
            "lib",
            "app",
            "api",
            "backend",
            "frontend",
            "packages",
            "internal",
            "pkg",
            "cmd",
            "services",
        }:
            sub = _list_dir_recursive(client, token, owner, repo, item["path"], branch, depth=0, max_depth=2)
            paths.extend(sub)
    return paths


def _list_dir_recursive(
    client: httpx.Client,
    token: str,
    owner: str,
    repo: str,
    path: str,
    branch: str,
    depth: int,
    max_depth: int,
) -> list[str]:
    if depth > max_depth:
        return []
    r = client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        headers=_headers(token),
        params={"ref": branch},
        timeout=60.0,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if item.get("type") == "file":
            out.append(item["path"])
        elif item.get("type") == "dir" and depth < max_depth:
            out.extend(
                _list_dir_recursive(client, token, owner, repo, item["path"], branch, depth + 1, max_depth)
            )
    return out


def fetch_file_text(
    client: httpx.Client, token: str, owner: str, repo: str, path: str, branch: str
) -> tuple[str, str | None]:
    """Returns (decoded_text, blob_sha for updates)."""
    r = client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        headers=_headers(token),
        params={"ref": branch},
        timeout=60.0,
    )
    if r.status_code == 404:
        return "", None
    r.raise_for_status()
    payload = r.json()
    if payload.get("encoding") != "base64" or "content" not in payload:
        return "", payload.get("sha")
    raw = base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
    return raw, payload.get("sha")


def select_text_files(paths: list[str], max_files: int = 12) -> list[str]:
    scored: list[tuple[int, str]] = []
    for p in paths:
        low = p.lower()
        ext = "." + low.rsplit(".", 1)[-1] if "." in low else ""
        if ext not in TEXT_EXTENSIONS:
            continue
        priority = 0
        if "readme" in low:
            priority += 5
        if ext in {".py", ".ts", ".tsx", ".js", ".jsx"}:
            priority += 3
        if "package.json" in low or "requirements" in low:
            priority += 2
        scored.append((priority, p))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [p for _, p in scored[:max_files]]


def create_branch(client: httpx.Client, token: str, owner: str, repo: str, name: str, from_sha: str) -> None:
    r = client.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/refs",
        headers=_headers(token),
        json={"ref": f"refs/heads/{name}", "sha": from_sha},
        timeout=60.0,
    )
    if r.status_code == 422 and "already exists" in r.text:
        return
    r.raise_for_status()


def commit_file_update(
    client: httpx.Client,
    token: str,
    owner: str,
    repo: str,
    path: str,
    branch: str,
    message: str,
    new_content: str,
    file_sha: str | None,
) -> None:
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(new_content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if file_sha:
        body["sha"] = file_sha
    r = client.put(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        headers=_headers(token),
        json=body,
        timeout=120.0,
    )
    r.raise_for_status()


def open_pull_request(
    client: httpx.Client,
    token: str,
    owner: str,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str,
) -> str:
    r = client.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        headers=_headers(token),
        json={"title": title, "body": body, "head": head, "base": base},
        timeout=60.0,
    )
    r.raise_for_status()
    return str(r.json().get("html_url", ""))


def unique_branch_name() -> str:
    return f"autohackfix/agent-{uuid.uuid4().hex[:8]}"
