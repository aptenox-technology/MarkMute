"""Transparent proxy to a remote GPU backend (free tier).

When ``PIXEL_REMOTE_URL`` is configured, the image pipeline (upload / inspect /
clean / score / remove-pixel), async task polling and file downloads are
forwarded verbatim to that host, so the app can offer CtrlRegen pixel removal
and SynthID scoring without owning a GPU. Requests sign with ``PIXEL_REMOTE_KEY``.

The proxy router is only mounted when ``PIXEL_REMOTE_URL`` is set — otherwise
the local routers serve those endpoints directly.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.config import settings

router = APIRouter(prefix="/api/v1", tags=["pixel-remote"])

_remote_client: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _remote_client
    if _remote_client is None:
        _remote_client = httpx.AsyncClient(
            timeout=httpx.Timeout(3600, connect=10),
            limits=httpx.Limits(max_connections=8),
        )
    return _remote_client


async def _forward(request: Request, suffix: str) -> StreamingResponse:
    base = settings.PIXEL_REMOTE_URL.rstrip("/")
    target = f"{base}/api/v1/{suffix}"
    if request.url.query:
        target += f"?{request.url.query}"

    headers = {
        "content-type": request.headers.get("content-type") or "application/octet-stream",
        "accept": request.headers.get("accept", "*/*"),
        "x-pixel-key": settings.PIXEL_REMOTE_KEY,
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


@router.api_route("/images/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_images(rest: str, request: Request):
    """Forward the whole image pipeline (upload → inspect → clean → GPU jobs)."""
    return await _forward(request, f"images/{rest}")


@router.api_route("/tasks/{rest:path}", methods=["GET", "POST"])
async def proxy_tasks(rest: str, request: Request):
    """Forward async job polling (Celery state lives on the GPU host)."""
    return await _forward(request, f"tasks/{rest}")


@router.api_route("/files/download/{rest:path}", methods=["GET"])
async def proxy_downloads(rest: str, request: Request):
    """Download cleaned files: local-first (non-image cleanup), remote fallback."""
    local_matches = list((Path(settings.UPLOAD_DIR) / "cleaned").glob(f"{rest}*"))
    if local_matches:
        file_path = local_matches[0]
        return FileResponse(
            file_path, filename=file_path.name, content_disposition_type="attachment"
        )
    return await _forward(request, f"files/download/{rest}")


async def pixel_key_guard(request: Request, call_next):
    """Deny unauthenticated /api/v1 calls on the GPU host when enforcement is on."""
    if settings.PIXEL_REMOTE_ENFORCE:
        if request.headers.get("x-pixel-key") != settings.PIXEL_REMOTE_KEY:
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)