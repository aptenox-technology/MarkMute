"""Atomic writes, temp-file helpers and cleanup."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def temp_text_file(text: str, suffix: str = ".txt") -> Iterator[str]:
    """Write `text` to a temp file, yield its path, always delete it."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        yield path
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically (temp file + rename) to avoid partial reads."""
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
