"""Simple agent executor for demonstration and testing.

This module provides a basic executor that simulates agent work.
In a real implementation, this would integrate with an actual AI agent
framework (e.g., GitHub Copilot SDK, LangChain, etc.).
"""
from __future__ import annotations

import random
import threading
import time
from typing import Any

from .registry import load_agents
from .runtime import get_runtime


_PROGRESS_MESSAGES: tuple[str, ...] = (
    "analyzing requirements",
    "gathering context",
    "processing logic",
    "validating approach",
    "generating output",
    "finalizing results",
)


def execute_agent_task(
    agent_id: str,
    task: str,
    metadata: dict[str, Any] | None = None,
    duration_range: tuple[float, float] = (2.0, 8.0),
) -> str:
    """Execute an agent task asynchronously.

    Parameters
    ----------
    agent_id:
        ID of the agent to execute.
    task:
        Task description/prompt for the agent.
    metadata:
        Additional metadata to attach to the execution.
    duration_range:
        Tuple of (min_seconds, max_seconds) for simulated duration.

    Returns
    -------
    str
        Execution ID that can be used to track progress.
    """
    agents = load_agents()
    agent = agents.get(agent_id)
    if not agent:
        raise ValueError(f"Unknown agent: {agent_id}")

    runtime = get_runtime()

    # Merge metadata with agent properties
    exec_metadata = {
        "risk_level": agent.risk_level,
        "profile": agent.preferred_profile,
        "capabilities": agent.capabilities,
        **(metadata or {}),
    }

    # Create execution
    execution_id = runtime.create_execution(
        agent_id=agent_id,
        agent_role=agent.role,
        task=task,
        metadata=exec_metadata,
    )

    # Start execution in background thread
    def _run() -> None:
        try:
            runtime.start_execution(execution_id)

            # Simulate work with progress updates
            duration = random.uniform(*duration_range)
            steps = random.randint(3, 6)
            step_duration = duration / steps

            for i in range(steps):
                time.sleep(step_duration)
                progress = (i + 1) / steps
                runtime.update_progress(
                    execution_id,
                    progress,
                    f"Step {i + 1}/{steps}: {_get_progress_message(i, steps)}",
                )

            # Complete with mock result
            runtime.complete_execution(
                execution_id,
                result={
                    "success": True,
                    "steps_completed": steps,
                    "output": f"Completed task: {task[:50]}...",
                },
            )

        except Exception as e:
            runtime.fail_execution(execution_id, str(e))

    thread = threading.Thread(target=_run, daemon=True, name=f"exec-{execution_id[:8]}")
    thread.start()

    return execution_id


def _get_progress_message(step: int, total_steps: int) -> str:
    """Generate a progress message based on current step."""
    if step < len(_PROGRESS_MESSAGES):
        return _PROGRESS_MESSAGES[step]
    return f"processing step {step + 1}"


def execute_workflow(
    workflow: list[tuple[str, str]],
    sequential: bool = True,
) -> list[str]:
    """Execute a workflow of multiple agent tasks.

    Parameters
    ----------
    workflow:
        List of (agent_id, task) tuples representing the workflow.
    sequential:
        If True, wait for each agent to complete before starting the next.
        If False, start all agents concurrently.

    Returns
    -------
    list[str]
        List of execution IDs for tracking.
    """
    execution_ids = []

    if sequential:
        # Execute agents one at a time
        for agent_id, task in workflow:
            exec_id = execute_agent_task(agent_id, task)
            execution_ids.append(exec_id)

            # Wait for completion
            runtime = get_runtime()
            while True:
                execution = runtime.get_execution(exec_id)
                if execution and execution.status.value in ("completed", "failed", "cancelled"):
                    break
                time.sleep(0.5)
    else:
        # Execute all agents concurrently
        for agent_id, task in workflow:
            exec_id = execute_agent_task(agent_id, task)
            execution_ids.append(exec_id)

    return execution_ids
