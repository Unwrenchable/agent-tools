from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry pushing agentx rollout branches and opening PRs")
    parser.add_argument("--summary", default="/tmp/agentx_rollout_summary.json", help="Rollout summary path")
    parser.add_argument("--workdir", default="/tmp/agentx-rollout", help="Local clone directory")
    args = parser.parse_args()

    summary_path = Path(args.summary)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    branch = summary["branch"]

    retry_repos = [r["repo"] for r in summary["results"] if r["status"] == "failed"]
    results: list[dict[str, str]] = []

    for name_with_owner in retry_repos:
        repo_name = name_with_owner.split("/", 1)[1]
        local_path = Path(args.workdir) / repo_name
        try:
            default_branch = run(
                [
                    "gh",
                    "repo",
                    "view",
                    name_with_owner,
                    "--json",
                    "defaultBranchRef",
                ]
            )
            default_branch_name = json.loads(default_branch)["defaultBranchRef"]["name"]

            run(["git", "push", "-u", "origin", branch], cwd=local_path)
            pr_url = run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    name_with_owner,
                    "--base",
                    default_branch_name,
                    "--head",
                    branch,
                    "--title",
                    "feat: add AgentX custom agent toolkit",
                    "--body",
                    "Adds `.agentx` custom agent toolkit pack with capability profiles.",
                ]
            )
            results.append({"repo": name_with_owner, "status": "pr_opened", "pr_url": pr_url})
        except Exception as exc:
            results.append({"repo": name_with_owner, "status": "failed", "message": str(exc)})

    print(json.dumps({"retried": len(retry_repos), "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
