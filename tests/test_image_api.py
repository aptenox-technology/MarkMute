"""Image API tests (upload / inspect / clean)."""

from __future__ import annotations

import io


def test_image_upload_inspect_clean(client, sample_png_bytes):
    res = client.post(
        "/api/v1/images/upload",
        files={"file": ("photo.png", io.BytesIO(sample_png_bytes), "image/png")},
    )
    assert res.status_code == 200
    file_id = res.json()["file_id"]

    res = client.post(f"/api/v1/images/inspect/{file_id}")
    assert res.status_code == 200
    detail = res.json()["detail"]
    assert detail["format"] == "png"

    res = client.post(f"/api/v1/images/clean/{file_id}")
    assert res.status_code == 200
    clean = res.json()
    assert clean["success"] is True

    res = client.get(clean["download_url"])
    assert res.status_code == 200
    assert res.content.startswith(b"\x89PNG")


def test_image_upload_rejects_non_image(client):
    res = client.post(
        "/api/v1/images/upload",
        files={"file": ("note.md", io.BytesIO(b"# hi"), "text/markdown")},
    )
    assert res.status_code == 415


def test_image_upload_jpeg(client):
    # Minimal JPEG (SOI + EOI) — sniff only checks magic bytes
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    res = client.post(
        "/api/v1/images/upload",
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert res.status_code == 200
