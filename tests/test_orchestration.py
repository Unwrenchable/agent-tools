from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent_tools.engine.executor import AgentExecutor
from agent_tools.engine.loader import AgentManifestLoader, validate_agent_manifest
from agent_tools.engine.memory import VectorMemoryAdapter
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


# ---------------------------------------------------------------------------
# Chain-of-thought memory tests
# ---------------------------------------------------------------------------


def test_load_memory_history_reads_global_and_agent(tmp_path: Path) -> None:
    adapter = VectorMemoryAdapter()
    adapter.append("global", {"agent_id": "master", "input": "g0", "summary": "global stuff"})
    adapter.append("master", {"agent_id": "master", "input": "l0", "summary": "local stuff"})

    executor = AgentExecutor(repo_root=tmp_path)
    policy = {
        "adapter": "json",
        "namespace": "master",
        "use_global": True,
        "use_agent_local": True,
        "max_history": 10,
    }
    history = executor._load_memory_history(adapter, policy, "master")

    assert len(history["global"]) == 1
    assert history["global"][0]["summary"] == "global stuff"
    assert len(history["agent"]) == 1
    assert history["agent"][0]["summary"] == "local stuff"


def test_load_memory_history_respects_max_history(tmp_path: Path) -> None:
    adapter = VectorMemoryAdapter()
    for i in range(8):
        adapter.append("global", {"agent_id": "a", "input": f"g{i}", "summary": f"gs{i}"})
        adapter.append("master", {"agent_id": "a", "input": f"l{i}", "summary": f"ls{i}"})

    executor = AgentExecutor(repo_root=tmp_path)
    policy = {
        "adapter": "json",
        "namespace": "master",
        "use_global": True,
        "use_agent_local": True,
        "max_history": 3,
    }
    history = executor._load_memory_history(adapter, policy, "master")

    assert len(history["global"]) == 3
    assert history["global"][-1]["input"] == "g7"
    assert len(history["agent"]) == 3
    assert history["agent"][-1]["input"] == "l7"


def test_load_memory_history_disable_global(tmp_path: Path) -> None:
    adapter = VectorMemoryAdapter()
    adapter.append("global", {"agent_id": "a", "input": "g0", "summary": "gs0"})
    adapter.append("master", {"agent_id": "a", "input": "l0", "summary": "ls0"})

    executor = AgentExecutor(repo_root=tmp_path)
    policy = {
        "adapter": "json",
        "namespace": "master",
        "use_global": False,
        "use_agent_local": True,
        "max_history": 10,
    }
    history = executor._load_memory_history(adapter, policy, "master")

    assert history["global"] == []
    assert len(history["agent"]) == 1


def test_chain_of_thought_populated_on_second_run(tmp_path: Path) -> None:
    shutil.copytree(_repo_root() / "agents", tmp_path / "agents")
    executor = AgentExecutor(repo_root=tmp_path)

    # First run — no prior memory, so chain_of_thought should be empty
    r1 = executor.run(agent_id="master", input_text="first prompt", dry_run=True)
    assert r1.output["raw"]["context"].get("chain_of_thought", "") == ""

    # Second run — should see the first run's entry in chain_of_thought
    r2 = executor.run(agent_id="master", input_text="second prompt", dry_run=True)
    cot = r2.output["raw"]["context"].get("chain_of_thought", "")
    assert "first prompt" in cot


def test_global_memory_written_after_run(tmp_path: Path) -> None:
    from agent_tools.engine.memory import JsonFileMemoryAdapter

    shutil.copytree(_repo_root() / "agents", tmp_path / "agents")
    executor = AgentExecutor(repo_root=tmp_path)
    executor.run(agent_id="master", input_text="test memory write", dry_run=True)

    adapter = JsonFileMemoryAdapter(tmp_path / ".agentx" / "memory.json")
    global_entries = adapter.read(namespace="global")
    assert any(e.get("input") == "test memory write" for e in global_entries)

