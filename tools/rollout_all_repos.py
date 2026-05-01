from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Ensure tools/ is on sys.path so _shared is importable whether this script is
# invoked directly ("python tools/rollout_all_repos.py") or as a module.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import run  # noqa: E402

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
    # JavaScript / Node — read package.json once for both existence and content checks
    pkg_json_path = repo_path / "package.json"
    if pkg_json_path.exists():
        tags.update(["node", "javascript"])
        try:
            pkg = json.loads(pkg_json_path.read_text(encoding="utf-8"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "@pump-fun/agent-payments-sdk" in deps or any(
                k.startswith("@solana/") for k in deps
            ):
                tags.add("solana")
        except (json.JSONDecodeError, OSError):
            pass
    # Python
    if (repo_path / "pyproject.toml").exists() or (repo_path / "requirements.txt").exists():
        tags.update(["python"])
    # Go
    if (repo_path / "go.mod").exists():
        tags.update(["go"])
    # Rust
    if (repo_path / "Cargo.toml").exists():
        tags.update(["rust"])
    # Ruby
    if (repo_path / "Gemfile").exists():
        tags.update(["ruby"])
    # Java / Kotlin (Maven or Gradle)
    if (repo_path / "pom.xml").exists() or (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
        tags.update(["jvm"])
    # .NET / C#
    if any(repo_path.glob("*.csproj")) or any(repo_path.glob("*.sln")):
        tags.update(["dotnet"])
    # PHP
    if (repo_path / "composer.json").exists():
        tags.update(["php"])
    # Swift / iOS
    if (repo_path / "Package.swift").exists() or any(repo_path.glob("*.xcodeproj")):
        tags.update(["swift"])
    # Containers
    if (repo_path / "Dockerfile").exists() or (repo_path / "docker-compose.yml").exists():
        tags.update(["containers"])
    # CI/CD
    if (repo_path / ".github" / "workflows").exists():
        tags.update(["ci-cd"])
    # Next.js
    if (repo_path / "next.config.js").exists() or (repo_path / "next.config.ts").exists():
        tags.add("nextjs")
    # Tailwind CSS
    if (repo_path / "tailwind.config.js").exists() or (repo_path / "tailwind.config.ts").exists():
        tags.add("tailwind")
    # Prisma ORM
    if (repo_path / "prisma").is_dir():
        tags.add("prisma")
    # Infrastructure as Code
    if any((repo_path / d).is_dir() for d in ("terraform", "infra", "infrastructure")):
        tags.add("infrastructure")
    # Kubernetes
    if any((repo_path / d).is_dir() for d in ("kubernetes", "k8s", "helm")):
        tags.add("kubernetes")
    # Database migrations
    if any((repo_path / d).is_dir() for d in ("migrations", "db", "database", "schema")):
        tags.add("database")
    # Documentation
    if any((repo_path / d).is_dir() for d in ("docs", "doc", "documentation")):
        tags.add("documentation")
    # Browser testing frameworks
    if (
        any(repo_path.glob("playwright.config.*"))
        or (repo_path / "cypress").is_dir()
        or any(repo_path.glob("cypress.config.*"))
    ):
        tags.add("browser-testing")
    # Game engines
    if (repo_path / "project.godot").exists():
        tags.update(["game", "godot"])
    if any(repo_path.glob("*.uproject")):
        tags.update(["game", "unreal"])
    if (repo_path / "Assets").is_dir() and (repo_path / "ProjectSettings").is_dir():
        tags.update(["game", "unity"])
    # Generic game project indicators (design docs, gameplay source dirs, asset dirs)
    if (repo_path / "design").is_dir():
        if any((repo_path / d).is_dir() for d in ("src", "assets", "prototypes", "production")):
            tags.add("game")
    if any((repo_path / "src" / sub).is_dir() for sub in ("gameplay", "core", "ai", "networking")):
        tags.add("game")
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
            "description": (
                f"Maintains architecture consistency and coordinates upgrades for {repo_name}. "
                "Produces ADRs, tracks dependency health, flags breaking changes, and ensures "
                "the codebase evolves in a deliberate, well-documented direction."
            ),
            "tags": [repo_name, *tags, "architecture", "planning"],
            "capabilities": ["roadmap-alignment", "upgrade-planning", "dependency-review", "adr-authoring", "breaking-change-detection"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search"],
            "preferred_profile": "safe",
            "risk_level": "low",
        },
        {
            "id": f"{base_id}-implementation-pilot",
            "role": f"{repo_name} Implementation Pilot",
            "description": (
                f"Executes scoped code changes with validation and release hygiene for {repo_name}. "
                "Validates each change with targeted tests, enforces code-style consistency, and "
                "ensures CI gates pass before marking work complete."
            ),
            "tags": [repo_name, *tags, "implementation", "quality"],
            "capabilities": ["code-changes", "refactoring", "test-validation", "style-enforcement", "ci-gate-compliance"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
            "preferred_profile": "balanced",
            "risk_level": "medium",
        },
        {
            "id": f"{base_id}-orchestrator",
            "role": f"{repo_name} Multi-Agent Orchestrator",
            "description": (
                f"Coordinates planning, implementation, and verification agents for {repo_name}. "
                "Breaks features into sub-tasks, routes work to the right specialist, tracks delivery "
                "status, and resolves blockers to keep releases on schedule."
            ),
            "tags": [repo_name, *tags, "orchestration", "multi-agent"],
            "capabilities": ["task-routing", "handoffs", "delivery-status", "blocker-resolution", "release-coordination"],
            "required_tools": ["read_file", "list_dir", "runSubagent", "github_repo"],
            "preferred_profile": "power",
            "risk_level": "medium",
        },
        {
            "id": f"{base_id}-qa-pilot",
            "role": f"{repo_name} QA Pilot",
            "description": (
                f"Plans and runs unit, integration, and end-to-end tests for {repo_name}. "
                "Defines coverage targets, maintains CI test gates, authors test fixtures, "
                "and drives regression-prevention culture across the team."
            ),
            "tags": [repo_name, *tags, "testing", "quality"],
            "capabilities": ["test-planning", "unit-testing", "integration-testing", "e2e-testing", "coverage-reporting", "regression-prevention"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
            "preferred_profile": "balanced",
            "risk_level": "medium",
        },
        {
            "id": f"{base_id}-security-hardener",
            "role": f"{repo_name} Security Hardener",
            "description": (
                f"Performs OWASP Top-10 reviews, dependency CVE triage, and secrets hygiene audits "
                f"for {repo_name}. Applies targeted remediations, enforces secure-by-default patterns, "
                "and documents residual risk with a clear remediation roadmap."
            ),
            "tags": [repo_name, *tags, "security", "vulnerability", "remediation"],
            "capabilities": ["vulnerability-scanning", "cve-triage", "secrets-audit", "secure-code-review", "security-remediation", "risk-reporting"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
            "preferred_profile": "balanced",
            "risk_level": "medium",
        },
        {
            "id": f"{base_id}-documentation-pilot",
            "role": f"{repo_name} Documentation Pilot",
            "description": (
                f"Produces and maintains living documentation for {repo_name}: README files, "
                "architecture decision records (ADRs), API reference docs, runbooks, and onboarding "
                "guides. Keeps docs in sync with every code change."
            ),
            "tags": [repo_name, *tags, "documentation", "knowledge-base"],
            "capabilities": ["readme-authoring", "adr-writing", "api-reference-generation", "runbook-creation", "onboarding-guide", "doc-sync"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file"],
            "preferred_profile": "balanced",
            "risk_level": "low",
        },
    ]

    # DevOps pilot for repos with CI/CD, containers, or infrastructure
    if tag_set & {"ci-cd", "containers", "kubernetes", "infrastructure"}:
        agents.append(
            {
                "id": f"{base_id}-devops-pilot",
                "role": f"{repo_name} DevOps Pilot",
                "description": (
                    f"Manages CI/CD pipelines, container builds, and deployment workflows for {repo_name}. "
                    "Instruments observability, automates secret rotation, enforces deployment gates, "
                    "and keeps the path from commit to production fast and reliable."
                ),
                "tags": [repo_name, *tags, "devops", "deployment"],
                "capabilities": ["pipeline-configuration", "container-management", "release-automation", "monitoring-setup", "secret-rotation", "deployment-gates"],
                "required_tools": ["read_file", "list_dir", "grep_search", "apply_patch", "create_file", "run_in_terminal", "github_repo"],
                "preferred_profile": "power",
                "risk_level": "medium",
            }
        )

    # Database architect for repos with a database/ORM layer
    if tag_set & {"database", "prisma", "python", "jvm", "dotnet", "ruby", "php"}:
        agents.append(
            {
                "id": f"{base_id}-database-architect",
                "role": f"{repo_name} Database Architect",
                "description": (
                    f"Designs schemas, authors migrations, optimizes slow queries, and enforces "
                    f"data-integrity constraints for {repo_name}. Runs explain-plan analysis, "
                    "implements indexing strategies, and documents the data model."
                ),
                "tags": [repo_name, *tags, "database", "schema", "migrations"],
                "capabilities": ["schema-design", "migration-authoring", "query-optimization", "index-strategy", "data-integrity-enforcement"],
                "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
                "preferred_profile": "balanced",
                "risk_level": "medium",
            }
        )

    # Performance engineer for Node, Python, JVM, Go, or Rust repos
    if tag_set & {"node", "javascript", "python", "go", "rust", "jvm", "dotnet"}:
        agents.append(
            {
                "id": f"{base_id}-performance-engineer",
                "role": f"{repo_name} Performance Engineer",
                "description": (
                    f"Profiles {repo_name} to locate CPU, memory, I/O, and network bottlenecks. "
                    "Implements caching strategies, tunes database queries, and establishes performance "
                    "budgets with automated regression alerts in CI."
                ),
                "tags": [repo_name, *tags, "performance", "profiling", "optimization"],
                "capabilities": ["profiling", "bottleneck-analysis", "caching-strategy", "query-optimization", "load-testing", "performance-budgeting"],
                "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
                "preferred_profile": "balanced",
                "risk_level": "medium",
            }
        )

    # Game studio agents for game repos
    if "game" in tag_set:
        agents.extend(_build_game_studio_agents(base_id, repo_name, tags, tag_set))

    # Browser test pilot for repos with Playwright or Cypress
    if "browser-testing" in tag_set:
        agents.append(
            {
                "id": f"{base_id}-browser-test-pilot",
                "role": f"{repo_name} Browser Test Pilot",
                "description": (
                    f"Scans code changes (git diff) for {repo_name} to identify user-facing "
                    "surfaces needing browser validation. Generates step-by-step test plans, "
                    "executes them against a live browser via Playwright or Cypress, and converts "
                    "validated flows into persistent end-to-end test suites. Integrates with CI "
                    "via exit-code conventions and records sessions for post-mortem replay."
                ),
                "tags": [repo_name, *tags, "testing", "browser", "e2e", "playwright"],
                "capabilities": [
                    "diff-analysis",
                    "test-plan-generation",
                    "browser-automation",
                    "playwright-execution",
                    "ci-integration",
                    "session-recording",
                ],
                "required_tools": ["read_file", "list_dir", "grep_search", "apply_patch", "create_file", "run_in_terminal"],
                "preferred_profile": "balanced",
                "risk_level": "medium",
            }
        )

    # Solana payment engineer for repos using @pump-fun/agent-payments-sdk or @solana packages
    if "solana" in tag_set:
        agents.append(
            {
                "id": f"{base_id}-solana-payment-engineer",
                "role": f"{repo_name} Solana Payment Engineer",
                "description": (
                    f"Builds and verifies on-chain payment flows for tokenized agents in {repo_name} "
                    "using the @pump-fun/agent-payments-sdk. Constructs Solana payment instructions, "
                    "serializes unsigned transactions for client signing, verifies on-chain invoice "
                    "payments server-side, and integrates Solana wallet adapters. Enforces the "
                    "mandatory pre-flight checklist and all safety rules: never logs key material, "
                    "never signs on behalf of users, always validates server-side."
                ),
                "tags": [repo_name, *tags, "solana", "web3", "payments", "pump-fun", "blockchain"],
                "capabilities": [
                    "payment-instruction-building",
                    "invoice-verification",
                    "wallet-adapter-integration",
                    "transaction-serialization",
                    "on-chain-validation",
                    "solana-rpc-integration",
                ],
                "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
                "preferred_profile": "balanced",
                "risk_level": "high",
            }
        )

    return agents


def _build_game_studio_agents(base_id: str, repo_name: str, tags: list[str], tag_set: set[str]) -> list[dict]:
    """Return game-studio–quality agents for repos identified as game projects."""
    game_agents: list[dict] = [
        {
            "id": f"{base_id}-creative-director",
            "role": f"{repo_name} Creative Director",
            "description": (
                f"Guards the creative vision, tone, and aesthetic direction of {repo_name}. "
                "Resolves cross-discipline conflicts between design, art, narrative, and audio using "
                "the MDA framework and player psychology. Presents 2-3 strategic options with "
                "trade-offs for every major creative decision; final call stays with the user."
            ),
            "tags": [repo_name, *tags, "game", "creative", "vision", "mda"],
            "capabilities": ["vision-guardianship", "pillar-conflict-resolution", "tone-definition", "scope-arbitration", "competitive-positioning", "reference-curation"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file"],
            "preferred_profile": "balanced",
            "risk_level": "low",
        },
        {
            "id": f"{base_id}-technical-director",
            "role": f"{repo_name} Technical Director",
            "description": (
                f"Owns all high-level technical decisions for {repo_name}: engine architecture, "
                "technology choices, performance budgets (frame time, memory, load times), and "
                "technical risk management. Produces Architecture Decision Records (ADRs), evaluates "
                "third-party libraries, and resolves cross-system technical conflicts."
            ),
            "tags": [repo_name, *tags, "game", "architecture", "performance", "adr"],
            "capabilities": ["architecture-ownership", "technology-evaluation", "performance-strategy", "technical-risk-assessment", "cross-system-integration", "adr-authoring"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
            "preferred_profile": "balanced",
            "risk_level": "medium",
        },
        {
            "id": f"{base_id}-game-designer",
            "role": f"{repo_name} Game Designer",
            "description": (
                f"Designs the rules, systems, and mechanics that define how {repo_name} plays. "
                "Applies MDA framework (Mechanics-Dynamics-Aesthetics), Self-Determination Theory, "
                "and Flow State Design. Maintains GDDs, defines balancing methodology (power curves, "
                "tuning knobs), and uses the sink/faucet model for virtual economies."
            ),
            "tags": [repo_name, *tags, "game", "design", "mechanics", "balance", "gdd"],
            "capabilities": ["core-loop-design", "systems-design", "balancing-framework", "player-experience-mapping", "edge-case-documentation", "gdd-authoring"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file"],
            "preferred_profile": "balanced",
            "risk_level": "low",
        },
        {
            "id": f"{base_id}-gameplay-programmer",
            "role": f"{repo_name} Gameplay Programmer",
            "description": (
                f"Translates GDDs into clean, performant, data-driven code for {repo_name}. "
                "Implements mechanics, player systems, and combat features with frame-rate-independent "
                "logic, clean state machines, and all gameplay values in external config files. "
                "Authors unit tests for all gameplay logic."
            ),
            "tags": [repo_name, *tags, "game", "programming", "mechanics", "data-driven"],
            "capabilities": ["feature-implementation", "data-driven-design", "state-management", "input-handling", "system-integration", "gameplay-testing"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
            "preferred_profile": "balanced",
            "risk_level": "medium",
        },
        {
            "id": f"{base_id}-producer",
            "role": f"{repo_name} Producer",
            "description": (
                f"Manages sprint planning, milestone tracking, and cross-team coordination for "
                f"{repo_name}. Identifies risks early, negotiates scope cuts that protect core "
                "game pillars, and maintains production/sprints/ and production/milestones/ documents "
                "to keep the project on schedule and on vision."
            ),
            "tags": [repo_name, *tags, "game", "production", "planning", "milestones"],
            "capabilities": ["sprint-planning", "milestone-tracking", "scope-management", "risk-identification", "cross-team-coordination", "release-coordination"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file"],
            "preferred_profile": "balanced",
            "risk_level": "low",
        },
        {
            "id": f"{base_id}-game-qa-lead",
            "role": f"{repo_name} Game QA Lead",
            "description": (
                f"Owns test strategy, bug triage, and release quality gates for {repo_name}. "
                "Defines per-milestone quality gates (crash rate, critical bug count, performance "
                "benchmarks, feature completeness), triages bugs using S1-S4 severity taxonomy, "
                "designs playtest protocols, and maintains regression suites for critical gameplay paths."
            ),
            "tags": [repo_name, *tags, "game", "qa", "testing", "quality-gates", "playtesting"],
            "capabilities": ["test-strategy", "bug-triage", "quality-gates", "regression-management", "playtest-coordination", "release-readiness"],
            "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
            "preferred_profile": "balanced",
            "risk_level": "medium",
        },
    ]

    # Engine-specific specialists
    if "godot" in tag_set:
        game_agents.append(
            {
                "id": f"{base_id}-godot-specialist",
                "role": f"{repo_name} Godot Specialist",
                "description": (
                    f"The authority on all Godot-specific patterns, APIs, and optimization techniques "
                    f"for {repo_name}. Guides GDScript vs C# vs GDExtension decisions, enforces "
                    "node/scene architecture best practices, proper signal usage, static typing, "
                    "resource management, and object pooling. Configures export presets and autoloads."
                ),
                "tags": [repo_name, *tags, "game", "godot", "gdscript", "engine"],
                "capabilities": ["godot-architecture", "gdscript-standards", "scene-design", "resource-management", "signal-patterns", "export-configuration"],
                "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
                "preferred_profile": "balanced",
                "risk_level": "medium",
            }
        )

    if "unity" in tag_set:
        game_agents.append(
            {
                "id": f"{base_id}-unity-specialist",
                "role": f"{repo_name} Unity Specialist",
                "description": (
                    f"The authority on Unity-specific patterns, APIs, and optimization for {repo_name}. "
                    "Guides C# code architecture, DOTS/ECS vs MonoBehaviour decisions, Addressables "
                    "asset management, UI Toolkit vs uGUI choices, shader/VFX Graph workflows, "
                    "and Unity project settings for target platforms."
                ),
                "tags": [repo_name, *tags, "game", "unity", "csharp", "engine"],
                "capabilities": ["unity-architecture", "ecs-dots", "addressables", "ui-toolkit", "shader-vfx", "platform-configuration"],
                "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
                "preferred_profile": "balanced",
                "risk_level": "medium",
            }
        )

    if "unreal" in tag_set:
        game_agents.append(
            {
                "id": f"{base_id}-unreal-specialist",
                "role": f"{repo_name} Unreal Engine Specialist",
                "description": (
                    f"The authority on Unreal Engine 5 patterns, Blueprints vs C++ decisions, "
                    f"and optimization for {repo_name}. Guides Gameplay Ability System (GAS) "
                    "implementation, replication/networking architecture, UMG/CommonUI patterns, "
                    "Blueprint/C++ interop, and Nanite/Lumen configuration for target platforms."
                ),
                "tags": [repo_name, *tags, "game", "unreal", "ue5", "blueprints", "engine"],
                "capabilities": ["unreal-architecture", "gameplay-ability-system", "replication", "umg-commonui", "blueprint-cpp-interop", "nanite-lumen"],
                "required_tools": ["read_file", "list_dir", "grep_search", "semantic_search", "apply_patch", "create_file", "run_in_terminal"],
                "preferred_profile": "balanced",
                "risk_level": "medium",
            }
        )

    return game_agents


def write_agentx_pack(repo_path: Path, repo_name: str, base_agents: list[dict], profiles: list[dict], agency_agents: list[dict]) -> None:
    tags = detect_stack_tags(repo_path)
    custom_agents = build_custom_agents(repo_name, tags)
    write_copilot_files(repo_path, repo_name, tags)

    merged: dict[str, dict] = {}
    for group in (base_agents, agency_agents, custom_agents):
        for agent in group:
            merged[str(agent["id"])] = agent

    agentx_dir = repo_path / ".agentx"
    agentx_dir.mkdir(parents=True, exist_ok=True)

    write_json(agentx_dir / "agents.json", sorted(merged.values(), key=lambda item: str(item["id"])))
    write_json(agentx_dir / "access_profiles.json", profiles)
    write_json(agentx_dir / "agency_import.json", agency_agents)

    base_id = slugify(repo_name)
    tag_set = set(tags)
    game_readme_section = ""
    if "game" in tag_set:
        engine_rows = ""
        if "godot" in tag_set:
            engine_rows += f"| `{base_id}-godot-specialist` | game/godot detected | Godot patterns, GDScript, scene architecture |\n"
        if "unity" in tag_set:
            engine_rows += f"| `{base_id}-unity-specialist` | game/unity detected | Unity C#, DOTS/ECS, Addressables, UI Toolkit |\n"
        if "unreal" in tag_set:
            engine_rows += f"| `{base_id}-unreal-specialist` | game/unreal detected | UE5 GAS, Blueprints, replication, UMG |\n"

        game_readme_section = f"""
## Game Studio Agents
| Agent | Profile | Purpose |
|-------|---------|---------|
| `{base_id}-creative-director` | balanced | Vision, MDA-based creative conflict resolution |
| `{base_id}-technical-director` | balanced | Architecture decisions, performance budgets, ADRs |
| `{base_id}-game-designer` | balanced | GDD authoring, systems design, balance methodology |
| `{base_id}-gameplay-programmer` | balanced | Data-driven mechanics, state machines, gameplay tests |
| `{base_id}-producer` | balanced | Sprint planning, milestone tracking, scope management |
| `{base_id}-game-qa-lead` | balanced | Test strategy, S1-S4 bug triage, quality gates |
{engine_rows}"""

    readme = f"""# AgentX Pack for {repo_name}

This repository is upgraded with AgentX capabilities for full-stack development and deployment.

## Included
- `agents.json`: merged core + imported + custom per-repo agents
- `access_profiles.json`: safe/balanced/power profiles
- `agency_import.json`: imported agents from agency-agents

## Core Per-Repo Agents
| Agent | Profile | Purpose |
|-------|---------|---------|
| `{base_id}-repo-architect` | safe | Architecture planning, ADRs, and dependency review |
| `{base_id}-implementation-pilot` | balanced | Code changes, refactoring, test validation |
| `{base_id}-orchestrator` | power | Multi-agent coordination and release handoffs |
| `{base_id}-qa-pilot` | balanced | Test planning, unit/integration/e2e tests |
| `{base_id}-security-hardener` | balanced | OWASP reviews, CVE triage, secrets hygiene |
| `{base_id}-documentation-pilot` | balanced | READMEs, ADRs, runbooks, API reference docs |

## Conditionally Generated Agents
| Agent | Condition | Purpose |
|-------|-----------|---------|
| `{base_id}-devops-pilot` | CI/CD, containers, or infra detected | Pipelines, containers, deployments |
| `{base_id}-database-architect` | DB/ORM layer detected | Schema design, migrations, query tuning |
| `{base_id}-performance-engineer` | Node/Python/Go/JVM/Rust/dotnet detected | Profiling, caching, performance budgets |
| `{base_id}-browser-test-pilot` | Playwright or Cypress detected | Diff→plan→browser test automation |
| `{base_id}-solana-payment-engineer` | @pump-fun/agent-payments-sdk or @solana/* detected | Solana invoice building, on-chain verification |
{game_readme_section}
## Access Profile Reference
| Profile | Write | Network | Secrets | Use case |
|---------|-------|---------|---------|---------|
| safe | no | no | none | Read-only analysis and auditing |
| balanced | yes | no | masked | Standard code changes and registry edits |
| power | yes | yes | scoped | Cross-repo orchestration and subagent spawning |

## Suggested commands
```bash
agentx find {repo_name}
agentx check {base_id}-implementation-pilot --profile balanced
agentx check {base_id}-orchestrator --profile power
agentx check {base_id}-qa-pilot --profile balanced
agentx check {base_id}-security-hardener --profile balanced
agentx check {base_id}-devops-pilot --profile power
```
"""
    (agentx_dir / "README.md").write_text(readme, encoding="utf-8")


_MCP_SERVERS: dict = {
    "servers": {
        "github": {
            "type": "http",
            "url": "https://api.githubcopilot.com/mcp/",
        }
    }
}

_VSCODE_SETTINGS: dict = {
    "chat.mcp.enabled": True,
    "github.copilot.chat.agent.thinkingTool": True,
    "github.copilot.nextEditSuggestions.enabled": True,
}


def write_copilot_files(repo_path: Path, repo_name: str, tags: list[str]) -> None:
    """Write .github/copilot-instructions.md and .vscode/ Copilot config files."""
    base_id = slugify(repo_name)
    tag_set = set(tags)
    tag_list = ", ".join(f"`{t}`" for t in sorted(tags)) if tags else "`general`"
    is_game = "game" in tag_set

    game_studio_section = ""
    if is_game:
        engine_agent_rows = ""
        if "godot" in tag_set:
            engine_agent_rows += f"| `{base_id}-godot-specialist` | balanced | Godot patterns, GDScript, scene architecture, export |\n"
        if "unity" in tag_set:
            engine_agent_rows += f"| `{base_id}-unity-specialist` | balanced | Unity C#, DOTS/ECS, Addressables, UI Toolkit |\n"
        if "unreal" in tag_set:
            engine_agent_rows += f"| `{base_id}-unreal-specialist` | balanced | UE5 GAS, Blueprints, replication, UMG/CommonUI |\n"

        game_studio_section = f"""
## Game Studio Agents

This is a game project. The following game-studio-quality agents are available:

### Directors (Strategic)
| Agent | Profile | Purpose |
|-------|---------|---------|
| `{base_id}-creative-director` | balanced | Vision guardian, MDA-based creative conflict resolution |
| `{base_id}-technical-director` | balanced | Architecture decisions, performance budgets, ADRs |
| `{base_id}-producer` | balanced | Sprint planning, milestone tracking, scope management |

### Specialists (Tactical)
| Agent | Profile | Purpose |
|-------|---------|---------|
| `{base_id}-game-designer` | balanced | GDD authoring, systems design, balance methodology |
| `{base_id}-gameplay-programmer` | balanced | Data-driven mechanics, state machines, gameplay tests |
| `{base_id}-game-qa-lead` | balanced | Test strategy, S1-S4 bug triage, quality gates |
{engine_agent_rows}
### Game Studio Workflow

1. Start every feature with `{base_id}-game-designer` — design before code
2. Use `{base_id}-creative-director` to resolve cross-discipline conflicts
3. Use `{base_id}-technical-director` for architecture choices and ADRs
4. Implement with `{base_id}-gameplay-programmer` — all values in config files
5. Validate with `{base_id}-game-qa-lead` before milestone gates

### Game Design Principles

- **MDA Framework**: Design from target Aesthetics → Dynamics → Mechanics
- **Data-driven values**: All gameplay numbers in `assets/data/` config files, never hardcoded
- **Frame-rate independence**: Delta time everywhere in gameplay code
- **Quality gates**: Crash rate, critical bug count, and perf benchmarks before every milestone
"""

    instructions = f"""\
# GitHub Copilot Custom Instructions — {repo_name}

## Project Context

This repository has been configured with the **AgentX** custom agent toolkit.
Detected stack tags: {tag_list}
{game_studio_section}
## Core Agents

Use the following specialized agents for development tasks in this repository:

| Agent | Profile | Purpose |
|-------|---------|---------|
| `{base_id}-repo-architect` | safe | Architecture planning, ADRs, and dependency review |
| `{base_id}-implementation-pilot` | balanced | Code changes, refactoring, test validation |
| `{base_id}-orchestrator` | power | Multi-agent coordination and release handoffs |
| `{base_id}-qa-pilot` | balanced | Test planning, unit/integration/e2e tests |
| `{base_id}-security-hardener` | balanced | OWASP reviews, CVE triage, secrets hygiene |
| `{base_id}-documentation-pilot` | balanced | READMEs, ADRs, runbooks, API reference docs |

## AgentX CLI

```bash
agentx find {repo_name}
agentx check {base_id}-implementation-pilot --profile balanced
agentx check {base_id}-orchestrator --profile power
agentx check {base_id}-security-hardener --profile balanced
```

## Access Profiles

| Profile | Write | Network | Secrets | Use case |
|---------|-------|---------|---------|----------|
| safe | no | no | none | Read-only analysis and auditing |
| balanced | yes | no | masked | Standard code changes |
| power | yes | yes | scoped | Cross-repo orchestration and subagent spawning |

## MCP Servers

The GitHub MCP server is configured in `.vscode/mcp.json`. Use `#github` tool
references in Copilot Chat to search issues, pull requests, and code across the
repository.

## Preferred Patterns

- Prefer the least-privilege profile that satisfies the task
- Use `safe` for read-only analysis, `balanced` for code changes, `power` only
  when cross-repo network access or subagent spawning is required
- Keep changes minimal, targeted, and validated before marking work complete
"""

    github_dir = repo_path / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    (github_dir / "copilot-instructions.md").write_text(instructions, encoding="utf-8")

    vscode_dir = repo_path / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)

    mcp_path = vscode_dir / "mcp.json"
    mcp_data = json.loads(mcp_path.read_text(encoding="utf-8")) if mcp_path.exists() else {}
    mcp_data.setdefault("servers", {}).update(_MCP_SERVERS["servers"])
    mcp_path.write_text(json.dumps(mcp_data, indent=2) + "\n", encoding="utf-8")

    settings_path = vscode_dir / "settings.json"
    settings_data = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    settings_data.update(_VSCODE_SETTINGS)
    settings_path.write_text(json.dumps(settings_data, indent=2) + "\n", encoding="utf-8")


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

        run(["git", "add", ".agentx", ".github/copilot-instructions.md", ".vscode"], cwd=local_path)
        run(
            [
                "git",
                "commit",
                "-m",
                "feat(agentx): add custom agent pack, Copilot instructions, and MCP config",
            ],
            cwd=local_path,
        )
        run(["git", "push", "-u", "origin", branch], cwd=local_path)

        body = (
            "Adds `.agentx` pack with:\n"
            "- merged agent registry (core + agency import + repo-custom agents)\n"
            "- access profiles for capability governance\n"
            "- usage docs for quick agent checks\n"
            "\n"
            "Adds GitHub Copilot configuration:\n"
            "- `.github/copilot-instructions.md`: repo-specific Copilot custom instructions\n"
            "- `.vscode/mcp.json`: GitHub MCP server wired to Copilot Chat\n"
            "- `.vscode/settings.json`: enables MCP and extended Copilot features\n"
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
                "feat: add AgentX toolkit, Copilot instructions, and MCP config",
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
