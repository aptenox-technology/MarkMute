"""Tests for the remote GPU backend proxy, registry and API-key guard."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from app.config import settings
from app.services import pixel_registry


class FakeRedis:
    def __init__(self):
        self.d = {}
        self.last_ex = None

    def set(self, key, value, ex=None):
        self.d[key] = value
        self.last_ex = ex
        return True

    def get(self, key):
        return self.d.get(key)

    def delete(self, key):
        return self.d.pop(key, None) is not None


def _clear_registry():
    pixel_registry._client = None
    pixel_registry._cache = None


def test_proxy_not_mounted_without_config(client):
    # No PIXEL_REMOTE_URL/registry → local image routes answer instead.
    res = client.post("/api/v1/images/remove-pixel/whatever")
    assert res.status_code == 503  # CtrlRegen not configured locally


def test_register_503_without_registry(client):
    _clear_registry()
    res = client.post(
        "/api/v1/pixel/register",
        json={"url": "https://abc.trycloudflare.com", "key": "k"},
    )
    assert res.status_code == 503


def test_register_validates_url_and_token(client, monkeypatch):
    _clear_registry()
    monkeypatch.setattr(settings, "PIXEL_REGISTRY_REDIS_URL", "redis://fake")
    monkeypatch.setattr(pixel_registry, "register", lambda url, key: True)

    bad = client.post(
        "/api/v1/pixel/register", json={"url": "https://evil.example/x", "key": "k"}
    )
    assert bad.status_code == 400

    good = client.post(
        "/api/v1/pixel/register",
        json={"url": "https://abc.trycloudflare.com", "key": "k"},
    )
    assert good.status_code == 200

    monkeypatch.setattr(settings, "PIXEL_REGISTER_TOKEN", "t0ken")
    denied = client.post(
        "/api/v1/pixel/register",
        json={"url": "https://abc.trycloudflare.com", "key": "k", "token": "nope"},
    )
    assert denied.status_code == 403

    allowed = client.post(
        "/api/v1/pixel/register",
        json={"url": "http://127.0.0.1:18000", "key": "k", "token": "t0ken"},
    )
    assert allowed.status_code == 200


def test_registry_roundtrip_with_ttl(monkeypatch):
    _clear_registry()
    fake = FakeRedis()
    monkeypatch.setattr(settings, "PIXEL_REGISTRY_REDIS_URL", "redis://fake")
    monkeypatch.setattr(settings, "PIXEL_REMOTE_URL", "")
    monkeypatch.setattr(pixel_registry, "_client", fake)

    assert pixel_registry.get_backend() is None
    assert pixel_registry.register("https://abc.trycloudflare.com", "key123")
    assert fake.last_ex == settings.PIXEL_REGISTRY_TTL

    backend = pixel_registry.get_backend()
    assert backend == {"url": "https://abc.trycloudflare.com", "key": "key123"}

    assert pixel_registry.unregister()
    assert pixel_registry.get_backend() is None


def test_env_url_wins_over_registry(monkeypatch):
    _clear_registry()
    monkeypatch.setattr(settings, "PIXEL_REGISTRY_REDIS_URL", "redis://fake")
    monkeypatch.setattr(settings, "PIXEL_REMOTE_URL", "https://static.example")
    monkeypatch.setattr(settings, "PIXEL_REMOTE_KEY", "kk")
    assert pixel_registry.get_backend() == {
        "url": "https://static.example",
        "key": "kk",
    }


def _run_forward_image_op(monkeypatch, tmp_path, file_id, op):
    """Drive _forward_image_op with a fake backend client and a real file."""
    from app.routers import proxy

    calls = []
    upload_target = tmp_path / "raw" / f"{file_id}.png"
    upload_target.parent.mkdir(parents=True, exist_ok=True)
    upload_target.write_bytes(b"\x89PNG\r\n\x1a\n fakepng")

    class UploadResponse:
        status_code = 200

        def json(self):
            return {"file_id": "img_remote_1"}

    class OpResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def aiter_bytes(self):
            yield b'{"task_id": "abc"}'

        async def aread(self):
            return b""

        async def aclose(self):
            pass

    class FakeClient:
        async def post(self, url, files=None, headers=None):
            calls.append(("upload", url, files["file"][1], headers))
            return UploadResponse()

        def build_request(self, method, target, headers=None):
            calls.append(("op", target, method, headers))
            return ("op", target)

        async def send(self, req, stream=True):
            return OpResponse()

    monkeypatch.setattr(
        settings, "PIXEL_REMOTE_URL", "https://gpuhost.example"
    )
    monkeypatch.setattr(settings, "PIXEL_REMOTE_KEY", "k")
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(proxy, "_remote_client", FakeClient())

    import asyncio

    from fastapi import Request

    request = AsyncMock(spec=Request)
    request.method = "POST"
    request.url = type("U", (), {"query": "strength=0.5&steps=3"})()
    return asyncio.run(proxy._forward_image_op(request, op, file_id)), calls


def test_forward_image_op_carries_local_file(monkeypatch, tmp_path):
    resp, calls = _run_forward_image_op(monkeypatch, tmp_path, "img_local", "remove-pixel")
    assert calls[0][1] == "https://gpuhost.example/api/v1/images/upload"
    assert calls[0][2] == b"\x89PNG\r\n\x1a\n fakepng"
    assert calls[0][3] == {"x-pixel-key": "k"}
    assert calls[1][1] == "https://gpuhost.example/api/v1/images/remove-pixel/img_remote_1?strength=0.5&steps=3"
    assert calls[1][2] == "POST"
    assert resp.status_code == 200


def test_forward_image_op_503_without_backend(client, monkeypatch):
    from app.routers import proxy

    monkeypatch.setattr(settings, "PIXEL_REMOTE_URL", "")
    monkeypatch.setattr(pixel_registry, "_cache", (0, None))
    # Registry reads settings at call time; give it an empty backend.
    monkeypatch.setattr(settings, "PIXEL_REGISTRY_REDIS_URL", "redis://fake")

    import asyncio

    from fastapi import Request

    request = AsyncMock(spec=Request)
    request.method = "POST"
    request.url = type("U", (), {"query": ""})()
    resp = asyncio.run(proxy._forward_image_op(request, "score", "img_local"))
    assert resp.status_code == 503


def test_forward_image_op_404_for_missing_file(client, monkeypatch):
    from app.routers import proxy

    monkeypatch.setattr(settings, "PIXEL_REMOTE_URL", "https://gpuhost.example")
    monkeypatch.setattr(settings, "PIXEL_REMOTE_KEY", "k")

    import asyncio

    from fastapi import Request

    request = AsyncMock(spec=Request)
    request.method = "POST"
    request.url = type("U", (), {"query": ""})()
    resp = asyncio.run(proxy._forward_image_op(request, "score", "missing_id"))
    assert resp.status_code == 404


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