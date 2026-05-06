from __future__ import annotations

import urllib.request
from typing import Any

from .registry import ToolDefinition


def get_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="http",
        description="Perform simple HTTP requests",
        input_schema={"required": ["url", "method"]},
        output_schema={"required": ["status", "body"]},
        safety="guarded",
        handler=_handle_http,
    )


def _handle_http(payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"status": 0, "body": f"DRY_RUN: would request {payload['url']}"}

    req = urllib.request.Request(url=str(payload["url"]), method=str(payload["method"]).upper())
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
        body = resp.read(256).decode("utf-8", errors="replace")
        return {"status": int(resp.status), "body": body}
