"""Tests for public pages (landing, features, about, privacy) and SEO artifacts."""

from __future__ import annotations

EXPECTED_PAGES = {
    "/": ("MarkMute", "canonical", "Open the tool"),
    "/features": ("Features", "canonical"),
    "/about": ("About MarkMute", "canonical"),
    "/privacy": ("Privacy Policy", "canonical"),
    "/terms": ("Terms of Use", "canonical"),
}


def test_pages_are_public(client):
    for path, (needle, _canonical, *extra) in EXPECTED_PAGES.items():
        res = client.get(path)
        assert res.status_code == 200, f"{path} returned {res.status_code}"
        assert "text/html" in res.headers["content-type"], f"{path} is not HTML"
        body = res.text
        assert needle in body, f"{path} missing expected text {needle!r}"
        if extra:
            assert extra[0] in body, f"{path} missing expected CTA {extra[0]!r}"


def test_pages_have_canonical_and_meta(client):
    for path in EXPECTED_PAGES:
        body = client.get(path).text
        assert "rel=\"canonical\"" in body
        assert "meta name=\"description\"" in body
        assert "robots" in body


def test_landing_links_to_tool_and_aptenox(client):
    body = client.get("/").text
    assert 'href="/app"' in body
    assert "aptenox.com" in body
    assert 'application/ld+json' in body


def test_tool_page_at_app(client):
    res = client.get("/app")
    assert res.status_code == 200
    assert "text-input" in res.text
    assert "text-inspect" in res.text


def test_sitemap_xml(client):
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/xml")
    body = res.text
    for loc in ("/", "/app", "/features", "/about", "/privacy", "/terms"):
        assert f"https://markmute.vercel.app{loc}" in body, f"sitemap missing {loc}"


def test_robots_txt(client):
    res = client.get("/robots.txt")
    assert res.status_code == 200
    body = res.text
    assert "User-agent: *" in body
    assert "Disallow: /api/" in body
    assert "Sitemap:" in body
