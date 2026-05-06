"""Unit tests for CodeEngineerAgent — dry-run, apply, and write-file paths."""
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
    """Initialise a bare git repo with a user identity configured."""
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "ci@test.com"],
        cwd=str(path), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CI"],
        cwd=str(path), check=True, capture_output=True,
    )


def _commit_file(path: Path, filename: str, content: str, message: str = "initial") -> None:
    (path / filename).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(path), check=True, capture_output=True,
    )


# ---------------------------------------------------------------------------
# apply_patch_and_commit — dry-run
# ---------------------------------------------------------------------------


class TestApplyPatchDryRun:
    def test_valid_patch_dry_run_returns_ok_and_no_commit(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit_file(tmp_path, "README.md", "Old line\n")

        # Build a real unified diff
        patch = textwrap.dedent("""\
            --- a/README.md
            +++ b/README.md
            @@ -1 +1 @@
            -Old line
            +New line
        """)

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.apply_patch_and_commit(
            patch_text=patch, commit_message="test", dry_run=True
        )

        assert result["ok"] is True
        assert result["stage"] == "dry-run"
        assert result["commit_sha"] is None
        # File must remain unchanged.
        assert (tmp_path / "README.md").read_text() == "Old line\n"

    def test_invalid_patch_dry_run_returns_failure(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.apply_patch_and_commit(
            patch_text="not a patch", commit_message="test", dry_run=True
        )

        assert result["ok"] is False
        assert result["stage"] == "precheck"
        assert result["stderr"]


# ---------------------------------------------------------------------------
# apply_patch_and_commit — real apply
# ---------------------------------------------------------------------------


class TestApplyPatchReal:
    def test_valid_patch_applies_and_commits(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit_file(tmp_path, "math.py", "def add(a, b):\n    return a + b\n")

        patch = textwrap.dedent("""\
            --- a/math.py
            +++ b/math.py
            @@ -1,2 +1,3 @@
             def add(a, b):
            +    \"\"\"Return a + b.\"\"\"
                 return a + b
        """)

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.apply_patch_and_commit(patch_text=patch, commit_message="refactor: docstring")

        assert result["ok"] is True, result["stderr"]
        assert result["stage"] == "commit"
        assert result["commit_sha"] and len(result["commit_sha"]) == 40
        assert "Return a + b" in (tmp_path / "math.py").read_text()

    def test_invalid_patch_returns_failure(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.apply_patch_and_commit(
            patch_text="garbage", commit_message="should fail"
        )

        assert result["ok"] is False
        assert result["stderr"]

    def test_temp_file_is_cleaned_up(self, tmp_path: Path) -> None:
        """Temporary patch files should not remain after apply_patch_and_commit."""
        import glob
        import tempfile

        _init_repo(tmp_path)
        _commit_file(tmp_path, "a.txt", "hello\n")

        patch = textwrap.dedent("""\
            --- a/a.txt
            +++ b/a.txt
            @@ -1 +1 @@
            -hello
            +world
        """)

        before = set(glob.glob(f"{tempfile.gettempdir()}/*.patch"))
        agent = CodeEngineerAgent(repo_root=tmp_path)
        agent.apply_patch_and_commit(patch_text=patch, commit_message="clean")
        after = set(glob.glob(f"{tempfile.gettempdir()}/*.patch"))

        # No new .patch files should remain.
        assert after.issubset(before), f"Leaked temp files: {after - before}"

    def test_author_is_recorded_in_commit(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit_file(tmp_path, "f.txt", "x\n")

        patch = textwrap.dedent("""\
            --- a/f.txt
            +++ b/f.txt
            @@ -1 +1 @@
            -x
            +y
        """)

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.apply_patch_and_commit(
            patch_text=patch,
            commit_message="chore",
            author="Bob <bob@example.com>",
        )

        assert result["ok"] is True, result["stderr"]
        log = subprocess.run(
            ["git", "log", "--format=%an <%ae>", "-1"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert "Bob" in log.stdout


# ---------------------------------------------------------------------------
# write_file_and_commit
# ---------------------------------------------------------------------------


class TestWriteFileAndCommit:
    def test_creates_file_and_returns_sha(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.write_file_and_commit(
            relative_path="src/util.py",
            content="def noop(): pass\n",
            commit_message="feat: add noop",
        )

        assert result["ok"] is True, result["stderr"]
        assert result["commit_sha"] and len(result["commit_sha"]) == 40
        assert (tmp_path / "src" / "util.py").exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.write_file_and_commit(
            relative_path="a/b/c/d.txt",
            content="deep\n",
            commit_message="chore: deep",
        )

        assert result["ok"] is True, result["stderr"]
        assert (tmp_path / "a" / "b" / "c" / "d.txt").exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _commit_file(tmp_path, "notes.txt", "original\n")

        agent = CodeEngineerAgent(repo_root=tmp_path)
        result = agent.write_file_and_commit(
            relative_path="notes.txt",
            content="updated\n",
            commit_message="update notes",
        )

        assert result["ok"] is True, result["stderr"]
        assert (tmp_path / "notes.txt").read_text() == "updated\n"


# ---------------------------------------------------------------------------
# _run helper
# ---------------------------------------------------------------------------


class TestRunHelper:
    def test_returns_structured_dict(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        agent = CodeEngineerAgent(repo_root=tmp_path)
        r = agent._run(["git", "status"])
        assert r["returncode"] == 0
        assert isinstance(r["stdout"], str)
        assert isinstance(r["stderr"], str)

    def test_nonzero_returncode_on_bad_command(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        agent = CodeEngineerAgent(repo_root=tmp_path)
        r = agent._run(["git", "log", "--no-such-flag"])
        assert r["returncode"] != 0


# ---------------------------------------------------------------------------
# pre-check
# ---------------------------------------------------------------------------


class TestGitAvailableCheck:
    def test_check_git_available_returns_true(self, tmp_path: Path) -> None:
        agent = CodeEngineerAgent(repo_root=tmp_path)
        assert agent._check_git_available() is True
