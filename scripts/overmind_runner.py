"""scripts/overmind_runner.py — Overmind multi-agent control loop.

Orchestrates the full RealAI agent pipeline:
  1. Task Planner decomposes the goal into steps.
  2. Each step is routed to the most suitable specialist agent.
  3. Memory Summarizer compresses each result into memory.
  4. The Overmind produces a final user-facing summary.

All steps share the same session_id so chain-of-thought and semantic
retrieval span the entire run.

Usage::

    export REALAI_API_URL="https://realai-qz3b.onrender.com"
    export REALAI_API_KEY="realai_live_xxx"

    python scripts/overmind_runner.py "Build a REST API for user authentication"

    # Or import and call from Python:
    from scripts.overmind_runner import run_goal
    result = run_goal("Audit the codebase for security issues")
"""

from __future__ import annotations

import json
import sys
from typing import Any

from agent_tools.engine.executor import AgentExecutor

# Heuristic tag → agent routing table.
# The Overmind may override this with explicit step assignments from the planner.
_STEP_AGENT_MAP: list[tuple[tuple[str, ...], str]] = [
    (("secur", "audit", "vulnerab", "secret"), "security"),
    (("deploy", "ci", "cd", "docker", "infra", "pipeline"), "devops"),
    (("architect", "design", "module", "api contract"), "architect"),
    (("document", "readme", "docstring", "tutorial"), "documentation"),
    (("review", "diff", "lint", "style"), "code_reviewer"),
    (("debug", "error", "traceback", "fix", "diagnose"), "debugger"),
    (("summariz", "compress", "memory"), "memory_summarizer"),
    (("plan", "decompose", "break"), "task_planner"),
]

_FALLBACK_AGENT = "code_engineer"
_SUMMARY_INPUT_MAX_CHARS = 1000


def _route_step(step: str) -> str:
    """Return the agent id best suited for *step* using keyword heuristics."""
    lower = step.lower()
    for keywords, agent_id in _STEP_AGENT_MAP:
        if any(kw in lower for kw in keywords):
            return agent_id
    return _FALLBACK_AGENT


def _parse_plan(plan_text: str) -> list[str]:
    """Extract steps from planner output.

    Accepts either:
    - A JSON object with a ``"steps"`` array of strings or ``{"description": ...}`` dicts.
    - Plain text with one step per non-empty line.
    """
    stripped = plan_text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(stripped)
            steps_raw: list[Any] = []
            if isinstance(data, dict):
                steps_raw = data.get("steps", [])
            elif isinstance(data, list):
                steps_raw = data
            steps: list[str] = []
            for item in steps_raw:
                if isinstance(item, str):
                    steps.append(item)
                elif isinstance(item, dict):
                    steps.append(item.get("description") or item.get("step") or str(item))
            if steps:
                return steps
        except (json.JSONDecodeError, TypeError):
            pass
    # Fall back to line-by-line parsing.
    return [line.strip() for line in plan_text.splitlines() if line.strip()]


def run_goal(
    goal: str,
    session_id: str | None = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run the full Overmind pipeline for *goal*.

    Args:
        goal:       High-level goal description.
        session_id: Optional session identifier for cross-run memory continuity.
                    A UUID is generated automatically if omitted.
        dry_run:    If True, no real provider calls are made.
        verbose:    If True, progress is printed to stdout.

    Returns:
        A dict with ``session_id``, ``plan``, ``results``, and ``summary``.
    """
    ex = AgentExecutor()

    def _log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    # ── Step 1: Planning ─────────────────────────────────────────────────────
    _log(f"\n[Overmind] Planning goal: {goal!r}")
    plan_res = ex.run(
        agent_id="task_planner",
        input_text=goal,
        session_id=session_id,
        dry_run=dry_run,
    )
    session_id = plan_res.session_id
    plan_text = plan_res.output.get("response", "") or plan_res.output.get("content", "")
    steps = _parse_plan(plan_text) or [goal]
    _log(f"[Overmind] Plan ({len(steps)} step(s)) | session={session_id}")

    # ── Step 2: Execute steps ────────────────────────────────────────────────
    step_results: list[dict[str, Any]] = []
    for i, step in enumerate(steps, start=1):
        agent_id = _route_step(step)
        _log(f"[Overmind] Step {i}/{len(steps)} → {agent_id!r}: {step[:80]!r}")
        step_res = ex.run(
            agent_id=agent_id,
            input_text=step,
            session_id=session_id,
            dry_run=dry_run,
        )
        step_output = step_res.output.get("response", "") or step_res.output.get("content", "")
        step_results.append({"step": step, "agent": agent_id, "output": step_output})

        # Compress the result into session memory.
        summary_input = f"Summarize this agent output for memory storage:\n{step_output[:_SUMMARY_INPUT_MAX_CHARS]}"
        ex.run(
            agent_id="memory_summarizer",
            input_text=summary_input,
            session_id=session_id,
            dry_run=dry_run,
        )

    # ── Step 3: Final Overmind summary ───────────────────────────────────────
    _log("[Overmind] Producing final summary …")
    results_text = "\n".join(
        f"Step {i}: [{r['agent']}] {r['step']}\n{r['output'][:300]}"
        for i, r in enumerate(step_results, start=1)
    )
    final_prompt = (
        f"Goal: {goal}\n\nExecution results:\n{results_text}\n\n"
        "Produce a concise user-facing summary of what was accomplished and any recommended next steps."
    )
    final_res = ex.run(
        agent_id="overmind",
        input_text=final_prompt,
        session_id=session_id,
        dry_run=dry_run,
    )
    summary = final_res.output.get("response", "") or final_res.output.get("content", "")
    _log(f"\n[Overmind] Done — session={session_id}")

    return {
        "session_id": session_id,
        "plan": steps,
        "results": step_results,
        "summary": summary,
    }


if __name__ == "__main__":
    goal_text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Hello, what can you do?"
    outcome = run_goal(goal_text)
    print("\n── Final Summary ──")
    print(outcome["summary"])
