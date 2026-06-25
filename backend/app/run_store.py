"""Persist validated scan results for deferred PR creation (Redis or file fallback)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.kv_cache import KVCache

_PREFIX = "run"


def save_pr_ready_run(payload: dict[str, Any], *, ttl_seconds: int) -> str:
    run_id = uuid.uuid4().hex
    record = {
        **payload,
        "run_id": run_id,
        "created_at": time.time(),
        "ttl_seconds": ttl_seconds,
        "pr_url": None,
        "branch_name": None,
    }
    KVCache.get().set_json(f"{_PREFIX}:{run_id}", record, ttl_seconds=ttl_seconds)
    return run_id


def get_pr_ready_run(run_id: str) -> dict[str, Any] | None:
    data = KVCache.get().get_json(f"{_PREFIX}:{run_id}")
    if not data:
        return None
    created = float(data.get("created_at") or 0)
    ttl = int(data.get("ttl_seconds") or 3600)
    if ttl > 0 and (time.time() - created) > ttl:
        return None
    return data


def mark_run_pr_created(run_id: str, *, pr_url: str, branch_name: str) -> None:
    key = f"{_PREFIX}:{run_id}"
    data = KVCache.get().get_json(key)
    if not data:
        return
    data["pr_url"] = pr_url
    data["branch_name"] = branch_name
    ttl = int(data.get("ttl_seconds") or 3600)
    remaining = max(60, int(ttl - (time.time() - float(data.get("created_at") or 0))))
    KVCache.get().set_json(key, data, ttl_seconds=remaining)
