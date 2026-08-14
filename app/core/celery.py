"""Celery app for long-running pixel-removal / rewrite jobs.

Celery + Redis are optional. The web app works without them; only
/start async operations (CtrlRegen pixel removal, remote LLM rewrites)
require a broker. If REDIS_URL is unreachable, those endpoints 503.
"""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "markmute",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.services.pixel_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,
    worker_prefetch_multiplier=1,
)
