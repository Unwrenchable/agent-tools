from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ManifestValidationError(ValueError):
    def __init__(self, source: Path, errors: list[str]) -> None:
        self.source = source
        self.errors = errors
        super().__init__(f"Invalid manifest {source}: {'; '.join(errors)}")


@dataclass(slots=True)
class AgentManifest:
    id: str
    role: str
    goals: list[str]
    input_format: dict[str, Any]
    output_format: dict[str, Any]
    tools_allowed: list[str]
    memory_policy: dict[str, Any]
    routing_tags: list[str]
    description: str = ""
    provider_preferences: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)


_REQUIRED_AGENT_FIELDS: tuple[str, ...] = (
    "id",
    "role",
    "goals",
    "input_format",
    "output_format",
    "tools_allowed",
    "memory_policy",
    "routing_tags",
)


class AgentManifestLoader:
    def __init__(self, agents_dir: Path | None = None) -> None:
        self._repo_root = Path(__file__).resolve().parents[2]
        self._agents_dir = agents_dir or (self._repo_root / "agents")
        self._cache: dict[str, AgentManifest] = {}
        self._mtimes: dict[Path, float] = {}

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    def discover_manifest_files(self) -> list[Path]:
        if not self._agents_dir.exists():
            return []
        return sorted(self._agents_dir.glob("*.agentx"))

    def load_agents(self, force: bool = False) -> dict[str, AgentManifest]:
        files = self.discover_manifest_files()
        if not force and not self._requires_reload(files):
            return dict(self._cache)

        loaded: dict[str, AgentManifest] = {}
        new_mtimes: dict[Path, float] = {}
        for path in files:
            raw = self._load_json(path)
            errors = validate_agent_manifest(raw)
            if errors:
                raise ManifestValidationError(path, errors)
            manifest = AgentManifest(
                id=raw["id"],
                role=raw["role"],
                goals=list(raw["goals"]),
                input_format=dict(raw["input_format"]),
                output_format=dict(raw["output_format"]),
                tools_allowed=list(raw["tools_allowed"]),
                memory_policy=dict(raw["memory_policy"]),
                routing_tags=list(raw["routing_tags"]),
                description=str(raw.get("description", "")),
                provider_preferences=list(raw.get("provider_preferences", [])),
                skills=list(raw.get("skills", [])),
            )
            loaded[manifest.id] = manifest
            new_mtimes[path] = path.stat().st_mtime

        self._cache = loaded
        self._mtimes = new_mtimes
        return dict(loaded)

    def get(self, agent_id: str) -> AgentManifest | None:
        return self.load_agents().get(agent_id)

    def _load_json(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        raw = json.loads(text)
        if not isinstance(raw, dict):
            raise ManifestValidationError(path, ["manifest must be a JSON object"])
        return raw

    def _requires_reload(self, files: list[Path]) -> bool:
        if set(files) != set(self._mtimes):
            return True
        for path in files:
            previous = self._mtimes.get(path)
            current = path.stat().st_mtime
            if previous != current:
                return True
        return False


def validate_agent_manifest(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    for key in _REQUIRED_AGENT_FIELDS:
        if key not in raw:
            errors.append(f"missing required field '{key}'")

    if "id" in raw and (not isinstance(raw["id"], str) or not raw["id"].strip()):
        errors.append("id must be a non-empty string")
    if "role" in raw and (not isinstance(raw["role"], str) or not raw["role"].strip()):
        errors.append("role must be a non-empty string")

    for list_field in ("goals", "tools_allowed", "routing_tags"):
        value = raw.get(list_field)
        if value is not None and not isinstance(value, list):
            errors.append(f"{list_field} must be a list")

    for dict_field in ("input_format", "output_format", "memory_policy"):
        value = raw.get(dict_field)
        if value is not None and not isinstance(value, dict):
            errors.append(f"{dict_field} must be an object")

    input_type = raw.get("input_format", {}).get("type") if isinstance(raw.get("input_format"), dict) else None
    if input_type and input_type not in {"text", "json"}:
        errors.append("input_format.type must be one of: text, json")

    output_type = raw.get("output_format", {}).get("type") if isinstance(raw.get("output_format"), dict) else None
    if output_type and output_type not in {"text", "json"}:
        errors.append("output_format.type must be one of: text, json")

    adapter = raw.get("memory_policy", {}).get("adapter") if isinstance(raw.get("memory_policy"), dict) else None
    if "memory_policy" in raw and not adapter:
        errors.append("memory_policy.adapter is required")

    return errors
