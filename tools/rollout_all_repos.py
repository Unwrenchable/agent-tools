from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import asdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from agent_tools.importer import import_agency_agents


ROOT = Path(__file__).resolve().parents[1]
BASE_AGENTS_PATH = ROOT / "agent_tools" / "data" / "agents.json"
BASE_PROFILES_PATH = ROOT / "agent_tools" / "data" / "access_profiles.json"


@dataclass(slots=True)
class RepoResult:
    repo: str
    status: str
    pr_url: str = ""
    message: str = ""


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> str:
    process = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if check and process.returncode != 0:
        raise RuntimeError(
            f"Command failed ({process.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{process.stdout}\n"
            f"stderr:\n{process.stderr}"
        )
    return process.stdout.strip()


def load_json(path: Path) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"Expected JSON list in {path}")
    return value


def write_json(path: Path, payload: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    return "-".join(part for part in "".join(c if c.isalnum() else "-" for c in value.lower()).split("-") if part)


def detect_stack_tags(repo_path: Path) -> list[str]:
    tags: set[str] = set()
    if (repo_path / "package.json").exists():
        tags.update(["node", "javascript"])
    if (repo_path / "pyproject.toml").exists() or (repo_path / "requirements.txt").exists():
        tags.update(["python"])
    if (repo_path / "go.mod").exists():
        tags.update(["go"])
    if (repo_path / "Cargo.toml").exists():
        tags.update(["rust"])
    if (repo_path / "Dockerfile").exists() or (repo_path / "docker-compose.yml").exists():
        tags.update(["containers"])
    if (repo_path / ".github" / "workflows").exists():
        tags.update(["ci-cd"])
    if (repo_path / "next.config.js").exists() or (repo_path / "next.config.ts").exists():
        tags.add("nextjs")
    if (repo_path / "tailwind.config.js").exists() or (repo_path / "tailwind.config.ts").exists():
        tags.add("tailwind")
    if (repo_path / "prisma").is_dir():
        tags.add("prisma")
    if any((repo_path / d).is_dir() for d in ("terraform", "infra", "infrastructure")):
        tags.add("infrastructure")
    if any((repo_path / d).is_dir() for d in ("kubernetes", "k8s", "helm")):
        tags.add("kubernetes")
    if not tags:
        tags.add("general")
    return sorted(tags)


def build_custom_agents(repo_name: str, tags: list[str]) -> list[dict]:
    base_id = slugify(repo_name)
    tag_set = set(tags)
    agents = [
        {
            "id": f"{base_id}-repo-architect",
            "role": f"{repo_name} Repository Architect",
            "description": "Maintains architecture consistency and coordinates upgrades for this repository.",
            "tags": [repo_name, *tags, "architecture", "planning"],
            "capabilities": ["roadmap-alignment", "upgrade-planning", "dependency-review"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search"],
            "preferred_profile": "safe",
            "risk_level": "low",
        },
        {
            "id": f"{base_id}-implementation-pilot",
            "role": f"{repo_name} Implementation Pilot",
            "description": "Executes scoped code changes with validation and release hygiene.",
            "tags": [repo_name, *tags, "implementation", "quality"],
            "capabilities": ["code-changes", "refactoring", "test-validation"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
            "preferred_profile": "balanced",
            "risk_level": "medium",
        },
        {
            "id": f"{base_id}-orchestrator",
            "role": f"{repo_name} Multi-Agent Orchestrator",
            "description": "Coordinates planning, implementation, and verification agents for this repository.",
            "tags": [repo_name, *tags, "orchestration", "multi-agent"],
            "capabilities": ["task-routing", "handoffs", "delivery-status"],
            "required_tools": ["read_file", "list_dir", "runSubagent", "github_repo"],
            "preferred_profile": "power",
            "risk_level": "medium",
        },
        {
            "id": f"{base_id}-qa-pilot",
            "role": f"{repo_name} QA Pilot",
            "description": "Plans and runs unit, integration, and end-to-end tests to ensure shipping quality for this repository.",
            "tags": [repo_name, *tags, "testing", "quality"],
            "capabilities": ["test-planning", "unit-testing", "integration-testing", "e2e-testing", "coverage-reporting"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
            "preferred_profile": "balanced",
            "risk_level": "medium",
        },
    ]

    # Add a DevOps pilot for repos with CI/CD, containers, or infrastructure
    if tag_set & {"ci-cd", "containers", "kubernetes", "infrastructure"}:
        agents.append(
            {
                "id": f"{base_id}-devops-pilot",
                "role": f"{repo_name} DevOps Pilot",
                "description": "Manages CI/CD pipelines, container builds, and deployment workflows for this repository.",
                "tags": [repo_name, *tags, "devops", "deployment"],
                "capabilities": ["pipeline-configuration", "container-management", "release-automation", "monitoring-setup"],
                "required_tools": ["read_file", "list_dir", "grep_search", "apply_patch", "create_file", "run_in_terminal", "github_repo"],
                "preferred_profile": "power",
                "risk_level": "medium",
            }
        )

    return agents


def write_agentx_pack(repo_path: Path, repo_name: str, base_agents: list[dict], profiles: list[dict], agency_agents: list[dict]) -> None:
    tags = detect_stack_tags(repo_path)
    custom_agents = build_custom_agents(repo_name, tags)

    merged: dict[str, dict] = {}
    for group in (base_agents, agency_agents, custom_agents):
        for agent in group:
            merged[str(agent["id"])] = agent

    agentx_dir = repo_path / ".agentx"
    agentx_dir.mkdir(parents=True, exist_ok=True)

    write_json(agentx_dir / "agents.json", sorted(merged.values(), key=lambda item: str(item["id"])))
    write_json(agentx_dir / "access_profiles.json", profiles)
    write_json(agentx_dir / "agency_import.json", agency_agents)

    readme = f"""# AgentX Pack for {repo_name}

This repository is upgraded with AgentX capabilities for full-stack development and deployment.

## Included
- `agents.json`: merged core + imported + custom per-repo agents
- `access_profiles.json`: safe/balanced/power profiles
- `agency_import.json`: imported agents from agency-agents

## Per-Repo Agents
| Agent | Profile | Purpose |
|-------|---------|---------|
| `{slugify(repo_name)}-repo-architect` | safe | Architecture planning and dependency review |
| `{slugify(repo_name)}-implementation-pilot` | balanced | Code changes, refactoring, test validation |
| `{slugify(repo_name)}-orchestrator` | power | Multi-agent coordination and handoffs |
| `{slugify(repo_name)}-qa-pilot` | balanced | Test planning, unit/integration/e2e tests |
| `{slugify(repo_name)}-devops-pilot` | power | CI/CD pipelines, containers, deployments |

> **Note:** The `devops-pilot` agent is only generated for repositories that contain CI/CD
> workflows, container configuration, Kubernetes manifests, or infrastructure-as-code.

## Suggested commands
```bash
agentx find {repo_name}
agentx check {slugify(repo_name)}-implementation-pilot --profile balanced
agentx check {slugify(repo_name)}-orchestrator --profile power
agentx check {slugify(repo_name)}-qa-pilot --profile balanced
```
"""
    (agentx_dir / "README.md").write_text(readme, encoding="utf-8")


def get_repos(owner: str, limit: int) -> list[dict]:
    payload = run(
        [
            "gh",
            "repo",
            "list",
            owner,
            "--limit",
            str(limit),
            "--json",
            "nameWithOwner,isPrivate,url,defaultBranchRef,isArchived",
        ]
    )
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("Unexpected GitHub response")
    return data


def upgrade_repo(workdir: Path, repo: dict, branch: str, base_agents: list[dict], profiles: list[dict], agency_agents: list[dict], dry_run: bool) -> RepoResult:
    name_with_owner = str(repo["nameWithOwner"])
    repo_name = name_with_owner.split("/", 1)[1]
    default_branch = (repo.get("defaultBranchRef") or {}).get("name") or "main"
    local_path = workdir / repo_name

    try:
        if local_path.exists():
            shutil.rmtree(local_path)

        run(["git", "clone", f"https://github.com/{name_with_owner}.git", str(local_path)])
        run(["git", "checkout", "-B", branch], cwd=local_path)

        write_agentx_pack(local_path, repo_name, base_agents, profiles, agency_agents)

        status = run(["git", "status", "--porcelain"], cwd=local_path)
        if not status:
            return RepoResult(repo=name_with_owner, status="no_changes", message="Nothing to commit")

        if dry_run:
            return RepoResult(repo=name_with_owner, status="dry_run", message="Changes prepared locally")

        run(["git", "add", ".agentx"], cwd=local_path)
        run(
            [
                "git",
                "commit",
                "-m",
                "feat(agentx): add custom agent pack with capability profiles",
            ],
            cwd=local_path,
        )
        run(["git", "push", "-u", "origin", branch], cwd=local_path)

        body = (
            "Adds `.agentx` pack with:\n"
            "- merged agent registry (core + agency import + repo-custom agents)\n"
            "- access profiles for capability governance\n"
            "- usage docs for quick agent checks\n"
        )
        pr_url = run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                name_with_owner,
                "--base",
                default_branch,
                "--head",
                branch,
                "--title",
                "feat: add AgentX custom agent toolkit",
                "--body",
                body,
            ]
        )
        return RepoResult(repo=name_with_owner, status="pr_opened", pr_url=pr_url)
    except Exception as exc:
        return RepoResult(repo=name_with_owner, status="failed", message=str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description="Roll out AgentX toolkit to all repos for an owner")
    parser.add_argument("--owner", required=True, help="GitHub owner/org")
    parser.add_argument("--limit", type=int, default=200, help="Max number of repos")
    parser.add_argument("--workdir", default="/tmp/agentx-rollout", help="Local workspace for cloning repos")
    parser.add_argument("--branch", default=f"agentx-upgrade-{date.today().isoformat()}", help="Branch name")
    parser.add_argument("--dry-run", action="store_true", help="Prepare changes without commit/push/PR")
    parser.add_argument(
        "--agency-source",
        default="/tmp/agency-agents",
        help="Path to agency-agents repo clone",
    )
    args = parser.parse_args()

    run(["gh", "auth", "status"])

    agency_source = Path(args.agency_source)
    if not agency_source.exists():
        run(["git", "clone", "--depth", "1", "https://github.com/msitarzewski/agency-agents.git", str(agency_source)])

    repos = [r for r in get_repos(args.owner, args.limit) if not bool(r.get("isArchived"))]
    base_agents = load_json(BASE_AGENTS_PATH)
    profiles = load_json(BASE_PROFILES_PATH)
    agency_agents = import_agency_agents(str(agency_source))

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    results: list[RepoResult] = []
    for repo in repos:
        results.append(
            upgrade_repo(
                workdir=workdir,
                repo=repo,
                branch=args.branch,
                base_agents=base_agents,
                profiles=profiles,
                agency_agents=agency_agents,
                dry_run=args.dry_run,
            )
        )

    summary = {
        "owner": args.owner,
        "branch": args.branch,
        "dry_run": args.dry_run,
        "total": len(results),
        "pr_opened": len([r for r in results if r.status == "pr_opened"]),
        "dry_run_ready": len([r for r in results if r.status == "dry_run"]),
        "no_changes": len([r for r in results if r.status == "no_changes"]),
        "failed": len([r for r in results if r.status == "failed"]),
        "results": [asdict(r) for r in results],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
