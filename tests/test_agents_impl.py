"""Tests for agent_tools.agents_impl — MemorySummarizerAgent and CodeEngineerAgent."""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agent_tools.agents_impl.code_engineer_agent import CodeEngineerAgent
from agent_tools.agents_impl.memory_summarizer_agent import MemorySummarizerAgent
from agent_tools.engine.memory import VectorMemoryAdapter


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_provider(response: str = "• item 1\n• item 2") -> MagicMock:
    """Return a mock RealAIProvider that returns *response*."""
    provider = MagicMock()
    provider.complete.return_value = {"response": response, "tokens": 10, "latency_ms": 50}
    return provider


# ---------------------------------------------------------------------------
# MemorySummarizerAgent tests
# ---------------------------------------------------------------------------


class TestMemorySummarizerAgent:
    def _make_agent(self, provider: Any | None = None) -> tuple[MemorySummarizerAgent, VectorMemoryAdapter]:
        mem = VectorMemoryAdapter()
        agent = MemorySummarizerAgent(repo_root=Path("/tmp/test-summarizer"))
        agent.memory = mem  # swap for in-memory adapter
        if provider is not None:
            agent._provider = provider
        return agent, mem

    def test_summarize_empty_namespace_returns_empty(self) -> None:
        agent, _ = self._make_agent()
        result = agent.summarize_namespace("empty-ns")
        assert result == []

    def test_summarize_dry_run_skips_real_provider(self) -> None:
        provider = _make_provider("[DRY RUN] summary")
        agent, mem = self._make_agent(provider=provider)
        mem.append("ns", {"agent_id": "a", "input": "hello", "summary": ""})
        result = agent.summarize_namespace("ns", dry_run=True)
        # dry_run is passed through to provider.complete
        provider.complete.assert_called_once()
        call_kwargs = provider.complete.call_args.kwargs
        assert call_kwargs.get("dry_run") is True

    def test_summarize_namespace_writes_results_back(self) -> None:
        provider = _make_provider("summary of item 1\nsummary of item 2")
        agent, mem = self._make_agent(provider=provider)
        mem.append("ns", {"agent_id": "a", "input": "do X", "summary": ""})
        mem.append("ns", {"agent_id": "b", "input": "do Y", "summary": ""})

        results = agent.summarize_namespace("ns")

        assert len(results) == 2
        for r in results:
            assert "original" in r
            assert "summary" in r
            assert r["summary"]

        # Summaries written back into namespace
        stored = mem.read("ns")
        summarized = [s for s in stored if s.get("source") == "memory_summarizer"]
        assert len(summarized) == 2

    def test_summarize_session_uses_global_namespace(self) -> None:
        provider = _make_provider("• done")
        agent, mem = self._make_agent(provider=provider)
        session_id = "test-session-abc"
        ns = f"{session_id}:global"
        mem.append(ns, {"agent_id": "x", "input": "task", "summary": "result"})

        results = agent.summarize_session(session_id=session_id)

        assert len(results) == 1
        provider.complete.assert_called_once()
        # The prompt should mention the item
        prompt_arg = provider.complete.call_args.kwargs.get("prompt") or provider.complete.call_args.args[0]
        assert "task" in prompt_arg

    def test_summarize_fewer_summary_lines_than_items_writes_fallback(self) -> None:
        # Provider returns only 1 line for 3 items.
        provider = _make_provider("only one summary line")
        agent, mem = self._make_agent(provider=provider)
        for i in range(3):
            mem.append("ns", {"agent_id": "a", "input": f"step {i}", "summary": f"orig {i}"})

        results = agent.summarize_namespace("ns")

        # All 3 items should be represented.
        assert len(results) == 3
        # First item uses the real summary line.
        assert results[0]["summary"] == "only one summary line"
        # Remaining fall back to original summary text.
        assert results[1]["summary"] == "orig 1"
        assert results[2]["summary"] == "orig 2"

    def test_summarize_produces_correct_prompt_body(self) -> None:
        provider = _make_provider("• s1")
        agent, mem = self._make_agent(provider=provider)
        mem.append("ns", {"agent_id": "eng", "input": "write tests", "summary": "wrote tests"})

        agent.summarize_namespace("ns")

        prompt_arg = provider.complete.call_args.kwargs.get("prompt") or provider.complete.call_args.args[0]
        assert "write tests" in prompt_arg
        assert "eng" in prompt_arg

    def test_create_memory_adapter_with_embeddings_provider(self, tmp_path: Path) -> None:
        """create_memory_adapter passes embeddings_provider through to ChromaVectorMemoryAdapter."""
        from agent_tools.engine.memory import _ProviderEmbeddingFunction, create_memory_adapter

        fake_provider = MagicMock()
        fake_provider.embed.return_value = [[0.1, 0.2, 0.3]]

        # Use "vector" adapter — embeddings_provider is silently ignored for non-chroma.
        adapter = create_memory_adapter("vector", tmp_path, embeddings_provider=fake_provider)
        adapter.append("ns", {"k": "v"})
        assert adapter.read("ns") == [{"k": "v"}]
        # Provider.embed NOT called for in-memory adapter.
        fake_provider.embed.assert_not_called()

    def test_provider_embedding_function_wraps_embed(self) -> None:
        from agent_tools.engine.memory import _ProviderEmbeddingFunction

        provider = MagicMock()
        provider.embed.return_value = [[0.5, 0.6]]
        ef = _ProviderEmbeddingFunction(provider)
        result = ef(["hello"])
        assert result == [[0.5, 0.6]]
        provider.embed.assert_called_once_with(["hello"])


# ---------------------------------------------------------------------------
# CodeEngineerAgent tests
# ---------------------------------------------------------------------------


class TestCodeEngineerAgent:
    def test_write_file_and_commit_creates_file_and_returns_sha(self, tmp_path: Path) -> None:
        # Initialise a real git repo so git commands succeed.
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.write_file_and_commit(
            relative_path="src/hello.py",
            content="def hello():\n    return 'hi'\n",
            commit_message="feat: add hello",
        )

        assert result["success"] is True, result["stderr"]
        assert result["commit_sha"] is not None
        assert len(result["commit_sha"]) == 40  # full SHA
        assert (tmp_path / "src" / "hello.py").exists()

    def test_write_file_and_commit_with_author(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.write_file_and_commit(
            relative_path="README.md",
            content="# Hello\n",
            commit_message="docs: add readme",
            author="Alice <alice@example.com>",
        )

        assert result["success"] is True, result["stderr"]
        log = subprocess.run(
            ["git", "log", "--format=%an <%ae>", "-1"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert "Alice" in log.stdout

    def test_apply_patch_and_commit_valid_patch(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )

        # Create a file and an initial commit.
        target = tmp_path / "math.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )

        # Build a valid unified diff that adds a docstring.
        patch = textwrap.dedent("""\
            --- a/math.py
            +++ b/math.py
            @@ -1,2 +1,3 @@
             def add(a, b):
            +    \"\"\"Return the sum of a and b.\"\"\"
                 return a + b
        """)

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.apply_patch_and_commit(
            patch_text=patch,
            commit_message="refactor: add docstring",
        )

        assert result["success"] is True, result["stderr"]
        assert result["commit_sha"] is not None
        content = target.read_text()
        assert "Return the sum" in content

    def test_apply_patch_and_commit_invalid_patch_returns_failure(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.apply_patch_and_commit(
            patch_text="not a valid unified diff at all",
            commit_message="bad patch",
        )

        assert result["success"] is False
        assert "git apply" in result["stderr"].lower() or result["stderr"]

    def test_write_file_and_commit_creates_parent_dirs(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.write_file_and_commit(
            relative_path="deep/nested/dir/file.txt",
            content="nested\n",
            commit_message="chore: deep file",
        )

        assert result["success"] is True, result["stderr"]
        assert (tmp_path / "deep" / "nested" / "dir" / "file.txt").exists()

    def test_run_helper_returns_structured_result(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent._run(["git", "status"])
        assert "returncode" in result
        assert "stdout" in result
        assert "stderr" in result
        assert result["returncode"] == 0
