"""Pydantic request/response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import RewriteBackend, RewriteStrength


# ---------- Text ----------


class TextInspectRequest(BaseModel):
    text: str = Field(max_length=268435456, description="Text to inspect for invisible Unicode / space homoglyphs")
    aggressive: bool = False
    strip_emoji_glue: bool = False


class TextCleanOptions(BaseModel):
    nfkc: bool = False
    aggressive_homoglyphs: bool = False
    strip_emoji_glue: bool = False


class TextCleanRequest(BaseModel):
    text: str = Field(max_length=268435456)
    options: TextCleanOptions = TextCleanOptions()


class TextRewriteRequest(BaseModel):
    text: str = Field(max_length=268435456)
    backend: RewriteBackend = RewriteBackend.print_prompt
    strength: RewriteStrength = RewriteStrength.paraphrase
    lang: str = "French"
    original_lang: str = "English"
    temperature: float | None = None
    candidates: int | None = None


class TextResponse(BaseModel):
    success: bool
    detail: dict[str, Any] | None = None
    message: str | None = None


class TextInspectResponse(BaseModel):
    success: bool
    suspicious_total: int = 0
    length: int = 0
    hits: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    raw_output: str | None = None


class TextCleanResponse(BaseModel):
    success: bool
    cleaned_text: str | None = None
    stats: dict[str, Any] | None = None
    message: str | None = None


class TextRewriteResponse(BaseModel):
    success: bool
    rewritten_text: str | None = None
    stats: dict[str, Any] | None = None
    message: str | None = None


# ---------- Files / Images ----------


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    size: int


class InspectResponse(BaseModel):
    success: bool
    detail: dict[str, Any] | None = None
    message: str | None = None


class CleanResponse(BaseModel):
    success: bool
    file_id: str
    cleaned_file_id: str
    download_url: str
    detail: dict[str, Any] | None = None
    message: str | None = None


# ---------- Tasks ----------


class TaskStatusResponse(BaseModel):
    task_id: str
    state: str
    progress: int | None = None
    result: dict[str, Any] | None = None
