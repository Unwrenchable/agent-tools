from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    safety: str
    handler: Callable[[dict[str, Any], bool], dict[str, Any]]


class ToolRegistry:
    def __init__(self, tools: dict[str, ToolDefinition]) -> None:
        self._tools = tools

    @classmethod
    def auto_wire(cls) -> "ToolRegistry":
        tools: dict[str, ToolDefinition] = {}
        for module_name in ("http", "filesystem", "crypto", "solana"):
            module = import_module(f"agent_tools.tooling.{module_name}")
            definition = module.get_tool_definition()
            tools[definition.name] = definition
        return cls(tools)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def invoke(
        self,
        tool_name: str,
        payload: dict[str, Any],
        allowed_tools: list[str],
        dry_run: bool,
    ) -> dict[str, Any]:
        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        if tool_name not in allowed_tools:
            raise PermissionError(f"Tool '{tool_name}' is not allowed for this agent")

        tool = self._tools[tool_name]
        _validate_payload(payload, tool.input_schema)
        output = tool.handler(payload, dry_run)
        _validate_payload(output, tool.output_schema)
        return output


def _validate_payload(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    required = schema.get("required", [])
    if not isinstance(required, list):
        raise ValueError("schema.required must be a list")
    for key in required:
        if key not in payload:
            raise ValueError(f"Missing required key '{key}'")
