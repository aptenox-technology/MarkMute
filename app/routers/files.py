"""File endpoints: upload / inspect / clean / download.

Blocking script calls run in FastAPI's threadpool (sync def), keeping the
event loop responsive.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.core.security import check_filename, sniff_magic_ok
from app.models.schemas import CleanResponse, InspectResponse, UploadResponse
from app.services.file_service import ScriptError, file_service

router = APIRouter(prefix="/api/v1/files", tags=["files"])


def _resolve_raw(file_id: str) -> Path:
    raw_dir = Path(settings.UPLOAD_DIR) / "raw"
    matches = list(raw_dir.glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="File not found")
    return matches[0]


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """Upload a file for inspection / cleaning."""
    check_filename(file.filename or "")
    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower()
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

    return UploadResponse(file_id=file_id, filename=file.filename, size=size)


@router.post("/inspect/{file_id}", response_model=InspectResponse)
def inspect_file(file_id: str):
    """Inspect an uploaded file for watermarks and metadata."""
    file_path = _resolve_raw(file_id)
    try:
        detail = file_service.inspect(file_path)
    except ScriptError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return InspectResponse(success=True, detail=detail)


@router.post("/clean/{file_id}", response_model=CleanResponse)
def clean_file(file_id: str, keep_non_ai_metadata: bool = False):
    """Clean an uploaded file, stripping metadata and AI traces."""
    file_path = _resolve_raw(file_id)
    cleaned_dir = Path(settings.UPLOAD_DIR) / "cleaned"
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    output_path = cleaned_dir / f"{file_id}_cleaned{file_path.suffix}"

    try:
        detail = file_service.clean(
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


@router.get("/download/{file_id}")
def download_file(file_id: str):
    """Download a cleaned file."""
    cleaned_dir = Path(settings.UPLOAD_DIR) / "cleaned"
    matches = list(cleaned_dir.glob(f"{file_id}*"))
    if not matches:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = matches[0]
    return FileResponse(file_path, filename=file_path.name, content_disposition_type="attachment")