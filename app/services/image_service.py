"""Wrapper service for image operations.

Calls the original inspect_image.py, clean_image.py and score_synthid.py.
Pixel-level removal (CtrlRegen) is routed through pixel_service for the
async/Celery path, but the sync wrapper is also exposed for short tasks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings
from app.core.runner import parse_json_output, run_script


class ScriptError(RuntimeError):
    """Raised when an upstream script fails (returncode >= 2)."""


class ImageService:
    def inspect(self, file_path: Path) -> dict[str, Any]:
        """Inspect an image for metadata, C2PA and AI traces."""
        args = [str(file_path), "--json"]
        if settings.REVERSE_SYNTHID_DIR:
            args += ["--synthid-dir", str(settings.REVERSE_SYNTHID_DIR)]
        proc = run_script(
            "inspect_image.py",
            *args,
            timeout=120,
            memory_limit_gb=8,
        )
        data = parse_json_output(proc, default={})
        data["exit_code"] = proc.returncode
        if proc.stderr.strip():
            data["stderr"] = proc.stderr.strip()
        return data

    def clean(
        self,
        input_path: Path,
        output_path: Path,
        keep_non_ai_metadata: bool = False,
    ) -> dict[str, Any]:
        """Clean an image, stripping metadata and AI traces."""
        args = [str(input_path), "-o", str(output_path), "--json"]
        if keep_non_ai_metadata:
            args.append("--keep-non-ai-metadata")
        if settings.REVERSE_SYNTHID_DIR:
            args += ["--synthid-dir", str(settings.REVERSE_SYNTHID_DIR)]
        proc = run_script(
            "clean_image.py",
            *args,
            timeout=600,
            memory_limit_gb=8,
        )
        if proc.returncode >= 2:
            raise ScriptError(proc.stderr.strip() or proc.stdout.strip())
        data = parse_json_output(proc, default={})
        data["exit_code"] = proc.returncode
        if proc.stderr.strip():
            data["stderr"] = proc.stderr.strip()
        return data

    def score_synthid(self, file_path: Path) -> dict[str, Any]:
        """Score an image with the reverse-SynthID pixel scorer (if installed)."""
        args = [str(file_path), "--json"]
        if settings.REVERSE_SYNTHID_DIR:
            args += ["--upstream-dir", str(settings.REVERSE_SYNTHID_DIR)]
        proc = run_script(
            "score_synthid.py",
            *args,
            timeout=300,
            memory_limit_gb=8,
        )
        if proc.returncode >= 2:
            raise ScriptError(proc.stderr.strip() or proc.stdout.strip())
        data = parse_json_output(proc, default={})
        data["exit_code"] = proc.returncode
        if proc.stderr.strip():
            data["stderr"] = proc.stderr.strip()
        return data


image_service = ImageService()
