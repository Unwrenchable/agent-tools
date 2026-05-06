# agent-tools

> **AI agent registry, capability enforcement, and multi-repo rollout for GitHub Copilot and autonomous coding agents.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Non-Commercial](https://img.shields.io/badge/license-non--commercial-lightgrey.svg)](LICENSE)
[![Topics: ai-agents · github-copilot · agent-registry · llm-tooling · devtools](https://img.shields.io/badge/topics-ai--agents%20%7C%20github--copilot%20%7C%20agent--registry%20%7C%20llm--tooling%20%7C%20devtools-informational.svg)](#)

`agent-tools` is a zero-dependency Python toolkit (`agentx` CLI) for managing AI agents across a GitHub organisation. It gives you:

- **Quick access** to a shared agent registry (`list`, `find`)
- **Smarter capability checks** (required tools vs granted tools)
- **Safer expanded access** via profile-based permissions (`safe`, `balanced`, `power`)
- **Real-time execution tracking** with live web dashboard
- **Workflow orchestration** for multi-agent collaboration
- **One-command rollout** of `.agentx` packs and Copilot config to every repo in an org

This project is inspired by multi-agent structure patterns (clear roles, workflows, and success criteria) and turns those ideas into a practical CLI you can use in your own ecosystem of repos.

## What you get

### Agent Management
- `agentx list`: see all registered agents
- `agentx find <query>`: quick lookup by role/tag/capability
- `agentx check <agent_id> [--profile ...]`: validate access fit
- `agentx recommend <agent_id>`: least-friction profile recommendation
- `agentx export --json`: export registry for automation pipelines
- `agentx import-agency <path>`: import markdown agents from agency-style repos

### Agent Training & Reliability Coverage
- Evaluation and regression specialists for measurable agent quality improvements
- Observability and feedback-loop specialists for production learning
- Grounding and incident-response specialists for safer, more reliable agent behavior

### Real-Time Execution
- `agentx serve`: launch web dashboard with live visualization
- `agentx run <agent_id> <task>`: execute an agent with a task
- `agentx workflow --file <json>`: run multi-agent workflows
- `agentx status`: monitor execution history and active tasks

**🎯 New:** Real-time agent execution tracking with visual dashboard! See [Real-Time Execution Guide](docs/REAL_TIME_EXECUTION.md) for details.

## Install

From this repository root:

```bash
python -m pip install -e .
```

If `agentx` is not on your `PATH`, use:

```bash
python -m agent_tools.cli <command>
```

## Quick start

### Basic Commands
```bash
# List and search agents
python -m agent_tools.cli list
python -m agent_tools.cli find orchestrator

# Validate agent access
python -m agent_tools.cli check orchestrator --profile safe
python -m agent_tools.cli recommend implementation-engineer

# Export registry
python -m agent_tools.cli export --json

# Import agents from other repos
python -m agent_tools.cli import-agency ~/code/agency-agents --output ./agency_import.json
python -m agent_tools.cli import-agency ~/code/agency-agents --merge

# from a GitHub URL (example)
git clone --depth 1 https://github.com/msitarzewski/agency-agents.git /tmp/agency-agents
python -m agent_tools.cli import-agency /tmp/agency-agents --merge
```

### Real-Time Execution & Dashboard

```bash
# Start the web dashboard
python -m agent_tools.cli serve
# Open http://127.0.0.1:7070 to see live agent activity

# Execute a single agent
python -m agent_tools.cli run backend-engineer "Implement user authentication API" --watch

# Run a workflow of multiple agents
python -m agent_tools.cli workflow --file examples/workflow-feature-dev.json

# Check execution status
python -m agent_tools.cli status --active

# Deterministic orchestration runtime
python -m agent_tools.cli run master --input "Create a sha256 hash for hello" --dry-run --json
python -m agent_tools.cli test
```

See the [Real-Time Execution Guide](docs/REAL_TIME_EXECUTION.md) for comprehensive examples and architecture workflows.

## Access model

Profiles are stored in `agent_tools/data/access_profiles.json`.

- `safe`: read-only analysis and discovery
- `balanced`: default coding profile (write enabled, no network)
- `power`: expanded profile for orchestration + cross-repo research

Agent definitions are in `agent_tools/data/agents.json` with:

- role + description
- capability tags
- required tools
- preferred profile
- risk level

The `check` command reports:

- `missing_tools` (agent under-provisioned)
- `extra_tools` (agent potentially over-provisioned)
- pass/fail + recommended profile

The `import-agency` command supports two modes:

- export-only mode (safe): parses markdown and writes a separate JSON file
- merge mode: upserts imported agents into your active registry (`agent_tools/data/agents.json` by default)

## Reuse in your ecosystem of repos

For each repo where you want smarter agent behavior:

1. Add this toolkit as a dev dependency (or copy the package folder).
2. Extend `agent_tools/data/agents.json` with repo-specific agents.
3. Tune `access_profiles.json` to your security boundary.
4. Add CI checks that run `python -m agent_tools.cli check ...` for critical agents.
5. Import upstream markdown agent packs as needed:

```bash
python -m agent_tools.cli import-agency /path/to/agency-agents --output .agentx/imported.json
python -m agent_tools.cli import-agency /path/to/agency-agents --merge --merge-target .agentx/agents.json
```

Example CI gate (concept):

```bash
python -m agent_tools.cli check implementation-engineer --profile balanced
python -m agent_tools.cli check orchestrator --profile power
```

## What was utilized from the referenced agency repo

Useful patterns adapted:

- standardized agent structure (identity, mission, workflow, metrics)
- orchestrator-first multi-agent coordination model
- explicit process and deliverable-driven agent design

What this project adds:

- concrete capability/access enforcement checks
- quick search and profile recommendation CLI
- portable policy model for multi-repo governance

## Project structure

```text
agent_tools/
  cli.py
  models.py
  registry.py
  data/
    access_profiles.json
    agents.json
pyproject.toml
README.md
```

Additional runtime-oriented folders:

```text
schema/
  agent.schema.json
  tool.schema.json
agents/
  *.agentx
agent_tools/engine/
agent_tools/tooling/
agent_tools/providers/
console/
```

## Per-repo overrides

Place a `.agentx/agents.json` and/or `.agentx/access_profiles.json` in your repo root (or any ancestor directory up to the nearest `.git` boundary). The CLI automatically discovers these files and **merges** them with the package defaults: per-repo entries override package entries with the same `id`/`name`, and additional entries are appended.

This means you can ship a lean base registry in the package and let each repository extend it with project-specific agents—exactly what the `.agentx/` pack already set up for this repo.

```bash
# Verify your repo-local agents are picked up
agentx list
```

## Knowledge Base

The repository includes a knowledge base with reference materials:

- [Quantitative Methods Formulas](docs/knowledge-base/quantitative-methods-formulas.md) - Comprehensive reference for CFA Level 1 quantitative methods formulas

## Next extensions

- add task-based policy checks (derive needed tools from task type)

## Multi-repo rollout (all repos)

Use the automation script to apply `.agentx` packs to every repo under an owner:

```bash
python tools/rollout_all_repos.py --owner Unwrenchable
```

Safe validation first:

```bash
python tools/rollout_all_repos.py --owner Unwrenchable --dry-run
```

If push/PR fails because token lacks write scope, fix GitHub auth and rerun only failed pushes:

```bash
python tools/retry_rollout_pushes.py --summary /tmp/agentx_rollout_summary.json --workdir /tmp/agentx-rollout
```

## Repo security hardening rollout

Harden all your repos in one command. Adds standard security files via PR and
applies GitHub repo settings (branch protection, Actions permissions, security
features) via the GitHub API.

### Quick start

```bash
# Dry-run first (default — no changes made)
python tools/harden_repos.py --owner Unwrenchable --hardening-all

# Apply everything: file PRs + settings
python tools/harden_repos.py --owner Unwrenchable --hardening-all --apply

# File PRs only (no API settings changes)
python tools/harden_repos.py --owner Unwrenchable --hardening-files --apply

# API settings only (no file PRs)
python tools/harden_repos.py --owner Unwrenchable --hardening-settings --apply

# Target specific repos
python tools/harden_repos.py --owner Unwrenchable --hardening-all --apply \
  --repos my-repo-1 my-repo-2
```

Output is a JSON summary with per-repo status, PR URLs, and settings applied/skipped/errors.

### What gets added per repo (file PR)

| File | Purpose |
|------|---------|
| `SECURITY.md` | Private vulnerability reporting, supported versions, disclosure policy |
| `.github/CODEOWNERS` | Enforces owner review on workflows, lockfiles, release configs |
| `.github/dependabot.yml` | Automated updates for detected ecosystems + GitHub Actions |
| `.github/pull_request_template.md` | Security checklist: deps, workflows, secrets, tests |
| `.github/workflows/security.yml` | Dependency review + Gitleaks secret scan (configurable) |
| `LICENSE` | Non-commercial source license (or dual-license if configured) |
| `README.md` | License summary section added/updated |

### Repo settings applied (API)

| Setting | Value |
|---------|-------|
| Branch protection | PRs required, 1 approval, dismiss stale reviews, require conversation resolution |
| Actions permissions | Default workflow token set to `read` (least privilege) |
| Dependabot alerts | Enabled |
| Dependabot security updates | Enabled |
| Secret scanning + push protection | Enabled (requires GitHub Advanced Security; errors reported gracefully) |

### Policy configuration (`policy.json`)

Customize hardening behavior by editing `policy.json` at the repo root:

```json
{
  "license_mode": "non-commercial",
  "license_contact": "your@email.com",
  "approvals_required": 1,
  "dependabot_schedule": "weekly",
  "security_workflow": true,
  "branch_protection": {
    "require_pr": true,
    "approvals_required": 1,
    "dismiss_stale_reviews": true,
    "require_conversation_resolution": true
  }
}
```

**`license_mode`** options:
- `"non-commercial"` (default) — non-commercial source-available license
- `"dual"` — dual-license scaffold (non-commercial public + commercial by contact)

Pass a custom policy file path with `--policy /path/to/policy.json`.

### Running tests

```bash
pip install -e ".[dev]"
python -m pytest
```
