from __future__ import annotations

from dataclasses import dataclass

from .loader import AgentManifest


@dataclass(slots=True)
class RouteDecision:
    agent_id: str
    reason: str


class AgentRouter:
    def route(
        self,
        agents: dict[str, AgentManifest],
        text: str,
        preferred_agent_id: str | None = None,
    ) -> RouteDecision:
        if not agents:
            raise ValueError("No agent manifests available")

        if preferred_agent_id and preferred_agent_id in agents:
            return RouteDecision(agent_id=preferred_agent_id, reason="explicit selection")

        lowered = text.lower()
        best_agent_id: str | None = None
        best_score = -1

        for agent_id, manifest in sorted(agents.items()):
            score = 0
            for tag in manifest.routing_tags:
                if tag.lower() in lowered:
                    score += 3
            for goal in manifest.goals:
                for word in goal.lower().split():
                    if word in lowered:
                        score += 1

            if score > best_score:
                best_agent_id = agent_id
                best_score = score

        if best_agent_id is None:
            fallback = sorted(agents)[0]
            return RouteDecision(agent_id=fallback, reason="fallback first agent")

        reason = "tag/goal match" if best_score > 0 else "fallback deterministic order"
        return RouteDecision(agent_id=best_agent_id, reason=reason)
