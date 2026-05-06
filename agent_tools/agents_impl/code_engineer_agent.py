"""Code Engineer agent.

Applies unified diffs / patches to the repository and commits them via git.
The implementation is deliberately minimal and safe:

* ``apply_patch_and_commit`` writes the patch to a temp file, runs
  ``git apply --check`` first (pre-check stage), then ``git apply``,
  stages all changes, and commits with the supplied message.
* A ``dry_run=True`` flag stops after the pre-check so callers can
  validate a patch without touching the working tree.
* ``write_file_and_commit`` writes arbitrary text to a file, stages it, and
  commits — useful when the caller already has the final file content.
* Neither method does a ``push``.  Pushing is left to the caller / CI.

Return value convention
-----------------------
All public methods return a dict with:

* ``ok``    — ``True`` on success, ``False`` on any failure.
* ``stage`` — Which stage completed last: ``"precheck"``, ``"dry-run"``,
              ``"apply"``, ``"add"``, or ``"commit"``.
* ``commit_sha`` — Full 40-char SHA on successful commit, else ``None``.
* ``note``  — Optional human-readable note (e.g. "nothing to commit").
* ``stdout`` / ``stderr`` — Raw git output.

Typical usage::

    from pathlib import Path
    from agent_tools.agents_impl.code_engineer_agent import CodeEngineerAgent

    agent = CodeEngineerAgent(repo_root=Path.cwd())

    # Validate without touching the tree:
    r = agent.apply_patch_and_commit(patch_text=diff, commit_message="feat: …", dry_run=True)
    if r["ok"]:
        print("Patch is valid; applying…")
        r = agent.apply_patch_and_commit(patch_text=diff, commit_message="feat: …")
        print("Committed:", r["commit_sha"])
    else:
        print("Patch rejected:", r["stderr"])
"""
from __future__ import annotations

import os
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
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Apply a unified diff and commit the result.

        Steps:

        1. Pre-check: confirms ``git`` is available in PATH.
        2. Writes *patch_text* to a temporary file (cleaned up on exit).
        3. Runs ``git apply --check`` to validate without modifying the tree.
        4. If *dry_run* is ``True``, returns here with ``stage="dry-run"``.
        5. Runs ``git apply`` to apply the patch.
        6. Stages all modified / new files (``git add -A``).
        7. Commits with *commit_message* (and optional *author*).

        Args:
            patch_text:     Unified diff in ``git diff`` / ``git format-patch`` format.
            commit_message: Git commit message.
            author:         Optional ``"Name <email>"`` git author string.
            dry_run:        When ``True``, validate only — do not modify the repo.

        Returns:
            Dict with ``ok``, ``stage``, ``commit_sha``, ``stdout``, ``stderr``,
            and optionally ``note``.
        """
        if not self._check_git_available():
            return {
                "ok": False,
                "stage": "precheck",
                "commit_sha": None,
                "stdout": "",
                "stderr": "git is not available in PATH",
            }

        patch_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(patch_text)
                patch_path = tmp.name

            # Validate first (no-op; does not touch the working tree).
            check = self._run(["git", "apply", "--check", patch_path])
            if check["returncode"] != 0:
                return {
                    "ok": False,
                    "stage": "precheck",
                    "commit_sha": None,
                    "stdout": check["stdout"],
                    "stderr": f"git apply --check failed:\n{check['stderr']}",
                }

            if dry_run:
                return {
                    "ok": True,
                    "stage": "dry-run",
                    "commit_sha": None,
                    "stdout": check["stdout"],
                    "stderr": check["stderr"],
                    "note": "Patch validated; dry-run mode — no changes applied.",
                }

            # Apply for real.
            apply = self._run(["git", "apply", patch_path])
            if apply["returncode"] != 0:
                return {
                    "ok": False,
                    "stage": "apply",
                    "commit_sha": None,
                    "stdout": apply["stdout"],
                    "stderr": f"git apply failed:\n{apply['stderr']}",
                }
        finally:
            if patch_path is not None:
                try:
                    os.unlink(patch_path)
                except OSError:
                    pass

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
        if not self._check_git_available():
            return {
                "ok": False,
                "stage": "precheck",
                "commit_sha": None,
                "stdout": "",
                "stderr": "git is not available in PATH",
            }
        target = self.repo_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return self._stage_and_commit(commit_message=commit_message, author=author)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_git_available(self) -> bool:
        """Return ``True`` if ``git`` is reachable in PATH."""
        result = self._run(["git", "--version"])
        return result["returncode"] == 0

    def _stage_and_commit(
        self,
        commit_message: str,
        author: str | None,
    ) -> dict[str, Any]:
        """Stage all changes (``git add -A``) and commit."""
        add = self._run(["git", "add", "-A"])
        if add["returncode"] != 0:
            return {
                "ok": False,
                "stage": "add",
                "commit_sha": None,
                "stdout": add["stdout"],
                "stderr": f"git add failed:\n{add['stderr']}",
            }

        commit_cmd = ["git", "commit", "-m", commit_message]
        if author:
            commit_cmd += ["--author", author]

        commit = self._run(commit_cmd)
        if commit["returncode"] != 0:
            stderr_lower = commit["stderr"].lower()
            if "nothing to commit" in stderr_lower:
                return {
                    "ok": True,
                    "stage": "commit",
                    "commit_sha": None,
                    "stdout": commit["stdout"],
                    "stderr": commit["stderr"],
                    "note": "nothing to commit",
                }
            return {
                "ok": False,
                "stage": "commit",
                "commit_sha": None,
                "stdout": commit["stdout"],
                "stderr": f"git commit failed:\n{commit['stderr']}",
            }

        # Retrieve the SHA of the just-created commit.
        sha_result = self._run(["git", "rev-parse", "HEAD"])
        sha = sha_result["stdout"].strip() if sha_result["returncode"] == 0 else None

        return {
            "ok": True,
            "stage": "commit",
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
