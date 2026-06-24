"""File-backed cache for repository ingest snapshots (avoids re-fetching on reruns)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

_CACHE_ROOT = Path(__file__).resolve().parent.parent / ".cache" / "repos"


def _safe_key(owner: str, repo: str) -> str:
    raw = f"{owner}__{repo}".lower()
    return re.sub(r"[^a-z0-9._-]+", "_", raw)


def _cache_path(owner: str, repo: str) -> Path:
    return _CACHE_ROOT / f"{_safe_key(owner, repo)}.json"


def get_cached_ingest(owner: str, repo: str, *, ttl_seconds: int) -> dict[str, Any] | None:
    """Return cached ingest payload if present and not expired."""
    path = _cache_path(owner, repo)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
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
) -> None:
    path = _cache_path(owner, repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "owner": owner,
        "repo": repo,
        "default_branch": default_branch,
        "files_snapshot": files_snapshot,
        "file_shas": file_shas,
        "cached_at": time.time(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
