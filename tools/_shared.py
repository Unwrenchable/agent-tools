"""Shared utilities for tools/ scripts."""
from __future__ import annotations

import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> str:
    """Run a subprocess command and return stripped stdout.

    Raises RuntimeError on non-zero exit when *check* is True.
    """
    process = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if check and process.returncode != 0:
        raise RuntimeError(
            f"Command failed ({process.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{process.stdout}\n"
            f"stderr:\n{process.stderr}"
        )
    return process.stdout.strip()
