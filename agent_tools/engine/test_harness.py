from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .executor import AgentExecutor
from .loader import AgentManifestLoader


@dataclass(slots=True)
class HarnessSummary:
    total: int
    passed: int
    failed: int


def run_self_tests(repo_root: Path) -> HarnessSummary:
    loader = AgentManifestLoader(repo_root / "agents")
    loader.load_agents(force=True)

    executor = AgentExecutor(repo_root=repo_root, loader=loader)
    test_files = sorted((repo_root / "agents").glob("*/tests/*.json"))

    passed = 0
    failed = 0

    for test_file in test_files:
        raw = json.loads(test_file.read_text(encoding="utf-8"))
        result = executor.run(
            agent_id=raw["agent_id"],
            input_text=raw["input"],
            dry_run=bool(raw.get("dry_run", False)),
        )

        if _assert_result(raw, result):
            passed += 1
        else:
            failed += 1

    return HarnessSummary(total=len(test_files), passed=passed, failed=failed)


def _assert_result(expectation: dict, result: object) -> bool:
    expected_contains = expectation.get("expected_contains")
    if isinstance(expected_contains, str):
        content = str(getattr(result, "output", {}).get("content", ""))
        if expected_contains not in content:
            return False

    expected_tool = expectation.get("expected_tool")
    if isinstance(expected_tool, str):
        tool_names = [entry.get("tool") for entry in getattr(result, "tool_calls", [])]
        if expected_tool not in tool_names:
            return False

    expected_provider = expectation.get("expected_provider")
    if isinstance(expected_provider, str):
        if getattr(result, "provider", "") != expected_provider:
            return False

    return True
