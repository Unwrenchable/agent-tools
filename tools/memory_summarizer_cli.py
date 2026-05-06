#!/usr/bin/env python3
"""CLI wrapper for the Memory Summarizer agent.

Reads recent items from a session-scoped global namespace, calls RealAI to
compress them into bullet summaries, and writes results back into memory.

Usage::

    python tools/memory_summarizer_cli.py --session my-session-id
    python tools/memory_summarizer_cli.py --session my-session-id --repo /path/to/repo --limit 100
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running directly as a script without installing the package.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent_tools.agents_impl.memory_summarizer_agent import MemorySummarizerAgent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Memory Summarizer for a session namespace.",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=".",
        help="Repo root path (default: current directory)",
    )
    parser.add_argument(
        "--session",
        type=str,
        required=True,
        help="Session ID to summarise (e.g. 'session-123')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum number of items to read before summarising (default: 200)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Call the LLM in dry-run mode (no real API call; useful for testing)",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists():
        print(f"error: repo path does not exist: {repo}", file=sys.stderr)
        return 2

    # Try to build an embeddings provider; fall back to None if env vars are missing.
    embeddings_provider = None
    try:
        from agent_tools.providers.realai_embeddings import RealAIEmbeddings
        embeddings_provider = RealAIEmbeddings()
    except (RuntimeError, ImportError):
        pass

    summarizer = MemorySummarizerAgent(
        repo_root=repo,
        embeddings_provider=embeddings_provider,
    )
    ns = f"{args.session}:global"
    summaries = summarizer.summarize_namespace(ns, max_items=args.limit, dry_run=args.dry_run)

    if not summaries:
        print(f"No items found in namespace '{ns}'.")
        return 0

    for s in summaries:
        orig = s.get("original", {})
        summary_text = s.get("summary", "")
        print(f"- agent={orig.get('agent_id')}  input={orig.get('input')}")
        print(f"  summary: {summary_text}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
