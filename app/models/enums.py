"""Enums shared across API and services."""

from __future__ import annotations

from enum import Enum


class TextCleanOptions(str, Enum):
    """Map of web options to clean_text.py behavior (defaults mirror the original)."""

    nfkc = "nfkc"
    aggressive_homoglyphs = "aggressive_homoglyphs"
    strip_emoji_glue = "strip_emoji_glue"


class RewriteBackend(str, Enum):
    print_prompt = "print-prompt"
    ollama = "ollama"
    openai_compatible = "openai-compatible"


class RewriteStrength(str, Enum):
    paraphrase = "paraphrase"
    backtranslate = "backtranslate"
    structural = "structural"
    humanize = "humanize"
    code = "code"


class FindingConfidence(str, Enum):
    confirmed = "confirmed"
    probable = "probable"
    suspected = "suspected"


class FileKind(str, Enum):
    text = "text"
    image = "image"
    container = "container"
    unknown = "unknown"


class TaskState(str, Enum):
    pending = "PENDING"
    started = "STARTED"
    progress = "PROGRESS"
    success = "SUCCESS"
    failure = "FAILURE"
