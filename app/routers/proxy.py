"""Transparent proxy + registration for a remote GPU backend (free tier).

A free GPU host (Colab T4 behind a quick tunnel) registers itself via
``POST /api/v1/pixel/register``; GPU-only operations are then forwarded to it:

- ``POST /images/score/{file_id}`` and ``POST /images/remove-pixel/{file_id}``
  carry the locally-uploaded file along (the GPU host can't reach Vercel's
  storage), signing with the registered key
- ``GET /tasks/{task_id}`` polls Celery state living on the GPU host
- ``GET /files/download/...`` stays local-first with a remote fallback

Everything else (text, uploads, image inspect/clean, file pipeline) always
runs locally. With no registration (or after a session's TTL expires) the
GPU-only endpoints return 503 and the rest of the app keeps working — no
manual env updates or redeploys when a Colab session rotates.

The proxy catch-all router is only mounted when a backend source is
configured (``PIXEL_REMOTE_URL`` or ``PIXEL_REGISTRY_REDIS_URL``); the
registration endpoints are always mounted.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.services import pixel_registry

router = APIRouter(prefix="/api/v1", tags=["pixel-remote"])
registry_router = APIRouter(prefix="/api/v1/pixel", tags=["pixel-registry"])

_remote_client: httpx.AsyncClient | None = None


class PixelRegisterRequest(BaseModel):
    url: str
    key: str
    token: str = ""


def _validate_gpu_url(url: str) -> bool:
    """Only allow tunnel-shaped or loopback URLs (register-time SSRF guard)."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not host:
        return False
    if host in ("127.0.0.1", "localhost"):
        return True
    return host.endswith(".trycloudflare.com")


@registry_router.post("/register")
async def register_pixel_backend(payload: PixelRegisterRequest):
    """Called by the GPU host at boot: registers its tunnel URL + key."""
    if not settings.PIXEL_REGISTRY_REDIS_URL:
        raise HTTPException(status_code=503, detail="Backend registry not configured")
    if settings.PIXEL_REGISTER_TOKEN and payload.token != settings.PIXEL_REGISTER_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not _validate_gpu_url(payload.url):
        raise HTTPException(
            status_code=400,
            detail="Only loopback or *.trycloudflare.com URLs are accepted",
        )
    if not pixel_registry.register(payload.url, payload.key):
        raise HTTPException(status_code=503, detail="Backend registry not configured")
    return {"status": "ok", "url": payload.url, "ttl": settings.PIXEL_REGISTRY_TTL}


@registry_router.delete("/register")
async def unregister_pixel_backend():
    """GPU host shutdown / offline signal."""
    pixel_registry.unregister()
    return {"status": "ok"}


def _client() -> httpx.AsyncClient:
    global _remote_client
    if _remote_client is None:
        _remote_client = httpx.AsyncClient(
            timeout=httpx.Timeout(3600, connect=10),
            limits=httpx.Limits(max_connections=8),
        )
    return _remote_client


async def _forward(request: Request, suffix: str) -> StreamingResponse:
    backend = pixel_registry.get_backend()
    if backend is None:
        return JSONResponse(
            status_code=503, content={"detail": "GPU backend not configured"}
        )
    target = f"{backend['url'].rstrip('/')}/api/v1/{suffix}"
    if request.url.query:
        target += f"?{request.url.query}"

    headers = {
        "content-type": request.headers.get("content-type") or "application/octet-stream",
        "accept": request.headers.get("accept", "*/*"),
        "x-pixel-key": backend["key"],
    }
    body = await request.body()

    req = _client().build_request(request.method, target, content=body, headers=headers)
    resp = await _client().send(req, stream=True)

    if resp.status_code >= 400:
        try:
            raw = (await resp.aread()).decode("utf-8", "replace")[:500]
        finally:
            await resp.aclose()
        return JSONResponse(status_code=resp.status_code, content={"detail": raw})

    resp_headers = {}
    for name in ("content-type", "content-disposition"):
        if resp.headers.get(name):
            resp_headers[name] = resp.headers[name]

    async def _stream():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()

    return StreamingResponse(_stream(), status_code=resp.status_code, headers=resp_headers)


@router.post("/images/score/{file_id}")
async def proxy_score_synthid(file_id: str, request: Request):
    """Proxy SynthID scoring to the GPU backend, carrying the local file."""
    return await _forward_image_op(request, "score", file_id)


@router.post("/images/remove-pixel/{file_id}")
async def proxy_remove_pixel(file_id: str, request: Request):
    """Proxy CtrlRegen pixel removal, carrying the local file."""
    return await _forward_image_op(request, "remove-pixel", file_id)


@router.get("/tasks/{rest:path}")
async def proxy_tasks(rest: str, request: Request):
    """Forward async task polling (Celery state lives on the GPU host)."""
    return await _forward(request, f"tasks/{rest}")


@router.get("/files/download/{rest:path}")
async def proxy_downloads(rest: str, request: Request):
    """Download cleaned files: local-first (non-image cleanup), remote fallback."""
    local_matches = list((Path(settings.UPLOAD_DIR) / "cleaned").glob(f"{rest}*"))
    if local_matches:
        file_path = local_matches[0]
        return FileResponse(
            file_path, filename=file_path.name, content_disposition_type="attachment"
        )
    return await _forward(request, f"files/download/{rest}")


async def _forward_image_op(request: Request, op: str, file_id: str) -> StreamingResponse:
    """GPU ops run on the backend, but the file lives here: upload it first."""
    backend = pixel_registry.get_backend()
    if backend is None:
        return JSONResponse(
            status_code=503, content={"detail": "GPU backend not configured"}
        )
    base = backend["url"].rstrip("/")
    auth = {"x-pixel-key": backend["key"]}

    try:
        raw_dir = Path(settings.UPLOAD_DIR) / "raw"
        matches = list(raw_dir.glob(f"{file_id}.*"))
        if not matches:
            return JSONResponse(status_code=404, content={"detail": "File not found"})
        file_path = matches[0]

        from mimetypes import guess_type

        with open(file_path, "rb") as fh:
            data = fh.read()
        mime = guess_type(file_path.name)[0] or "application/octet-stream"

        client = _client()
        upload_resp = await asyncio.wait_for(
            client.post(
                f"{base}/api/v1/images/upload",
                files={"file": (file_path.name, data, mime)},
                headers=auth,
            ),
            timeout=60,
        )
        if upload_resp.status_code >= 400:
            body = upload_resp.text[:300]
            return JSONResponse(
                status_code=502,
                content={"detail": f"GPU backend upload failed ({upload_resp.status_code}): {body}"},
            )
        new_id = (upload_resp.json() or {}).get("file_id")

        target = f"{base}/api/v1/images/{op}/{new_id}"
        if request.url.query:
            target += f"?{request.url.query}"

        resp = await client.send(
            client.build_request(request.method, target, headers=auth), stream=True
        )
        if resp.status_code >= 400:
            try:
                raw = (await resp.aread()).decode("utf-8", "replace")[:500]
            finally:
                await resp.aclose()
            return JSONResponse(status_code=resp.status_code, content={"detail": raw})

        resp_headers = {}
        for name in ("content-type", "content-disposition"):
            if resp.headers.get(name):
                resp_headers[name] = resp.headers[name]

        async def _stream():
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()

        return StreamingResponse(_stream(), status_code=resp.status_code, headers=resp_headers)
    except Exception as e:  # noqa: BLE001 — never leak a bare 500; surface the cause
        return JSONResponse(
            status_code=502,
            content={"detail": f"GPU backend error: {type(e).__name__}: {e}"},
        )


async def pixel_key_guard(request: Request, call_next):
    """Deny unauthenticated /api/v1 calls on the GPU host when enforcement is on."""
    if settings.PIXEL_REMOTE_ENFORCE:
        if request.headers.get("x-pixel-key") != settings.PIXEL_REMOTE_KEY:
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)