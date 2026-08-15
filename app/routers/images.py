"""Image endpoints: inspect / clean / synthid score / async pixel removal."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.core.security import check_filename, sniff_magic_ok
from app.models.schemas import CleanResponse, InspectResponse
from app.services.image_service import ScriptError, image_service
from app.services.pixel_service import pixel_service

router = APIRouter(prefix="/api/v1/images", tags=["images"])


def _resolve_raw(file_id: str) -> Path:
    raw_dir = Path(settings.UPLOAD_DIR) / "raw"
    matches = list(raw_dir.glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="File not found")
    return matches[0]


@router.post("/upload", response_model=dict)
async def upload_image(file: UploadFile = File(...)):
    """Upload an image for inspection / cleaning."""
    check_filename(file.filename or "")
    ext = Path(file.filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(status_code=415, detail="Only PNG, JPEG or WebP images are supported")

    file_id = f"img_{uuid4().hex}"
    upload_path = Path(settings.UPLOAD_DIR) / "raw" / f"{file_id}{ext}"
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    with open(upload_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.MAX_FILE_SIZE:
                upload_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large")
            out.write(chunk)

    if not sniff_magic_ok(upload_path):
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=415, detail="File content does not match its extension")

    return {"file_id": file_id, "filename": file.filename, "size": size}


@router.post("/inspect/{file_id}", response_model=InspectResponse)
def inspect_image(file_id: str):
    """Inspect an image for metadata, C2PA and AI traces."""
    file_path = _resolve_raw(file_id)
    try:
        detail = image_service.inspect(file_path)
    except ScriptError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return InspectResponse(success=True, detail=detail)


@router.post("/clean/{file_id}", response_model=CleanResponse)
def clean_image(file_id: str, keep_non_ai_metadata: bool = False):
    """Clean an image, stripping metadata and AI traces."""
    file_path = _resolve_raw(file_id)
    cleaned_dir = Path(settings.UPLOAD_DIR) / "cleaned"
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    output_path = cleaned_dir / f"{file_id}_cleaned{file_path.suffix}"

    try:
        detail = image_service.clean(
            file_path, output_path, keep_non_ai_metadata=keep_non_ai_metadata
        )
    except ScriptError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not output_path.exists():
        raise HTTPException(status_code=500, detail="Clean failed: no output produced")

    return CleanResponse(
        success=True,
        file_id=file_id,
        cleaned_file_id=f"{file_id}_cleaned",
        download_url=f"/api/v1/files/download/{file_id}_cleaned{file_path.suffix}",
        detail=detail,
    )


@router.post("/score/{file_id}", response_model=InspectResponse)
def score_synthid(file_id: str):
    """Score an image with the reverse-SynthID pixel scorer."""
    if not settings.REVERSE_SYNTHID_DIR:
        raise HTTPException(status_code=503, detail="SynthID scorer not configured")
    file_path = _resolve_raw(file_id)
    try:
        detail = image_service.score_synthid(file_path)
    except ScriptError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return InspectResponse(success=True, detail=detail)


@router.post("/remove-pixel/{file_id}")
def start_pixel_removal(file_id: str, strength: float = 0.7, steps: int = 20):
    """Start async CtrlRegen pixel-watermark removal (Celery task).

    Returns a task_id for /api/v1/tasks/{task_id} polling.
    """
    if not pixel_service.is_available():
        raise HTTPException(status_code=503, detail="CtrlRegen backend not configured")

    from app.services.pixel_tasks import remove_pixel_watermark

    file_path = _resolve_raw(file_id)
    cleaned_dir = Path(settings.UPLOAD_DIR) / "cleaned"
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    output_path = cleaned_dir / f"{file_id}_ctrlregen{file_path.suffix}"

    try:
        task = remove_pixel_watermark.delay(
            str(file_path),
            str(output_path),
            {"strength": strength, "steps": steps},
        )
    except Exception as e:  # noqa: BLE001 — broker (redis) down: tell the caller why
        raise HTTPException(
            status_code=503,
            detail=f"Job broker unavailable: {type(e).__name__}: {e}",
        )
    return {"task_id": task.id, "download_url": f"/api/v1/files/download/{file_id}_ctrlregen{file_path.suffix}"}
