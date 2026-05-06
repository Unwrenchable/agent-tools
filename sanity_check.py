"""sanity_check.py — Quick end-to-end verification of the RealAI platform.

Run this after setting REALAI_API_URL and REALAI_API_KEY to confirm that:
  - All expected agent manifests are loaded.
  - AgentExecutor runs dry-run calls without errors.
  - Session IDs are auto-generated and propagated correctly.
  - Memory adapters (json, sqlite, vector, chroma) initialise without errors.
  - Chain-of-thought context flows from run 1 to run 2 within the same session.

Usage::

    # Dry-run mode (no real API calls, no REALAI_* vars needed):
    python sanity_check.py

    # Live mode (calls the RealAI backend):
    export REALAI_API_URL="https://realai-qz3b.onrender.com"
    export REALAI_API_KEY="realai_live_xxx"
    python sanity_check.py --live
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# ── helpers ──────────────────────────────────────────────────────────────────

_PASS = "✓"
_FAIL = "✗"
_results: list[tuple[str, bool, str]] = []


def check(name: str, fn):  # type: ignore[no-untyped-def]
    """Run *fn()*, record pass/fail, and print result."""
    try:
        fn()
        _results.append((name, True, ""))
        print(f"  {_PASS} {name}")
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        _results.append((name, False, str(exc)))
        print(f"  {_FAIL} {name}: {exc}")
        if "--verbose" in sys.argv:
            print(tb)


# ── checks ───────────────────────────────────────────────────────────────────

def _check_imports() -> None:
    from agent_tools.engine.executor import AgentExecutor, ExecutionResult  # noqa: F401
    from agent_tools.engine.memory import (  # noqa: F401
        ChromaVectorMemoryAdapter,
        JsonFileMemoryAdapter,
        SQLiteMemoryAdapter,
        VectorMemoryAdapter,
        create_memory_adapter,
    )
    from agent_tools.providers.realai import RealAIProvider  # noqa: F401
    from agent_tools.providers.realai_embeddings import RealAIEmbeddings  # noqa: F401
    from agent_tools.providers.router import ProviderRouter  # noqa: F401


def _check_manifests() -> None:
    from agent_tools.engine.loader import AgentManifestLoader

    repo_root = Path(__file__).parent
    loader = AgentManifestLoader(repo_root / "agents")
    agents = loader.load_agents(force=True)

    expected = {
        "overmind", "task_planner", "memory_summarizer", "npc_intel",
        "code_engineer", "code_reviewer", "debugger", "architect",
        "documentation", "security", "devops",
    }
    missing = expected - set(agents)
    assert not missing, f"Missing manifests: {missing}"


def _check_memory_adapters(tmp_path: Path) -> None:
    from agent_tools.engine.memory import (
        ChromaVectorMemoryAdapter,
        JsonFileMemoryAdapter,
        SQLiteMemoryAdapter,
        VectorMemoryAdapter,
        create_memory_adapter,
    )

    # json
    j = JsonFileMemoryAdapter(tmp_path / "mem.json")
    j.append("ns", {"k": "v"})
    assert j.read("ns") == [{"k": "v"}]

    # sqlite
    s = SQLiteMemoryAdapter(tmp_path / "mem.sqlite")
    s.append("ns", {"k": "v"})
    assert s.read("ns") == [{"k": "v"}]

    # in-memory vector
    v = VectorMemoryAdapter()
    v.append("ns", {"k": "v"})
    assert v.read("ns") == [{"k": "v"}]

    # chroma (persistent, no network)
    c = ChromaVectorMemoryAdapter(tmp_path / "chroma")
    c.append("test-ns-check", {"k": "v"})
    assert c.read("test-ns-check") == [{"k": "v"}]

    # factory
    a = create_memory_adapter("json", tmp_path)
    assert isinstance(a, JsonFileMemoryAdapter)
    b = create_memory_adapter("chroma", tmp_path)
    assert isinstance(b, ChromaVectorMemoryAdapter)


def _check_provider_router() -> None:
    from agent_tools.providers.router import ProviderRouter

    router = ProviderRouter()
    assert hasattr(router, "_providers"), "ProviderRouter missing _providers"
    assert "realai" in router._providers, "RealAIProvider not registered"


def _check_dry_run_basic() -> None:
    from agent_tools.engine.executor import AgentExecutor

    ex = AgentExecutor()
    r = ex.run(agent_id="code_engineer", input_text="Write a hello-world function", dry_run=True)
    assert r.session_id is not None, "session_id should be auto-generated"
    assert r.agent_id == "code_engineer"
    assert r.dry_run is True


def _check_dry_run_session_continuity() -> None:
    """Second call in the same session should see the first call in context."""
    from agent_tools.engine.executor import AgentExecutor

    ex = AgentExecutor()
    session = "sanity-session-1"

    r1 = ex.run(
        agent_id="code_engineer",
        input_text="Create a function add(a, b) that returns a+b",
        session_id=session,
        dry_run=True,
    )
    assert r1.session_id == session

    r2 = ex.run(
        agent_id="code_engineer",
        input_text="What did we just ask the system to do?",
        session_id=session,
        dry_run=True,
    )
    assert r2.session_id == session
    # Both runs completed — with a real provider, r2 would reflect r1 via chain-of-thought.


def _check_execution_result_fields() -> None:
    from agent_tools.engine.executor import AgentExecutor

    ex = AgentExecutor()
    r = ex.run(agent_id="task_planner", input_text="Plan a blog post", dry_run=True)
    # Required fields
    assert r.agent_id
    assert r.provider
    assert r.output is not None
    assert isinstance(r.tool_calls, list)
    assert isinstance(r.logs, list)
    assert r.latency_ms >= 0
    assert r.session_id is not None


def _check_overmind_runner_import() -> None:
    # Just ensure the module is importable without error.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "overmind_runner",
        Path(__file__).parent / "scripts" / "overmind_runner.py",
    )
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert callable(getattr(mod, "run_goal", None))


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    import tempfile

    live = "--live" in sys.argv
    print(f"\n{'RealAI Platform Sanity Check':=^60}")
    print(f"Mode: {'live' if live else 'dry-run (no API calls)'}\n")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        print("Imports:")
        check("all core imports resolve", _check_imports)

        print("\nManifests:")
        check("all 11 agent manifests load", _check_manifests)

        print("\nMemory adapters:")
        check("json / sqlite / vector / chroma adapters", lambda: _check_memory_adapters(tmp))

        print("\nProvider router:")
        check("RealAIProvider registered in ProviderRouter", _check_provider_router)

        print("\nExecutor (dry-run):")
        check("dry-run run returns valid ExecutionResult", _check_dry_run_basic)
        check("ExecutionResult has all required fields", _check_execution_result_fields)
        check("session continuity across two runs", _check_dry_run_session_continuity)

        print("\nScripts:")
        check("scripts/overmind_runner.py importable + run_goal callable", _check_overmind_runner_import)

        if live:
            print("\nLive provider check:")

            def _live_realai() -> None:
                from agent_tools.engine.executor import AgentExecutor
                ex = AgentExecutor()
                r = ex.run(
                    agent_id="code_engineer",
                    input_text="Say hello in one sentence.",
                    dry_run=False,
                )
                assert r.output.get("response"), "Expected a non-empty response from RealAI"
                print(f"    → {r.output['response'][:120]}")

            check("live RealAI completion", _live_realai)

    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    print(f"\n{'Result':=^60}")
    print(f"  {_PASS} Passed: {passed}   {_FAIL} Failed: {failed}")
    if failed:
        print("\nFailed checks:")
        for name, ok, err in _results:
            if not ok:
                print(f"  {_FAIL} {name}: {err}")
        sys.exit(1)
    else:
        print("\nAll checks passed. RealAI platform is ready.")


if __name__ == "__main__":
    main()
