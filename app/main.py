"""MarkMute — FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, settings
from app.routers import files, images, tasks, text

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure runtime dirs exist
    for sub in ("raw", "cleaned", "backups"):
        (settings.UPLOAD_DIR / sub).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Best-effort removal of watermarks, invisible Unicode traces and "
        "metadata from your own content. Wraps the original "
        "watermarks-remover toolkit."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(text.router)
app.include_router(files.router)
app.include_router(images.router)
app.include_router(tasks.router)


@app.get("/api/v1/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "synthid_available": bool(settings.REVERSE_SYNTHID_DIR),
        "ctrlregen_available": bool(settings.NOAI_WATERMARK_DIR),
    }


app.mount("/", StaticFiles(directory=str(BASE_DIR / "app" / "static"), html=True), name="static")
