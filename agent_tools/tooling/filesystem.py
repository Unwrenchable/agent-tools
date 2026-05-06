from __future__ import annotations

from pathlib import Path
from typing import Any

from .registry import ToolDefinition


def get_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="filesystem",
        description="Read files or list directories in workspace",
        input_schema={"required": ["operation", "path"]},
        output_schema={"required": ["ok", "result"]},
        safety="guarded",
        handler=_handle_filesystem,
    )


def _handle_filesystem(payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    operation = str(payload["operation"])
    target = Path(str(payload["path"]))

    if dry_run:
        return {"ok": True, "result": f"DRY_RUN: would run {operation} on {target}"}

    if operation == "read":
        if not target.exists() or not target.is_file():
            return {"ok": False, "result": "file not found"}
        return {"ok": True, "result": target.read_text(encoding="utf-8")[:500]}

    if operation == "list":
        if not target.exists() or not target.is_dir():
            return {"ok": False, "result": []}
        return {"ok": True, "result": sorted(item.name for item in target.iterdir())}

    return {"ok": False, "result": f"unknown operation: {operation}"}
