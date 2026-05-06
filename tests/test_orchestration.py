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
        "adapter": "vector",
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
        "adapter": "vector",
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
        "adapter": "vector",
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


# ---------------------------------------------------------------------------
# search() / semantic retrieval tests
# ---------------------------------------------------------------------------


def test_vector_adapter_search_returns_matching_items() -> None:
    from agent_tools.engine.memory import VectorMemoryAdapter

    adapter = VectorMemoryAdapter()
    adapter.append("ns", {"agent_id": "a", "input": "deploy to production", "summary": "deploy prod"})
    adapter.append("ns", {"agent_id": "b", "input": "plan sprint", "summary": "sprint planning"})
    adapter.append("ns", {"agent_id": "c", "input": "deploy to staging", "summary": "deploy staging"})

    hits = adapter.search("ns", query="deploy", k=5)
    assert len(hits) == 2
    assert all("deploy" in h["input"] for h in hits)


def test_vector_adapter_search_respects_k() -> None:
    from agent_tools.engine.memory import VectorMemoryAdapter

    adapter = VectorMemoryAdapter()
    for i in range(10):
        adapter.append("ns", {"agent_id": "a", "input": f"deploy step {i}", "summary": f"s{i}"})

    hits = adapter.search("ns", query="deploy", k=3)
    assert len(hits) == 3


def test_json_adapter_search_returns_matching_items(tmp_path: Path) -> None:
    from agent_tools.engine.memory import JsonFileMemoryAdapter

    adapter = JsonFileMemoryAdapter(tmp_path / "mem.json")
    adapter.append("ns", {"agent_id": "a", "input": "hash the file", "summary": "crypto"})
    adapter.append("ns", {"agent_id": "b", "input": "read config", "summary": "filesystem"})

    hits = adapter.search("ns", query="hash", k=5)
    assert len(hits) == 1
    assert hits[0]["agent_id"] == "a"


def test_sqlite_adapter_search_returns_matching_items(tmp_path: Path) -> None:
    from agent_tools.engine.memory import SQLiteMemoryAdapter

    adapter = SQLiteMemoryAdapter(tmp_path / "mem.sqlite")
    adapter.append("ns", {"agent_id": "a", "input": "fetch url", "summary": "http call"})
    adapter.append("ns", {"agent_id": "b", "input": "read file", "summary": "filesystem"})

    hits = adapter.search("ns", query="url", k=5)
    assert len(hits) == 1
    assert hits[0]["agent_id"] == "a"


def test_search_empty_namespace_returns_empty() -> None:
    from agent_tools.engine.memory import VectorMemoryAdapter

    adapter = VectorMemoryAdapter()
    assert adapter.search("nonexistent", query="anything") == []


# ---------------------------------------------------------------------------
# session_id tests
# ---------------------------------------------------------------------------


def test_run_returns_session_id(tmp_path: Path) -> None:
    shutil.copytree(_repo_root() / "agents", tmp_path / "agents")
    executor = AgentExecutor(repo_root=tmp_path)
    result = executor.run(agent_id="master", input_text="hello", dry_run=True, session_id="s-abc")
    assert result.session_id == "s-abc"


def test_run_auto_generates_session_id_when_not_provided(tmp_path: Path) -> None:
    shutil.copytree(_repo_root() / "agents", tmp_path / "agents")
    executor = AgentExecutor(repo_root=tmp_path)
    result = executor.run(agent_id="master", input_text="hello", dry_run=True)
    assert result.session_id is not None
    assert len(result.session_id) > 0


def test_session_scoped_memory_isolates_between_sessions(tmp_path: Path) -> None:
    shutil.copytree(_repo_root() / "agents", tmp_path / "agents")
    executor = AgentExecutor(repo_root=tmp_path)

    executor.run(agent_id="master", input_text="session A prompt", dry_run=True, session_id="sess-A")
    executor.run(agent_id="master", input_text="session B prompt", dry_run=True, session_id="sess-B")

    # Second run of session A should only see session A history in cot
    r = executor.run(agent_id="master", input_text="third prompt", dry_run=True, session_id="sess-A")
    cot = r.output["raw"]["context"].get("chain_of_thought", "")
    assert "session A prompt" in cot
    assert "session B prompt" not in cot


def test_session_scoped_memory_accumulates_within_session(tmp_path: Path) -> None:
    shutil.copytree(_repo_root() / "agents", tmp_path / "agents")
    executor = AgentExecutor(repo_root=tmp_path)

    executor.run(agent_id="master", input_text="first session step", dry_run=True, session_id="sess-1")
    r = executor.run(agent_id="master", input_text="second session step", dry_run=True, session_id="sess-1")
    cot = r.output["raw"]["context"].get("chain_of_thought", "")
    assert "first session step" in cot


# ---------------------------------------------------------------------------
# semantic_context tests
# ---------------------------------------------------------------------------


def test_semantic_context_passed_to_provider(tmp_path: Path) -> None:
    shutil.copytree(_repo_root() / "agents", tmp_path / "agents")
    executor = AgentExecutor(repo_root=tmp_path)

    executor.run(agent_id="master", input_text="deploy the rocket", dry_run=True, session_id="sem-1")

    r = executor.run(agent_id="master", input_text="deploy again", dry_run=True, session_id="sem-1")
    semantic = r.output["raw"]["context"].get("semantic_context", "")
    assert isinstance(semantic, str)


# ---------------------------------------------------------------------------
# New manifest tests
# ---------------------------------------------------------------------------


def test_new_manifests_load_correctly() -> None:
    loader = AgentManifestLoader(_repo_root() / "agents")
    agents = loader.load_agents(force=True)
    for expected_id in ("overmind", "memory_summarizer", "task_planner", "npc_intel"):
        assert expected_id in agents, f"Expected manifest '{expected_id}' not found"


def test_overmind_manifest_properties() -> None:
    loader = AgentManifestLoader(_repo_root() / "agents")
    agents = loader.load_agents(force=True)
    overmind = agents["overmind"]
    assert overmind.memory_policy["adapter"] == "vector"
    assert overmind.memory_policy["max_history"] == 20
    assert "long-context" in overmind.routing_tags
    assert overmind.provider_preferences == ["realai"]


def test_npc_intel_manifest_properties() -> None:
    loader = AgentManifestLoader(_repo_root() / "agents")
    agents = loader.load_agents(force=True)
    npc = agents["npc_intel"]
    assert npc.memory_policy["namespace"] == "npc_intel"
    assert npc.memory_policy["max_history"] == 50
    assert "lore" in npc.routing_tags

