"""Task status polling for async Celery jobs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.celery import celery_app
from app.models.schemas import TaskStatusResponse

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskStatusResponse)
def task_status(task_id: str):
    """Poll the state of an async task (pixel removal, rewrite)."""
    result = celery_app.AsyncResult(task_id)

    progress = None
    if result.info:
        if isinstance(result.info, dict):
            progress = result.info.get("progress")
            info = result.info
        else:
            info = str(result.info)
    else:
        info = None

    return TaskStatusResponse(
        task_id=task_id,
        state=result.state,
        progress=progress,
        result=info if result.state == "SUCCESS" else None,
    )