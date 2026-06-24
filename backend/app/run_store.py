"""Persist validated scan results so PRs can be opened later without re-running AI."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

_RUNS_ROOT = Path(__file__).resolve().parent.parent / ".cache" / "runs"


def save_pr_ready_run(payload: dict[str, Any], *, ttl_seconds: int) -> str:
    """Store a validated fix snapshot; returns run_id."""
    run_id = uuid.uuid4().hex
    path = _RUNS_ROOT / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        **payload,
        "run_id": run_id,
        "created_at": time.time(),
        "ttl_seconds": ttl_seconds,
        "pr_url": None,
        "branch_name": None,
    }
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return run_id


def get_pr_ready_run(run_id: str) -> dict[str, Any] | None:
    path = _RUNS_ROOT / f"{run_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    created = float(data.get("created_at") or 0)
    ttl = int(data.get("ttl_seconds") or 3600)
    if ttl > 0 and (time.time() - created) > ttl:
        return None
    return data


def mark_run_pr_created(run_id: str, *, pr_url: str, branch_name: str) -> None:
    path = _RUNS_ROOT / f"{run_id}.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    data["pr_url"] = pr_url
    data["branch_name"] = branch_name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
