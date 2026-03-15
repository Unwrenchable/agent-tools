from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Iterable

from .models import AccessProfile, AgentDefinition


def _find_agentx_override(filename: str) -> Path | None:
    """Walk from CWD upward to find .agentx/<filename>, stopping at a .git boundary."""
    current = Path.cwd()
    for directory in [current, *current.parents]:
        candidate = directory / ".agentx" / filename
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists():
            break
    return None


def _merge_json_lists(base: list[dict], override: list[dict]) -> list[dict]:
    """Merge *override* into *base*, keyed by the item's 'id' or 'name' field.

    Items that are not dicts or that lack both 'id' and 'name' are skipped.
    """
    def _key(item: dict) -> str:
        return str(item.get("id") or item.get("name") or "")

    merged: dict[str, dict] = {}
    for item in base:
        if not isinstance(item, dict):
            continue
        k = _key(item)
        if k:
            merged[k] = item

    for item in override:
        if not isinstance(item, dict):
            continue
        k = _key(item)
        if k:
            merged[k] = item

    return list(merged.values())


def _load_json_resource(filename: str) -> list[dict]:
    resource = files("agent_tools.data").joinpath(filename)
    with resource.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Resource {filename} must contain a JSON array")

    local_path = _find_agentx_override(filename)
    if local_path is not None:
        try:
            local_data = json.loads(local_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in per-repo override {local_path}: {exc}") from exc
        if isinstance(local_data, list):
            data = _merge_json_lists(data, local_data)

    return data


def load_profiles() -> dict[str, AccessProfile]:
    profiles = {}
    for item in _load_json_resource("access_profiles.json"):
        profile = AccessProfile(
            name=item["name"],
            tools=item.get("tools", []),
            write=bool(item.get("write", False)),
            network=bool(item.get("network", False)),
            secrets=item.get("secrets", "none"),
            notes=item.get("notes", ""),
        )
        profiles[profile.name] = profile
    return profiles


def load_agents() -> dict[str, AgentDefinition]:
    agents = {}
    for item in _load_json_resource("agents.json"):
        agent = AgentDefinition.from_dict(item)
        agents[agent.id] = agent
    return agents


def find_agents(agents: dict[str, AgentDefinition], query: str) -> Iterable[AgentDefinition]:
    lowered = query.lower().strip()
    for agent in agents.values():
        haystack = " ".join(
            [
                agent.id,
                agent.role,
                agent.description,
                *agent.tags,
                *agent.capabilities,
            ]
        ).lower()
        if lowered in haystack:
            yield agent


def assess_agent_access(agent: AgentDefinition, profile: AccessProfile) -> dict:
    required = set(agent.required_tools)
    granted = set(profile.tools)
    missing = sorted(required - granted)
    extra = sorted(granted - required)
    pass_state = len(missing) == 0

    return {
        "agent": agent.id,
        "profile": profile.name,
        "pass": pass_state,
        "missing_tools": missing,
        "extra_tools": extra,
        "risk_level": agent.risk_level,
        "recommended_profile": agent.preferred_profile,
    }


def recommend_profile(agent: AgentDefinition, profiles: dict[str, AccessProfile]) -> AccessProfile:
    if agent.preferred_profile in profiles:
        return profiles[agent.preferred_profile]

    fallback_order = ["safe", "balanced", "power"]
    for name in fallback_order:
        profile = profiles.get(name)
        if profile is None:
            continue
        if not set(agent.required_tools) - set(profile.tools):
            return profile

    return next(iter(profiles.values()))
