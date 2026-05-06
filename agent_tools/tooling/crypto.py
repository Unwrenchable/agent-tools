from __future__ import annotations

import hashlib
from typing import Any

from .registry import ToolDefinition


def get_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="crypto",
        description="Compute cryptographic hashes",
        input_schema={"required": ["operation", "text"]},
        output_schema={"required": ["algorithm", "digest"]},
        safety="safe",
        handler=_handle_crypto,
    )


def _handle_crypto(payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    operation = str(payload["operation"]).lower()
    text = str(payload["text"])

    if operation != "sha256":
        raise ValueError("crypto tool supports only sha256")

    if dry_run:
        return {"algorithm": "sha256", "digest": "DRY_RUN"}

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"algorithm": "sha256", "digest": digest}
