from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from dataclasses import asdict

from .dashboard import serve as _serve_dashboard
from .engine.executor import AgentExecutor
from .engine.loader import ManifestValidationError
from .engine.test_harness import run_self_tests
from .executor import execute_agent_task, execute_workflow
from .importer import import_agency_agents, merge_into_registry, write_json
from .registry import (
    assess_agent_access,
    find_agents,
    load_agents,
    load_profiles,
    recommend_profile,
)
from .runtime import get_runtime


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentx",
        description="Quick-access agent toolkit with capability/access checks",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all registered agents")

    find_parser = sub.add_parser("find", help="Search agents by keyword")
    find_parser.add_argument("query", help="search term")

    check_parser = sub.add_parser("check", help="Check if profile grants required access")
    check_parser.add_argument("agent_id", help="agent identifier")
    check_parser.add_argument("--profile", default=None, help="profile name (safe|balanced|power)")

    rec_parser = sub.add_parser("recommend", help="Recommend best profile for an agent")
    rec_parser.add_argument("agent_id", help="agent identifier")

    export_parser = sub.add_parser("export", help="Export merged toolkit data")
    export_parser.add_argument("--json", action="store_true", help="output JSON")

    import_parser = sub.add_parser(
        "import-agency",
        help="Import markdown agents from agency-style repos into JSON registry",
    )
    import_parser.add_argument("source", help="path to agency repo or folder with markdown agents")
    import_parser.add_argument(
        "--output",
        default="agent_tools/data/agency_import.json",
        help="output JSON path for imported agents",
    )
    import_parser.add_argument(
        "--merge",
        action="store_true",
        help="merge imported agents into registry target",
    )
    import_parser.add_argument(
        "--merge-target",
        default="agent_tools/data/agents.json",
        help="registry JSON path used when --merge is set",
    )

    serve_parser = sub.add_parser("serve", help="Launch the AgentX web dashboard")
    serve_parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=7070, help="port to listen on (default: 7070)")
    serve_parser.add_argument("--no-simulation", action="store_true", help="disable simulated activity")

    run_parser = sub.add_parser("run", help="Execute an agent with a task")
    run_parser.add_argument("agent_id", help="agent identifier")
    run_parser.add_argument("task", nargs="?", help="task description for the agent")
    run_parser.add_argument("--input", dest="input_text", help="input text (alternative to positional task)")
    run_parser.add_argument("--provider", default=None, help="provider override (openai|groq|anthropic|realai|local)")
    run_parser.add_argument("--dry-run", action="store_true", help="show planned actions without side effects")
    run_parser.add_argument("--json", action="store_true", help="emit structured JSON output")
    run_parser.add_argument("--watch", action="store_true", help="watch execution progress")

    workflow_parser = sub.add_parser("workflow", help="Execute a workflow of multiple agents")
    workflow_parser.add_argument("--file", required=True, help="JSON file with workflow definition")
    workflow_parser.add_argument("--parallel", action="store_true", help="execute agents concurrently")

    status_parser = sub.add_parser("status", help="Show execution status")
    status_parser.add_argument("--active", action="store_true", help="show only active executions")
    status_parser.add_argument("--limit", type=int, default=10, help="number of recent executions to show")

    sub.add_parser("test", help="Run schema and agent self-tests")

    return parser


def cmd_list() -> int:
    agents = load_agents()
    for agent in agents.values():
        print(f"{agent.id:24} {agent.role}")
    return 0


def cmd_find(query: str) -> int:
    agents = load_agents()
    matches = list(find_agents(agents, query))
    if not matches:
        print("No agents found")
        return 1

    for agent in matches:
        print(f"{agent.id}: {agent.role}")
        print(f"  tags: {', '.join(agent.tags)}")
        print(f"  capabilities: {', '.join(agent.capabilities)}")
    return 0


def cmd_check(agent_id: str, profile_name: str | None) -> int:
    agents = load_agents()
    profiles = load_profiles()

    agent = agents.get(agent_id)
    if agent is None:
        print(f"Unknown agent: {agent_id}")
        return 2

    if profile_name is None:
        profile = recommend_profile(agent, profiles)
    else:
        profile = profiles.get(profile_name)
        if profile is None:
            print(f"Unknown profile: {profile_name}")
            return 2

    report = assess_agent_access(agent, profile)

    status = "PASS" if report["pass"] else "FAIL"
    print(f"[{status}] agent={report['agent']} profile={report['profile']}")
    if report["missing_tools"]:
        print(f"missing_tools: {', '.join(report['missing_tools'])}")
    else:
        print("missing_tools: none")

    print(f"extra_tools: {', '.join(report['extra_tools']) if report['extra_tools'] else 'none'}")
    print(f"risk_level: {report['risk_level']}")
    print(f"recommended_profile: {report['recommended_profile']}")
    return 0 if report["pass"] else 3


def cmd_recommend(agent_id: str) -> int:
    agents = load_agents()
    profiles = load_profiles()

    agent = agents.get(agent_id)
    if agent is None:
        print(f"Unknown agent: {agent_id}")
        return 2

    profile = recommend_profile(agent, profiles)
    print(profile.name)
    print(f"tools: {', '.join(profile.tools)}")
    print(f"write={profile.write} network={profile.network} secrets={profile.secrets}")
    return 0


def cmd_export(as_json: bool) -> int:
    agents = load_agents()
    profiles = load_profiles()

    payload = {
        "agents": [asdict(a) for a in agents.values()],
        "profiles": [asdict(p) for p in profiles.values()],
    }

    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"agents={len(payload['agents'])} profiles={len(payload['profiles'])}")

    return 0


def cmd_import_agency(source: str, output: str, merge: bool, merge_target: str) -> int:
    imported = import_agency_agents(source)
    if not imported:
        print("No agent markdown files were detected")
        return 1

    if merge:
        target, imported_count, added, updated = merge_into_registry(imported, merge_target)
        print(f"Imported: {imported_count}")
        print(f"Merged into: {target}")
        print(f"Added: {added}")
        print(f"Updated: {updated}")
        return 0

    target = write_json(output, imported)
    print(f"Imported: {len(imported)}")
    print(f"Output: {target}")
    return 0


def cmd_serve(host: str, port: int, no_simulation: bool) -> int:
    _serve_dashboard(host=host, port=port, enable_simulation=not no_simulation)
    return 0


def cmd_run(
    agent_id: str,
    task: str | None,
    input_text: str | None,
    watch: bool,
    provider: str | None,
    dry_run: bool,
    as_json: bool,
) -> int:
    """Execute an agent with a task or input payload."""
    resolved_input = (input_text or task or "").strip()
    if not resolved_input:
        print("Error: provide either positional task or --input")
        return 2

    print(f"Executing agent: {agent_id}")
    print(f"Input: {resolved_input}")

    # New deterministic engine path for provider override or dry-run usage.
    if provider or dry_run or as_json:
        try:
            executor = AgentExecutor(repo_root=Path.cwd())
            result = executor.run(
                agent_id=agent_id,
                input_text=resolved_input,
                provider_override=provider,
                dry_run=dry_run,
            )
        except ManifestValidationError as exc:
            print(f"Manifest validation failed: {exc}")
            for err in exc.errors:
                print(f"- {err}")
            return 1
        except Exception as exc:
            print(f"Error: {exc}")
            return 1

        payload = {
            "agent_id": result.agent_id,
            "provider": result.provider,
            "latency_ms": result.latency_ms,
            "dry_run": result.dry_run,
            "tool_calls": result.tool_calls,
            "output": result.output,
            "logs": result.logs,
        }
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Provider: {result.provider}")
            print(f"Latency: {result.latency_ms}ms")
            print(f"Dry run: {result.dry_run}")
            print(f"Tool calls: {len(result.tool_calls)}")
            print(f"Output: {json.dumps(result.output, indent=2)}")
        return 0

    try:
        execution_id = execute_agent_task(agent_id, resolved_input)
        print(f"Execution ID: {execution_id}")

        if watch:
            print("\nWatching execution...")
            runtime = get_runtime()
            last_status = None

            while True:
                execution = runtime.get_execution(execution_id)
                if not execution:
                    print("Execution not found")
                    return 1

                if execution.status.value != last_status:
                    print(f"Status: {execution.status.value}")
                    last_status = execution.status.value

                if execution.status.value in ("completed", "failed", "cancelled"):
                    if execution.status.value == "completed":
                        print(f"\n✓ Completed in {execution.duration_ms}ms")
                        if execution.result:
                            print(f"Result: {json.dumps(execution.result, indent=2)}")
                        return 0
                    else:
                        print(f"\n✗ Failed: {execution.error}")
                        return 1

                time.sleep(0.5)

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_test() -> int:
    """Run agent manifest and fixture self-tests."""
    try:
        summary = run_self_tests(Path.cwd())
    except ManifestValidationError as exc:
        print(f"Manifest validation failed: {exc}")
        for err in exc.errors:
            print(f"- {err}")
        return 1
    except Exception as exc:
        print(f"Test harness failed: {exc}")
        return 1

    print(f"Self-tests: total={summary.total} passed={summary.passed} failed={summary.failed}")
    return 0 if summary.failed == 0 else 1


def cmd_workflow(file: str, parallel: bool) -> int:
    """Execute a workflow from a JSON file."""
    try:
        with open(file) as f:
            workflow_def = json.load(f)

        workflow = [(step["agent_id"], step["task"]) for step in workflow_def["steps"]]

        print(f"Executing workflow with {len(workflow)} steps")
        if parallel:
            print("Mode: parallel")
        else:
            print("Mode: sequential")

        execution_ids = execute_workflow(workflow, sequential=not parallel)

        print(f"\nStarted {len(execution_ids)} executions:")
        for i, exec_id in enumerate(execution_ids):
            print(f"  {i + 1}. {exec_id}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_status(active: bool, limit: int) -> int:
    """Show execution status."""
    runtime = get_runtime()

    if active:
        executions = runtime.get_active_executions()
        print(f"Active executions: {len(executions)}")
    else:
        executions = runtime.get_recent_executions(limit=limit)
        print(f"Recent executions (limit {limit}):")

    if not executions:
        print("No executions found")
        return 0

    print()
    for execution in executions:
        duration = f"{execution.duration_ms}ms" if execution.duration_ms else "running"
        status_icon = {
            "completed": "✓",
            "failed": "✗",
            "running": "→",
            "queued": "·",
            "cancelled": "○",
        }.get(execution.status.value, "?")

        print(f"{status_icon} {execution.id[:8]} | {execution.agent_id:20} | {execution.status.value:10} | {duration:10}")
        print(f"  Task: {execution.task[:60]}{'...' if len(execution.task) > 60 else ''}")
        if execution.error:
            print(f"  Error: {execution.error}")
        print()

    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "list":
        return cmd_list()
    if args.command == "find":
        return cmd_find(args.query)
    if args.command == "check":
        return cmd_check(args.agent_id, args.profile)
    if args.command == "recommend":
        return cmd_recommend(args.agent_id)
    if args.command == "export":
        return cmd_export(args.json)
    if args.command == "import-agency":
        return cmd_import_agency(args.source, args.output, args.merge, args.merge_target)
    if args.command == "serve":
        return cmd_serve(args.host, args.port, args.no_simulation)
    if args.command == "run":
        return cmd_run(
            args.agent_id,
            args.task,
            args.input_text,
            args.watch,
            args.provider,
            args.dry_run,
            args.json,
        )
    if args.command == "workflow":
        return cmd_workflow(args.file, args.parallel)
    if args.command == "status":
        return cmd_status(args.active, args.limit)
    if args.command == "test":
        return cmd_test()

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
