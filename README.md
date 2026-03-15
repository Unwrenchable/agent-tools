# agent-tools

Reusable toolkit for managing AI agents across repositories with:

- **Quick access** to agent registry (`list`, `find`)
- **Smarter capability checks** (required tools vs granted tools)
- **Safer expanded access** via profile-based permissions (`safe`, `balanced`, `power`)

This project is inspired by multi-agent structure patterns (clear roles, workflows, and success criteria) and turns those ideas into a practical CLI you can use in your own ecosystem of repos.

## What you get

- `agentx list`: see all registered agents
- `agentx find <query>`: quick lookup by role/tag/capability
- `agentx check <agent_id> [--profile ...]`: validate access fit
- `agentx recommend <agent_id>`: least-friction profile recommendation
- `agentx export --json`: export registry for automation pipelines
- `agentx import-agency <path>`: import markdown agents from agency-style repos

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

```bash
python -m agent_tools.cli list
python -m agent_tools.cli find orchestrator
python -m agent_tools.cli check orchestrator --profile safe
python -m agent_tools.cli recommend implementation-engineer
python -m agent_tools.cli export --json
python -m agent_tools.cli import-agency ~/code/agency-agents --output ./agency_import.json
python -m agent_tools.cli import-agency ~/code/agency-agents --merge

# from a GitHub URL (example)
git clone --depth 1 https://github.com/msitarzewski/agency-agents.git /tmp/agency-agents
python -m agent_tools.cli import-agency /tmp/agency-agents --merge
```

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

## Per-repo overrides

Place a `.agentx/agents.json` and/or `.agentx/access_profiles.json` in your repo root (or any ancestor directory up to the nearest `.git` boundary). The CLI automatically discovers these files and **merges** them with the package defaults: per-repo entries override package entries with the same `id`/`name`, and additional entries are appended.

This means you can ship a lean base registry in the package and let each repository extend it with project-specific agents—exactly what the `.agentx/` pack already set up for this repo.

```bash
# Verify your repo-local agents are picked up
agentx list
```

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
