"""Persistent registry for the remote GPU backend (free tier).

The GPU host (a free Colab session behind a quick tunnel) self-registers its
tunnel URL + API key after boot, so the public app needs no manual env updates
or redeploys when a session rotates. Storage is Redis (Upstash free tier) with
a ~12 h TTL — when registration expires, the proxy reports the backend as
unavailable until the next session registers.

The static env var ``PIXEL_REMOTE_URL`` always wins over the registry.
"""

from __future__ import annotations

import json
import time

import redis

from app.config import settings

REGISTRY_KEY = "markmute:pixel:backend"
CACHE_TTL_SECONDS = 45.0

_client: redis.Redis | None = None
_cache: tuple[float, dict] | None = None


def _get_client() -> redis.Redis | None:
    global _client
    if _client is None:
        if not settings.PIXEL_REGISTRY_REDIS_URL:
            return None
        _client = redis.from_url(
            settings.PIXEL_REGISTRY_REDIS_URL, decode_responses=True
        )
    return _client


def register(url: str, key: str) -> bool:
    """Persist the backend with a TTL; returns False when no registry is set."""
    client = _get_client()
    if client is None:
        return False
    client.set(
        REGISTRY_KEY,
        json.dumps({"url": url, "key": key}),
        ex=settings.PIXEL_REGISTRY_TTL,
    )
    _invalidate_cache()
    return True


def unregister() -> bool:
    client = _get_client()
    if client is None:
        return False
    client.delete(REGISTRY_KEY)
    _invalidate_cache()
    return True


def get_backend() -> dict | None:
    """Return {"url", "key"} for the active backend, honoring a short cache."""
    global _cache
    if settings.PIXEL_REMOTE_URL:
        return {"url": settings.PIXEL_REMOTE_URL, "key": settings.PIXEL_REMOTE_KEY}
    client = _get_client()
    if client is None:
        return None
    if _cache is not None and time.monotonic() - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]
    try:
        raw = client.get(REGISTRY_KEY)
        value = json.loads(raw) if raw else None
    except Exception:
        value = None
    _cache = (time.monotonic(), value)
    return value


def _invalidate_cache() -> None:
    global _cache
    _cache = None