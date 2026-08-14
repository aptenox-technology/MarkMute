"""Wrapper service for text operations.

Calls the original watermarks-remover scripts (inspect_text.py,
clean_text.py, rewrite_text.py) via subprocess — never reimplements them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.core.runner import parse_json_output, run_script
from app.core.utils import temp_text_file
from app.models.schemas import TextCleanOptions


class ScriptError(RuntimeError):
    """Raised when an upstream script fails hard (returncode >= 2)."""


class TextService:
    def inspect(
        self,
        text: str,
        aggressive: bool = False,
        strip_emoji_glue: bool = False,
    ) -> dict[str, Any]:
        """Inspect text for invisible Unicode / space homoglyphs (Layer A).

        Upstream exit codes: 0 = clean, 1 = suspicious found (both are valid).
        """
        with temp_text_file(text) as path:
            args = [path, "--json"]
            if aggressive:
                args.append("--aggressive")
            if strip_emoji_glue:
                args.append("--strip-emoji-glue")
            proc = run_script("inspect_text.py", *args, timeout=60)

        data = parse_json_output(proc, default={})
        return {
            "success": True,
            "length": data.get("length", len(text)),
            "suspicious_total": data.get("suspicious_total", 0),
            "hits": data.get("hits", []),
            "notes": data.get("notes", []),
            "exit_code": proc.returncode,
            "raw_output": (proc.stdout + proc.stderr).strip() or None,
        }

    def clean(self, text: str, options: TextCleanOptions) -> dict[str, Any]:
        """Clean text via the original clean_text.py (Layer A removal).

        The original script is a pure scrubber: it has no failure path other
        than usage errors (exit 2), so success is structural here.
        """
        with temp_text_file(text) as in_path:
            out_path = in_path.replace(".txt", ".cleaned.txt")
            args = [in_path, "-o", out_path, "--stats"]
            if options.nfkc:
                args.append("--nfkc")
            if options.aggressive_homoglyphs:
                args.append("--aggressive-homoglyphs")
            if options.strip_emoji_glue:
                args.append("--strip-emoji-glue")

            proc = run_script("clean_text.py", *args, timeout=60)

            stats = None
            if proc.stderr.strip():
                try:
                    stats = json.loads(proc.stderr)
                except json.JSONDecodeError:
                    pass

            if Path(out_path).exists():
                cleaned = Path(out_path).read_text(encoding="utf-8", errors="surrogateescape")
            else:
                cleaned = None

            if proc.returncode >= 2:
                raise ScriptError(proc.stderr.strip() or proc.stdout.strip())

            return {
                "success": True,
                "cleaned_text": cleaned,
                "stats": stats,
                "raw_output": proc.stdout.strip() or None,
            }

    def rewrite(
        self,
        text: str,
        backend: str = "print-prompt",
        strength: str = "paraphrase",
        lang: str = "French",
        original_lang: str = "English",
        temperature: float | None = None,
        candidates: int | None = None,
    ) -> dict[str, Any]:
        """Rewrite text to defeat statistical watermarks (Layer B).

        print-prompt backend: prints the prompt and returns the input
        unchanged — useful for previewing before paying for an LLM call.
        """
        with temp_text_file(text) as in_path:
            out_path = in_path.replace(".txt", ".rewritten.txt")
            args = [
                in_path,
                "-o", out_path,
                "--backend", backend,
                "--strength", strength,
                "--lang", lang,
                "--original-lang", original_lang,
                "--json-stats",
            ]
            if temperature is not None:
                args += ["--temperature", str(temperature)]
            if candidates is not None:
                args += ["--candidates", str(candidates)]

            env_overrides = {
                "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
                "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),
                "OLLAMA_HOST": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
                "WATERMARKS_REWRITE_ALLOW_REMOTE": os.environ.get(
                    "WATERMARKS_REWRITE_ALLOW_REMOTE", "0"
                ),
                "WATERMARKS_REWRITE_API_KEY": os.environ.get("WATERMARKS_REWRITE_API_KEY"),
                "WATERMARKS_REWRITE_MODEL": os.environ.get("WATERMARKS_REWRITE_MODEL"),
                "WATERMARKS_REWRITE_BASE_URL": os.environ.get("WATERMARKS_REWRITE_BASE_URL"),
            }

            proc = run_script(
                "rewrite_text.py",
                *args,
                env_overrides=env_overrides,
                timeout=300,
            )

            stats = None
            if proc.stderr.strip():
                try:
                    stats = json.loads(proc.stderr)
                except json.JSONDecodeError:
                    pass

            rewritten = None
            if Path(out_path).exists():
                rewritten = Path(out_path).read_text(encoding="utf-8", errors="surrogateescape")

            if proc.returncode != 0:
                raise ScriptError(
                    (proc.stderr.strip() or proc.stdout.strip())
                    or f"rewrite_text.py exited {proc.returncode}"
                )

            return {
                "success": True,
                "rewritten_text": rewritten,
                "stats": stats,
                "raw_output": proc.stdout.strip() or None,
            }


text_service = TextService()
