"""Text endpoints: inspect / clean / rewrite."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.security import check_text_size
from app.models.schemas import (
    TextCleanRequest,
    TextCleanResponse,
    TextInspectRequest,
    TextInspectResponse,
    TextRewriteRequest,
    TextRewriteResponse,
)
from app.services.text_service import ScriptError, text_service

router = APIRouter(prefix="/api/v1/text", tags=["text"])


@router.post("/inspect", response_model=TextInspectResponse)
async def inspect_text(request: TextInspectRequest):
    """Inspect text for invisible Unicode characters and space homoglyphs."""
    check_text_size(request.text)
    try:
        return text_service.inspect(
            request.text,
            aggressive=request.aggressive,
            strip_emoji_glue=request.strip_emoji_glue,
        )
    except ScriptError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clean", response_model=TextCleanResponse)
async def clean_text(request: TextCleanRequest):
    """Clean text by removing invisible Unicode characters."""
    check_text_size(request.text)
    try:
        return text_service.clean(request.text, request.options)
    except ScriptError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rewrite", response_model=TextRewriteResponse)
async def rewrite_text(request: TextRewriteRequest):
    """Rewrite text to defeat statistical (token-sampling) watermarks — Layer B."""
    check_text_size(request.text)
    try:
        return text_service.rewrite(
            request.text,
            backend=request.backend,
            strength=request.strength,
            lang=request.lang,
            original_lang=request.original_lang,
            temperature=request.temperature,
            candidates=request.candidates,
        )
    except ScriptError as e:
        raise HTTPException(status_code=500, detail=str(e))