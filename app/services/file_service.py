"""Wrapper service for file operations (metadata / C2PA / container cleaning).

Calls the original inspect_file.py and clean_file.py via subprocess.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.runner import parse_json_output, run_script


class ScriptError(RuntimeError):
    """Raised when the upstream script fails (returncode >= 2)."""


class FileService:
    def inspect(self, file_path: Path) -> dict[str, Any]:
        """Inspect a file for watermarks / metadata.

        Exit codes: 0 = clean, 1 = suspicious found (both valid results).
        The upstream script emits structured JSON with --json.
        """
        proc = run_script(
            "inspect_file.py",
            str(file_path),
            "--json",
            timeout=60,
            memory_limit_gb=4,
        )
        data = parse_json_output(proc, default={})
        data["exit_code"] = proc.returncode
        if proc.stderr.strip():
            data["stderr"] = proc.stderr.strip()
        return data

    def clean(
        self,
        input_path: Path,
        output_path: Path,
        keep_non_ai_metadata: bool = False,
    ) -> dict[str, Any]:
        """Clean a file, stripping metadata and AI traces.

        clean_file.py semantics:
          * exit 0 — fully clean
          * exit 1 — cleaned but residual C2PA/AI signals remain (best-effort;
            the output file IS written) → we still report success
          * exit 2 — usage / hard refusal errors → ScriptError
        """
        args = [str(input_path), "-o", str(output_path), "--json"]
        if keep_non_ai_metadata:
            args.append("--keep-non-ai-metadata")

        proc = run_script(
            "clean_file.py",
            *args,
            timeout=300,
            memory_limit_gb=4,
        )

        if proc.returncode >= 2:
            raise ScriptError(proc.stderr.strip() or proc.stdout.strip())

        data = parse_json_output(proc, default={})
        data["exit_code"] = proc.returncode
        if proc.stderr.strip():
            data["stderr"] = proc.stderr.strip()

        residual = bool(
            data.get("still_has_c2pa") or data.get("still_has_ai_metadata")
        )
        data["residual"] = residual
        return data


file_service = FileService()
