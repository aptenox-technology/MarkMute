"""Shared subprocess runner for the original watermarks-remover scripts.

Every original script is invoked through this helper so that:
  * a single policy governs timeouts, resource limits and env passthrough,
  * callers never touch subprocess directly,
  * the script directory is resolved exactly once.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from app.config import settings


def run_script(
    script_name: str,
    *args: str,
    env_overrides: dict[str, str] | None = None,
    timeout: int = 60,
    memory_limit_gb: int = 4,
    input_text: str | None = None,
) -> subprocess.CompletedProcess:
    """Run one of the upstream scripts with policy limits.

    Args:
        script_name: filename inside the upstream scripts dir (e.g. "inspect_text.py").
        *args: CLI arguments passed to the script (paths, flags).
        env_overrides: extra environment variables for the subprocess.
        timeout: hard timeout in seconds.
        memory_limit_gb: RLIMIT_AS limit in GiB (POSIX only; ignored on Windows).
        input_text: if set, piped to the child's stdin.
    """
    script = settings.SCRIPTS_DIR / script_name
    if not script.exists():
        raise FileNotFoundError(f"Original script not found: {script}")

    env = os.environ.copy()
    if env_overrides:
        env.update({k: v for k, v in env_overrides.items() if v is not None})

    return subprocess.run(
        ["python3", str(script), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        input=input_text,
        preexec_fn=_set_limits(memory_limit_gb) if os.name != "nt" else None,
    )


def parse_json_output(proc: subprocess.CompletedProcess, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Best-effort parse of the script's JSON stdout."""
    if not proc.stdout.strip():
        return default if default is not None else {}
    try:
        data = json.loads(proc.stdout)
        return data if isinstance(data, dict) else (default if default is not None else {})
    except json.JSONDecodeError:
        return default if default is not None else {}


def _set_limits(gb: int):
    """Build a POSIX preexec_fn applying RLIMIT_AS / RLIMIT_FSIZE.

    Some platforms (notably macOS) refuse to lower an infinite RLIMIT_AS
    hard limit — failure there is non-fatal, the child still gets RLIMIT_FSIZE.
    """
    import resource

    def _apply() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_AS, (gb * 1024 ** 3, gb * 1024 ** 3))
        except (ValueError, OSError):
            pass
        resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 ** 3, 2 * 1024 ** 3))

    return _apply
