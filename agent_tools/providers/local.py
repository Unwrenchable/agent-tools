from __future__ import annotations

from typing import Any


class LocalProvider:
    name = "local"
    cost_score = 5
    speed_score = 5
    context_score = 2

    def available(self) -> bool:
        return True

    def complete(self, prompt: str, context: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        suffix = " (dry-run)" if dry_run else ""
        tool_count = len(context.get("tools", []))
        return {
            "content": f"local{suffix}: executed with {tool_count} tool calls for '{prompt[:80]}'",
            "tokens": max(1, len(prompt.split())),
            "raw": {"context": context},
        }
