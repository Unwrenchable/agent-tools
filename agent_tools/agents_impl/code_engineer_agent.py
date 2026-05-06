"""Code Engineer agent.

Applies unified diffs / patches to the repository and commits them via git.
The implementation is deliberately minimal and safe:

* ``apply_patch_and_commit`` writes the patch to a temp file, runs
  ``git apply --check`` first, then ``git apply``, stages all changes, and
  commits with the supplied message.
* ``write_file_and_commit`` writes arbitrary text to a file, stages it, and
  commits — useful when the caller already has the final file content.
* Neither method does a ``push``.  Pushing is left to the caller / CI.

Typical usage::

    from pathlib import Path
    from agent_tools.agents_impl.code_engineer_agent import CodeEngineerAgent

    agent = CodeEngineerAgent(repo_root=Path.cwd())

    result = agent.apply_patch_and_commit(
        patch_text=my_unified_diff,
        commit_message="feat: add add() function",
    )
    if result["success"]:
        print("Committed:", result["commit_sha"])
    else:
        print("Failed:", result["stderr"])
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any


class CodeEngineerAgent:
    """Applies unified diffs and writes files, then commits via git.

    Args:
        repo_root: Absolute path to the repository root.  All git commands
                   run with this as the working directory.
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_patch_and_commit(
        self,
        patch_text: str,
        commit_message: str,
        author: str | None = None,
    ) -> dict[str, Any]:
        """Apply a unified diff and commit the result.

        The method:

        1. Writes *patch_text* to a temporary file.
        2. Runs ``git apply --check`` to validate without modifying the tree.
        3. Runs ``git apply`` to apply the patch.
        4. Stages all modified / new files (``git add -A``).
        5. Commits with *commit_message* (and optional *author*).

        Args:
            patch_text:     Unified diff in ``git diff`` format.
            commit_message: Git commit message.
            author:         Optional ``"Name <email>"`` git author string.

        Returns:
            A dict with keys:

            * ``success`` (bool)
            * ``commit_sha`` (str | None) — SHA of the new commit on success.
            * ``stdout`` (str)
            * ``stderr`` (str)
        """
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(patch_text)
            patch_path = tmp.name

        # Validate first (no-op).
        check = self._run(["git", "apply", "--check", patch_path])
        if check["returncode"] != 0:
            return {
                "success": False,
                "commit_sha": None,
                "stdout": check["stdout"],
                "stderr": f"git apply --check failed:\n{check['stderr']}",
            }

        # Apply for real.
        apply = self._run(["git", "apply", patch_path])
        if apply["returncode"] != 0:
            return {
                "success": False,
                "commit_sha": None,
                "stdout": apply["stdout"],
                "stderr": f"git apply failed:\n{apply['stderr']}",
            }

        return self._stage_and_commit(commit_message=commit_message, author=author)

    def write_file_and_commit(
        self,
        relative_path: str,
        content: str,
        commit_message: str,
        author: str | None = None,
    ) -> dict[str, Any]:
        """Write *content* to *relative_path* inside the repo and commit.

        Parent directories are created automatically.

        Args:
            relative_path:  Path relative to ``repo_root`` (e.g. ``"src/foo.py"``).
            content:        Full text content to write.
            commit_message: Git commit message.
            author:         Optional ``"Name <email>"`` git author string.

        Returns:
            Same structure as :meth:`apply_patch_and_commit`.
        """
        target = self.repo_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return self._stage_and_commit(commit_message=commit_message, author=author)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _stage_and_commit(
        self,
        commit_message: str,
        author: str | None,
    ) -> dict[str, Any]:
        """Stage all changes (``git add -A``) and commit."""
        add = self._run(["git", "add", "-A"])
        if add["returncode"] != 0:
            return {
                "success": False,
                "commit_sha": None,
                "stdout": add["stdout"],
                "stderr": f"git add failed:\n{add['stderr']}",
            }

        commit_cmd = ["git", "commit", "-m", commit_message]
        if author:
            commit_cmd += ["--author", author]

        commit = self._run(commit_cmd)
        if commit["returncode"] != 0:
            return {
                "success": False,
                "commit_sha": None,
                "stdout": commit["stdout"],
                "stderr": f"git commit failed:\n{commit['stderr']}",
            }

        # Retrieve the SHA of the just-created commit.
        sha_result = self._run(["git", "rev-parse", "HEAD"])
        sha = sha_result["stdout"].strip() if sha_result["returncode"] == 0 else None

        return {
            "success": True,
            "commit_sha": sha,
            "stdout": commit["stdout"],
            "stderr": commit["stderr"],
        }

    def _run(self, cmd: list[str]) -> dict[str, Any]:
        """Run *cmd* in ``repo_root`` and return returncode/stdout/stderr."""
        proc = subprocess.run(
            cmd,
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
