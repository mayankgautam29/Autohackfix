"""Repository ingest cache (Redis or file fallback via kv_cache)."""

from __future__ import annotations

import time
from typing import Any

from app.kv_cache import KVCache

_PREFIX = "ingest"


def _key(owner: str, repo: str) -> str:
    return f"{_PREFIX}:{owner.lower()}:{repo.lower()}"


def get_cached_ingest(owner: str, repo: str, *, ttl_seconds: int) -> dict[str, Any] | None:
    data = KVCache.get().get_json(_key(owner, repo))
    if not data:
        return None
    cached_at = float(data.get("cached_at") or 0)
    if ttl_seconds > 0 and (time.time() - cached_at) > ttl_seconds:
        return None
    if not data.get("files_snapshot"):
        return None
    return data


def set_cached_ingest(
    owner: str,
    repo: str,
    *,
    default_branch: str,
    files_snapshot: dict[str, str],
    file_shas: dict[str, str | None],
    ttl_seconds: int = 3600,
) -> None:
    KVCache.get().set_json(
        _key(owner, repo),
        {
            "owner": owner,
            "repo": repo,
            "default_branch": default_branch,
            "files_snapshot": files_snapshot,
            "file_shas": file_shas,
            "cached_at": time.time(),
        },
        ttl_seconds=ttl_seconds,
    )
