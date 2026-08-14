"""Text API tests (inspect / clean / rewrite)."""

from __future__ import annotations


def test_inspect_finds_zwsp(client):
    text = "Hello\u200bWorld"
    res = client.post("/api/v1/text/inspect", json={"text": text})
    assert res.status_code == 200
    data = res.json()
    assert data["suspicious_total"] > 0
    kinds = {h["kind"] for h in data["hits"]}
    assert "zwj_family" in kinds


def test_inspect_clean_text_returns_ok(client):
    res = client.post("/api/v1/text/inspect", json={"text": "Plain text, no marks."})
    assert res.status_code == 200
    assert res.json()["suspicious_total"] == 0


def test_clean_removes_invisibles(client):
    text = "Hello\u200bWorld\u200e"
    res = client.post(
        "/api/v1/text/clean",
        json={"text": text, "options": {"nfkc": False}},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["cleaned_text"] == "HelloWorld"
    assert data["stats"]["removed_count"] == 2


def test_clean_aggressive_homoglyphs(client):
    # Cyrillic 'а' (U+0430) inside "cafe" — homoglyph mapping
    text = "caf\u0430"
    res = client.post(
        "/api/v1/text/clean",
        json={"text": text, "options": {"aggressive_homoglyphs": True}},
    )
    assert res.status_code == 200
    assert res.json()["cleaned_text"] == "cafa"


def test_clean_no_unicode_is_noop(client):
    res = client.post(
        "/api/v1/text/clean",
        json={"text": "nothing here", "options": {}},
    )
    assert res.status_code == 200
    assert res.json()["cleaned_text"] == "nothing here"


def test_rewrite_print_prompt_returns_prompt(client):
    text = "The quick brown fox jumps over the lazy dog."
    res = client.post(
        "/api/v1/text/rewrite",
        json={"text": text, "backend": "print-prompt", "strength": "paraphrase"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    # print-prompt backend emits the LLM prompt itself (no API call)
    assert data["rewritten_text"].startswith("Rewrite the following text")
    assert text in data["rewritten_text"]


def test_rewrite_invalid_backend_rejected(client):
    res = client.post(
        "/api/v1/text/rewrite",
        json={"text": "x", "backend": "does-not-exist"},
    )
    assert res.status_code == 422


def test_oversized_text_rejected(client):
    res = client.post(
        "/api/v1/text/inspect",
        json={"text": "x" * (512 * 1024 * 1024)},
    )
    # Pydantic max_length (268435456) rejects at 422 before our byte-size check
    assert res.status_code in (413, 422)
