from __future__ import annotations

import os
from typing import Any


class OpenAIProvider:
    name = "openai"
    cost_score = 2
    speed_score = 3
    context_score = 5

    def available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def complete(self, prompt: str, context: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        suffix = " (dry-run)" if dry_run else ""
        return {
            "content": f"openai{suffix}: processed prompt '{prompt[:80]}'",
            "tokens": max(1, len(prompt.split()) * 2),
            "raw": {"context": context},
        }
