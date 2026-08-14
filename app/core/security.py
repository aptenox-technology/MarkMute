"""Input validation and size limits."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.config import settings

ALLOWED_UPLOAD_EXTENSIONS = {
    ".txt", ".md", ".html", ".htm", ".svg", ".pdf",
    ".png", ".jpg", ".jpeg", ".webp",
    ".docx", ".odt",
}

BINARY_MAGIC = {
    "png": b"\x89PNG",
    "jpeg": b"\xff\xd8\xff",
    "pdf": b"%PDF",
    "webp": b"RIFF",
    "zip": b"PK\x03\x04",  # docx/odt are zip containers
}


def check_text_size(text: str) -> None:
    """Reject oversized text payloads (applies to inspect/clean/rewrite)."""
    if len(text.encode("utf-8", errors="surrogateescape")) > settings.MAX_INPUT_SIZE:
        raise HTTPException(status_code=413, detail="Text too large")


def check_filename(filename: str) -> None:
    """Validate uploaded filename: non-empty, sane length, allowed extension."""
    if not filename or len(filename) > 255:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if "\\" in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix or '(none)'}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}",
        )
    if suffix in (".exe", ".py", ".sh", ".bin"):
        raise HTTPException(status_code=415, detail="Unsupported file type")


def sniff_magic_ok(path: "Path") -> bool:
    """Sanity-check magic bytes against the declared extension (defense in depth).

    Returns True when the file is consistent with its extension:
      * declared-binary formats must start with the expected magic;
      * text formats must NOT start with a known binary magic (a binary
        pretending to be text would corrupt when scrubbed as text).
    """
    suffix = path.suffix.lower()
    expected = {
        ".png": BINARY_MAGIC["png"],
        ".jpg": BINARY_MAGIC["jpeg"],
        ".jpeg": BINARY_MAGIC["jpeg"],
        ".pdf": BINARY_MAGIC["pdf"],
        ".webp": BINARY_MAGIC["webp"],
        ".docx": BINARY_MAGIC["zip"],
        ".odt": BINARY_MAGIC["zip"],
    }.get(suffix)
    head = path.read_bytes()[:8]
    if expected is not None:
        return head.startswith(expected)
    return not any(head.startswith(m) for m in BINARY_MAGIC.values())
