"""Key-value cache: Upstash Redis in production, local JSON files as fallback."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)
_FILE_ROOT = Path(__file__).resolve().parent.parent / ".cache" / "kv"


class KVCache:
    _instance: KVCache | None = None

    def __init__(self) -> None:
        settings = get_settings()
        self._redis: Any = None
        self._backend = "file"
        url = (settings.upstash_redis_rest_url or "").strip()
        token = (settings.upstash_redis_rest_token or "").strip()
        if url and token:
            try:
                from upstash_redis import Redis

                client = Redis(url=url, token=token)
                client.ping()
                self._redis = client
                self._backend = "redis"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Upstash Redis unavailable, using file cache: %s", exc)

    @classmethod
    def get(cls) -> KVCache:
        if cls._instance is None:
            cls._instance = KVCache()
        return cls._instance

    @property
    def backend_name(self) -> str:
        return self._backend

    def get_json(self, key: str) -> dict[str, Any] | None:
        safe = _sanitize_key(key)
        if self._redis is not None:
            try:
                raw = self._redis.get(safe)
                if raw is None:
                    return None
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                if not isinstance(raw, str):
                    raw = str(raw)
                data = json.loads(raw)
                return data if isinstance(data, dict) else None
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis get failed for %s: %s", safe, exc)
        return self._file_get(safe)

    def set_json(self, key: str, data: dict[str, Any], *, ttl_seconds: int) -> None:
        safe = _sanitize_key(key)
        blob = json.dumps(data, ensure_ascii=False)
        if self._redis is not None:
            try:
                ex = ttl_seconds if ttl_seconds > 0 else None
                self._redis.set(safe, blob, ex=ex)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis set failed for %s: %s", safe, exc)
        self._file_set(safe, data, ttl_seconds)

    def _file_get(self, safe_key: str) -> dict[str, Any] | None:
        path = _file_path(safe_key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        expires = float(data.get("_expires_at") or 0)
        if expires > 0 and time.time() > expires:
            return None
        return {k: v for k, v in data.items() if not k.startswith("_")}

    def _file_set(self, safe_key: str, data: dict[str, Any], ttl_seconds: int) -> None:
        path = _file_path(safe_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(data)
        if ttl_seconds > 0:
            payload["_expires_at"] = time.time() + ttl_seconds
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _sanitize_key(key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9:_-]+", "_", key)[:220]


def _file_path(safe_key: str) -> Path:
    file_key = safe_key.replace(":", "__")
    return _FILE_ROOT / f"{file_key}.json"


def cache_backend_name() -> str:
    return KVCache.get().backend_name
