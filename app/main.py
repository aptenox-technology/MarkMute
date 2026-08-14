"""MarkMute — FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, settings
from app.routers import files, images, tasks, text

API_PREFIX = "/api/v1"

PAGES_DIR = BASE_DIR / "app" / "static" / "pages"
TOOL_PAGE = BASE_DIR / "app" / "static" / "app.html"


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


@app.get("/", include_in_schema=False)
def landing():
    return FileResponse(PAGES_DIR / "landing.html")


@app.get("/features", include_in_schema=False)
def features():
    return FileResponse(PAGES_DIR / "features.html")


@app.get("/about", include_in_schema=False)
def about():
    return FileResponse(PAGES_DIR / "about.html")


@app.get("/privacy", include_in_schema=False)
def privacy():
    return FileResponse(PAGES_DIR / "privacy.html")


@app.get("/app", include_in_schema=False)
def tool():
    return FileResponse(TOOL_PAGE)


@app.get("/api/v1/health", tags=["system"])
def health():
    from app.services.pixel_service import pixel_service

    synthid = (
        bool(settings.REVERSE_SYNTHID_DIR)
        and settings.REVERSE_SYNTHID_DIR.exists()
    )
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "synthid_available": synthid,
        "ctrlregen_available": pixel_service.is_available(),
    }


app.mount("/", StaticFiles(directory=str(BASE_DIR / "app" / "static"), html=True), name="static")
