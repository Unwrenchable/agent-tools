"""Isolated unit tests for MemorySummarizerAgent.

These tests use a pre-built in-memory VectorMemoryAdapter and a stub
RealAIProvider so they run without any network access or env vars.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent_tools.agents_impl.memory_summarizer_agent import MemorySummarizerAgent
from agent_tools.engine.memory import VectorMemoryAdapter, create_memory_adapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_provider(response: str = "• Summary 1\n• Summary 2\n• Summary 3") -> MagicMock:
    p = MagicMock()
    p.complete.return_value = {"response": response, "tokens": 5, "latency_ms": 1}
    return p


def _make_agent(
    provider: MagicMock | None = None,
    mem: VectorMemoryAdapter | None = None,
) -> tuple[MemorySummarizerAgent, VectorMemoryAdapter]:
    memory = mem or VectorMemoryAdapter()
    agent = MemorySummarizerAgent(
        repo_root=Path("/tmp/test-ms"),
        memory=memory,
        provider=provider or _stub_provider(),
    )
    return agent, memory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_summarize_empty_namespace_returns_empty() -> None:
    agent, _ = _make_agent()
    assert agent.summarize_namespace("empty-ns") == []


def test_summarize_namespace_writes_back_to_memory() -> None:
    agent, mem = _make_agent()
    for i in range(3):
        mem.append("ns", {"agent_id": "eng", "input": f"step {i}", "summary": ""})

    results = agent.summarize_namespace("ns", max_items=10)

    assert len(results) >= 1
    stored = mem.read("ns", limit=50)
    summarizer_entries = [s for s in stored if s.get("source") == "memory_summarizer"]
    assert len(summarizer_entries) >= 1, "Summarizer did not write back summaries"


def test_summarize_session_targets_global_namespace() -> None:
    provider = _stub_provider("• done")
    agent, mem = _make_agent(provider=provider)
    session_id = "test-session-xyz"
    ns = f"{session_id}:global"
    mem.append(ns, {"agent_id": "a1", "input": "first input", "tool_calls": []})
    mem.append(ns, {"agent_id": "a2", "input": "second input", "tool_calls": []})
    mem.append(ns, {"agent_id": "a3", "input": "third input", "tool_calls": []})

    summaries = agent.summarize_session(session_id=session_id, max_items=10)

    assert isinstance(summaries, list)
    assert len(summaries) >= 1
    stored = mem.read(ns, limit=50)
    assert any(s.get("source") == "memory_summarizer" for s in stored)


def test_summarize_dry_run_passes_flag_to_provider() -> None:
    provider = _stub_provider("[DRY RUN]")
    agent, mem = _make_agent(provider=provider)
    mem.append("ns", {"agent_id": "x", "input": "task", "summary": ""})

    agent.summarize_namespace("ns", dry_run=True)

    provider.complete.assert_called_once()
    assert provider.complete.call_args.kwargs.get("dry_run") is True


def test_summarize_prompt_body_contains_item_data() -> None:
    provider = _stub_provider("• s")
    agent, mem = _make_agent(provider=provider)
    mem.append("ns", {"agent_id": "reviewer", "input": "review PR #42", "summary": "LGTM"})

    agent.summarize_namespace("ns")

    prompt = provider.complete.call_args.kwargs.get("prompt") or provider.complete.call_args.args[0]
    assert "reviewer" in prompt
    assert "review PR #42" in prompt


def test_summarize_fallback_when_fewer_summary_lines_than_items() -> None:
    # Provider returns only 1 line but 3 items exist.
    provider = _stub_provider("only one line")
    agent, mem = _make_agent(provider=provider)
    for i in range(3):
        mem.append("ns", {"agent_id": "a", "input": f"step {i}", "summary": f"orig {i}"})

    results = agent.summarize_namespace("ns")

    assert len(results) == 3
    # First item gets the real summary line.
    assert results[0]["summary"] == "only one line"
    # Remaining get the original summary text as fallback.
    assert results[1]["summary"] == "orig 1"
    assert results[2]["summary"] == "orig 2"


def test_create_memory_adapter_with_embeddings_provider_vector_type(tmp_path: Path) -> None:
    """embeddings_provider is silently ignored for the in-memory vector adapter."""
    fake_provider = MagicMock()
    fake_provider.embed.return_value = [[0.1, 0.2]]

    adapter = create_memory_adapter("vector", tmp_path, embeddings_provider=fake_provider)
    adapter.append("ns", {"k": "v"})
    assert adapter.read("ns") == [{"k": "v"}]
    fake_provider.embed.assert_not_called()


def test_agent_accepts_memory_injection_directly(tmp_path: Path) -> None:
    """Passing memory= should use that adapter instead of constructing one."""
    mem = VectorMemoryAdapter()
    agent = MemorySummarizerAgent(repo_root=tmp_path, memory=mem)
    assert agent.memory is mem
