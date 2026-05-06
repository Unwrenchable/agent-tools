from __future__ import annotations

from pathlib import Path

import pytest

from agent_tools.engine.executor import AgentExecutor
from agent_tools.engine.loader import AgentManifestLoader, validate_agent_manifest
from agent_tools.providers.router import ProviderRouter


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_manifest_loader_and_schema_validation() -> None:
    loader = AgentManifestLoader(_repo_root() / "agents")
    agents = loader.load_agents(force=True)
    assert "master" in agents

    invalid = {
        "id": "bad",
        "role": "Bad Agent",
    }
    errors = validate_agent_manifest(invalid)
    assert any("missing required field" in err for err in errors)


def test_tool_permission_enforcement() -> None:
    executor = AgentExecutor(repo_root=_repo_root())
    with pytest.raises(PermissionError):
        executor.run(agent_id="router", input_text="Create sha256 hash", dry_run=False)


def test_dry_run_has_no_side_effect_tools() -> None:
    executor = AgentExecutor(repo_root=_repo_root())
    result = executor.run(agent_id="master", input_text="Read file and hash this", dry_run=True)
    assert result.dry_run is True
    assert result.tool_calls
    assert all("DRY_RUN" in str(call["result"]) for call in result.tool_calls)


def test_provider_router_fallback_to_local_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("REALAI_API_KEY", raising=False)

    router = ProviderRouter()
    provider = router.select_provider(routing_tags=["routing"], preferred_order=["openai", "groq"])
    assert provider.name == "local"


def test_provider_override_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    executor = AgentExecutor(repo_root=_repo_root())
    result = executor.run(
        agent_id="master",
        input_text="simple prompt",
        provider_override="openai",
        dry_run=True,
    )
    assert result.provider == "openai"
