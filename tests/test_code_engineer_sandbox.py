"""Unit tests for CodeEngineerAgent sandbox methods.

Tests gracefully handle the case where Docker is not installed —
``apply_patch_and_commit_sandbox`` and ``run_tests_in_sandbox`` must
return ``{"ok": False, …}`` rather than raise an exception.
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from agent_tools.agents_impl.code_engineer_agent import CodeEngineerAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "ci@test.com"],
        cwd=str(path), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CI"],
        cwd=str(path), check=True, capture_output=True,
    )


def _commit_file(path: Path, filename: str, content: str) -> None:
    (path / filename).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(path), check=True, capture_output=True,
    )


def _docker_available() -> bool:
    try:
        r = subprocess.run(
            ["docker", "--version"], capture_output=True, timeout=5
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# run_tests_in_sandbox
# ---------------------------------------------------------------------------


class TestRunTestsInSandbox:
    def test_returns_dict_always(self, tmp_path: Path) -> None:
        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.run_tests_in_sandbox(image="nonexistent-image:test")
        assert isinstance(result, dict)
        assert "ok" in result

    def test_graceful_failure_when_docker_missing(self, tmp_path: Path) -> None:
        """If docker is not available the method must return ok=False, not raise."""
        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.run_tests_in_sandbox(image="any-image:latest")
        if not _docker_available():
            assert result["ok"] is False
            assert result["stderr"]
        else:
            # Docker is present but image is missing → still fails gracefully.
            assert isinstance(result.get("ok"), bool)

    def test_stage_is_tests(self, tmp_path: Path) -> None:
        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.run_tests_in_sandbox(image="nonexistent-image:test")
        assert result.get("stage") == "tests"

    def test_result_has_stdout_and_stderr_keys(self, tmp_path: Path) -> None:
        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.run_tests_in_sandbox(image="nonexistent-image:test")
        assert "stdout" in result
        assert "stderr" in result


# ---------------------------------------------------------------------------
# apply_patch_and_commit_sandbox
# ---------------------------------------------------------------------------


class TestApplyPatchSandbox:
    def test_returns_dict_always(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit_file(tmp_path, "README.md", "hello\n")
        agent = CodeEngineerAgent(repo_root=tmp_path)

        patch = textwrap.dedent("""\
            --- a/README.md
            +++ b/README.md
            @@ -1 +1 @@
            -hello
            +world
        """)
        result = agent.apply_patch_and_commit_sandbox(
            patch_text=patch,
            commit_message="update",
            image="nonexistent-image:test",
        )
        assert isinstance(result, dict)
        assert "ok" in result

    def test_graceful_failure_when_docker_missing(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit_file(tmp_path, "f.txt", "a\n")
        agent = CodeEngineerAgent(repo_root=tmp_path)

        patch = textwrap.dedent("""\
            --- a/f.txt
            +++ b/f.txt
            @@ -1 +1 @@
            -a
            +b
        """)
        result = agent.apply_patch_and_commit_sandbox(
            patch_text=patch,
            commit_message="test",
            image="nonexistent-image:test",
        )
        if not _docker_available():
            assert result["ok"] is False
            assert result.get("stderr")
        else:
            assert isinstance(result.get("ok"), bool)

    def test_stage_is_sandbox_on_failure(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        agent = CodeEngineerAgent(repo_root=tmp_path)

        result = agent.apply_patch_and_commit_sandbox(
            patch_text="not a patch",
            commit_message="fail",
            image="nonexistent-image:test",
        )
        if not _docker_available():
            assert result.get("stage") == "sandbox"

    def test_temp_file_cleaned_up(self, tmp_path: Path) -> None:
        """Temporary patch file must not persist after the sandbox call."""
        import glob
        import tempfile

        _init_repo(tmp_path)
        agent = CodeEngineerAgent(repo_root=tmp_path)

        before = set(glob.glob(f"{tempfile.gettempdir()}/*.patch"))
        agent.apply_patch_and_commit_sandbox(
            patch_text="not a patch",
            commit_message="cleanup test",
            image="nonexistent-image:test",
        )
        after = set(glob.glob(f"{tempfile.gettempdir()}/*.patch"))
        assert after.issubset(before), f"Leaked temp files: {after - before}"
