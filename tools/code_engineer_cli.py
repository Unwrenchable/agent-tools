#!/usr/bin/env python3
"""CLI for the Code Engineer agent — validate and apply patches safely.

Supports a ``--dry-run`` flag that validates the patch with
``git apply --check`` without modifying the working tree.

Usage::

    # Validate only:
    python tools/code_engineer_cli.py \\
        --patch-file /path/to/my.patch \\
        --commit-message "feat: add feature" \\
        --dry-run

    # Apply and commit:
    python tools/code_engineer_cli.py \\
        --patch-file /path/to/my.patch \\
        --commit-message "feat: add feature"

    # With author:
    python tools/code_engineer_cli.py \\
        --patch-file /path/to/my.patch \\
        --commit-message "feat: add feature" \\
        --author "Alice <alice@example.com>"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent_tools.agents_impl.code_engineer_agent import CodeEngineerAgent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Code Engineer CLI — validate and apply unified diffs safely.",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=".",
        help="Repo root path (default: current directory)",
    )
    parser.add_argument(
        "--patch-file",
        type=str,
        required=True,
        help="Path to a unified diff file (git diff / git format-patch output)",
    )
    parser.add_argument(
        "--commit-message",
        type=str,
        required=True,
        help="Git commit message",
    )
    parser.add_argument(
        "--author",
        type=str,
        default=None,
        help="Optional commit author in 'Name <email>' format",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate patch but do not apply or commit",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists():
        print(f"error: repo path does not exist: {repo}", file=sys.stderr)
        return 2

    patch_file = Path(args.patch_file)
    if not patch_file.exists():
        print(f"error: patch file not found: {patch_file}", file=sys.stderr)
        return 2

    patch_text = patch_file.read_text(encoding="utf-8")
    agent = CodeEngineerAgent(repo_root=repo)

    result = agent.apply_patch_and_commit(
        patch_text=patch_text,
        commit_message=args.commit_message,
        author=args.author,
        dry_run=args.dry_run,
    )

    if result.get("ok"):
        stage = result.get("stage", "")
        note = result.get("note", "")
        sha = result.get("commit_sha")
        parts = [f"SUCCESS [{stage}]"]
        if sha:
            parts.append(f"commit={sha}")
        if note:
            parts.append(note)
        print(" — ".join(parts))
        return 0
    else:
        stage = result.get("stage", "")
        print(f"FAILED [{stage}]", file=sys.stderr)
        if result.get("stderr"):
            print(result["stderr"], file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
