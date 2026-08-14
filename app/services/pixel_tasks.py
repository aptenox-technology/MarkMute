"""Celery tasks for long-running operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from celery import shared_task

from app.services.pixel_service import pixel_service


@shared_task(bind=True)
def remove_pixel_watermark(
    self,
    input_path: str,
    output_path: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Async CtrlRegen pixel-watermark removal on an image."""
    options = options or {}
    self.update_state(state="PROGRESS", meta={"progress": 10, "stage": "starting"})
    result = pixel_service.clean(
        Path(input_path),
        Path(output_path),
        strength=float(options.get("strength", 0.7)),
        steps=int(options.get("steps", 20)),
        device=str(options.get("device", "cuda")),
        seed=int(options.get("seed", 0)),
    )
    self.update_state(state="PROGRESS", meta={"progress": 100, "stage": "done"})
    return result
