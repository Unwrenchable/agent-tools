from __future__ import annotations

import os
from typing import Any


class RealAIProvider:
    name = "realai"
    cost_score = 5
    speed_score = 4
    context_score = 4

    def available(self) -> bool:
        return bool(os.getenv("REALAI_API_KEY"))

    def complete(self, prompt: str, context: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        suffix = " (dry-run)" if dry_run else ""
        return {
            "content": f"realai{suffix}: processed prompt '{prompt[:80]}'",
            "tokens": max(1, len(prompt.split()) * 2),
            "raw": {"context": context},
        }
