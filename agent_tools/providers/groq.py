from __future__ import annotations

import os
from typing import Any


class GroqProvider:
    name = "groq"
    cost_score = 4
    speed_score = 5
    context_score = 3

    def available(self) -> bool:
        return bool(os.getenv("GROQ_API_KEY"))

    def complete(self, prompt: str, context: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        suffix = " (dry-run)" if dry_run else ""
        return {
            "content": f"groq{suffix}: processed prompt '{prompt[:80]}'",
            "tokens": max(1, len(prompt.split())),
            "raw": {"context": context},
        }
