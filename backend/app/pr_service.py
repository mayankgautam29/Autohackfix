"""GitHub pull request creation from a validated fix (no AI re-run)."""

from __future__ import annotations

from typing import Any

import httpx

from app.github_client import (
    commit_file_update,
    create_branch,
    get_default_branch_sha,
    open_pull_request,
    unique_branch_name,
)


def create_pull_request_for_fix(
    token: str,
    *,
    owner: str,
    repo: str,
    default_branch: str,
    target_path: str,
    fix_title: str,
    fix_explanation: str,
    new_content: str,
    confidence: float,
    validation_notes: str,
    file_shas: dict[str, str | None],
) -> dict[str, Any]:
    """Open a branch, commit the fix, and create a PR. Returns pr_url, branch_name, or error."""
    path = target_path
    branch = unique_branch_name()
    base = default_branch
    try:
        with httpx.Client() as client:
            tip_sha = get_default_branch_sha(client, token, owner, repo, base)
            create_branch(client, token, owner, repo, branch, tip_sha)
            blob_sha = file_shas.get(path)
            commit_file_update(
                client,
                token,
                owner,
                repo,
                path,
                branch,
                f"fix: {fix_title}",
                new_content,
                blob_sha,
            )
            pr_body = (
                "## AutoHackFix\n\n"
                f"**What was wrong:** see issue targeting `{path}`.\n\n"
                f"**What we changed:** {fix_explanation}\n\n"
                f"**Confidence:** {confidence:.2f}\n\n"
                f"**Validation:** {validation_notes}\n\n"
                "_Opened by AutoHackFix agent pipeline._"
            )
            url = open_pull_request(
                client,
                token,
                owner,
                repo,
                fix_title,
                pr_body,
                head=branch,
                base=base,
            )
    except httpx.HTTPStatusError as e:
        err = f"GitHub error creating PR: {e.response.status_code} — {e.response.text[:400]}"
        return {"error": err, "pr_url": None, "branch_name": branch}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "pr_url": None, "branch_name": None}

    return {"error": None, "pr_url": url, "branch_name": branch}
