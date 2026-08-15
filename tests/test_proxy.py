"""Tests for the remote GPU backend proxy and the GPU-host API-key guard."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


def test_proxy_not_mounted_without_config(client):
    # No PIXEL_REMOTE_URL → local image routes answer instead of the proxy.
    res = client.post("/api/v1/images/remove-pixel/whatever")
    assert res.status_code == 503  # CtrlRegen not configured locally


def test_api_key_guard_blocks_when_key_set(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "PIXEL_REMOTE_KEY", "s3cret")
    monkeypatch.setattr(settings, "PIXEL_REMOTE_ENFORCE", True)
    res = client.get("/api/v1/health")
    assert res.status_code == 403  # all /api/v1 guarded on the GPU host


def test_api_key_guard_allows_with_key(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "PIXEL_REMOTE_KEY", "s3cret")
    monkeypatch.setattr(settings, "PIXEL_REMOTE_ENFORCE", True)
    res = client.get("/api/v1/health", headers={"x-pixel-key": "s3cret"})
    assert res.status_code == 200


def test_api_key_guard_noop_when_not_enforced(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "PIXEL_REMOTE_KEY", "s3cret")
    res = client.get("/api/v1/health")
    assert res.status_code == 200  # hardening key set but enforcement off


def test_forward_builds_target_and_streams(monkeypatch):
    from app.routers import proxy

    received = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def aiter_bytes(self):
            yield b'{"ok": true}'

        async def aread(self):
            return b""

        async def aclose(self):
            pass

    fake_client = MagicMock()
    fake_client.build_request.side_effect = (
        lambda method, target, content=b"", headers=None: (method, target, content, headers)
    )

    async def fake_send(req, stream=True):
        received["method"], received["target"], received["content"], received["headers"] = req
        return FakeResponse()

    fake_client.send = fake_send

    monkeypatch.setattr(proxy, "_remote_client", fake_client)
    monkeypatch.setattr(
        proxy.settings, "PIXEL_REMOTE_URL", "https://gpuhost.example"
    )
    monkeypatch.setattr(proxy.settings, "PIXEL_REMOTE_KEY", "k")

    import asyncio

    async def run():
        req = __import__("fastapi").Request
        request = AsyncMock(spec=req)
        request.method = "POST"
        request.url = type("U", (), {"query": "strength=0.5&steps=3"})()
        request.headers.get = lambda n, *a: "application/octet-stream"
        request.body = AsyncMock(return_value=b"\x89PNG")

        return await proxy._forward(request, "images/upload")

    resp = asyncio.run(run())
    assert received["method"] == "POST"
    assert received["target"] == "https://gpuhost.example/api/v1/images/upload?strength=0.5&steps=3"
    assert received["content"] == b"\x89PNG"
    assert received["headers"]["x-pixel-key"] == "k"
    assert resp.headers["content-type"] == "application/json"