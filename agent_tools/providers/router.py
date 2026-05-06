from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .anthropic import AnthropicProvider
from .groq import GroqProvider
from .local import LocalProvider
from .openai import OpenAIProvider
from .realai import RealAIProvider


class ProviderClient(Protocol):
    name: str
    cost_score: int
    speed_score: int
    context_score: int

    def available(self) -> bool: ...

    def complete(self, prompt: str, context: dict[str, Any], dry_run: bool) -> dict[str, Any]: ...


@dataclass(slots=True)
class _ProviderScore:
    provider: ProviderClient
    score: int


class ProviderRouter:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderClient] = {
            "openai": OpenAIProvider(),
            "groq": GroqProvider(),
            "anthropic": AnthropicProvider(),
            "realai": RealAIProvider(),
            "local": LocalProvider(),
        }

    def select_provider(
        self,
        routing_tags: list[str],
        preferred_order: list[str] | None = None,
        user_preference: str | None = None,
    ) -> ProviderClient:
        if user_preference:
            preferred = self._providers.get(user_preference)
            if preferred and preferred.available():
                return preferred

        weighted = self._rank_providers(routing_tags, preferred_order or [])
        for entry in weighted:
            if entry.provider.available():
                return entry.provider

        return self._providers["local"]

    def _rank_providers(self, routing_tags: list[str], preferred_order: list[str]) -> list[_ProviderScore]:
        preferred_position = {name: idx for idx, name in enumerate(preferred_order)}
        is_long_context = any(tag in {"long-context", "analysis"} for tag in routing_tags)
        wants_speed = any(tag in {"realtime", "routing", "classification"} for tag in routing_tags)

        scores: list[_ProviderScore] = []
        for name, provider in self._providers.items():
            score = provider.cost_score * 3
            score += provider.speed_score * (3 if wants_speed else 2)
            score += provider.context_score * (3 if is_long_context else 1)
            if name in preferred_position:
                score += max(0, 5 - preferred_position[name]) * 3
            scores.append(_ProviderScore(provider=provider, score=score))

        return sorted(scores, key=lambda item: (item.score, item.provider.name), reverse=True)
