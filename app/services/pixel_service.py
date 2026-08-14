"""Pixel-level watermark removal (CtrlRegen backend).

This is GPU-heavy and slow (minutes per image), so it only ever runs as a
Celery task. The module must stay importable without Redis/Celery workers
running — the celery import is lazy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings
from app.core.runner import run_script


class PixelService:
    """Sync wrapper around clean_image.py's --remove-pixel ctrlregen path.

    Used by the Celery task; the FastAPI layer never calls this inline.
    """

    def clean(
        self,
        input_path: Path,
        output_path: Path,
        strength: float = 0.7,
        steps: int = 20,
        device: str = "cuda",
        seed: int = 0,
        timeout: int = 1800,
    ) -> dict[str, Any]:
        if not settings.NOAI_WATERMARK_DIR:
            raise RuntimeError(
                "NOAI_WATERMARK_DIR not configured — CtrlRegen backend unavailable"
            )
        args = [
            str(input_path),
            "-o", str(output_path),
            "--json",
            "--remove-pixel", "ctrlregen",
            "--ctrlregen-dir", str(settings.NOAI_WATERMARK_DIR),
            "--ctrlregen-strength", str(strength),
            "--ctrlregen-steps", str(steps),
            "--ctrlregen-device", device,
            "--ctrlregen-seed", str(seed),
        ]
        proc = run_script(
            "clean_image.py",
            *args,
            timeout=timeout,
            memory_limit_gb=16,
        )
        if proc.returncode >= 2:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
        return {
            "success": proc.returncode == 0 and Path(output_path).exists(),
            "exit_code": proc.returncode,
            "output_path": str(output_path),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    def is_available(self) -> bool:
        if not settings.NOAI_WATERMARK_DIR:
            return False
        return Path(settings.NOAI_WATERMARK_DIR).exists()


pixel_service = PixelService()
