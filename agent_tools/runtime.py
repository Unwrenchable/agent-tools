"""Agent execution runtime with real-time tracking.

Provides execution environment for running agents with lifecycle event tracking,
enabling real-time dashboard visualization of agent collaboration workflows.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


class ExecutionStatus(Enum):
    """Agent execution lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class ExecutionEvent:
    """Single event in an agent execution lifecycle."""

    execution_id: str
    agent_id: str
    event_type: str  # dispatch, progress, complete, error
    timestamp: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentExecution:
    """Represents a single agent execution instance."""

    id: str
    agent_id: str
    agent_role: str
    task: str
    status: ExecutionStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "task": self.task,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class ExecutionRuntime:
    """Agent execution runtime with event broadcasting."""

    def __init__(self) -> None:
        self._executions: dict[str, AgentExecution] = {}
        self._lock = threading.Lock()
        self._event_handlers: list[Callable[[ExecutionEvent], None]] = []
        self._history_file: Path | None = None

    def set_history_file(self, path: Path) -> None:
        """Enable execution history persistence."""
        self._history_file = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def subscribe(self, handler: Callable[[ExecutionEvent], None]) -> None:
        """Subscribe to execution events."""
        with self._lock:
            self._event_handlers.append(handler)

    def unsubscribe(self, handler: Callable[[ExecutionEvent], None]) -> None:
        """Unsubscribe from execution events."""
        with self._lock:
            try:
                self._event_handlers.remove(handler)
            except ValueError:
                pass

    def _emit_event(self, event: ExecutionEvent) -> None:
        """Broadcast event to all subscribers."""
        with self._lock:
            handlers = list(self._event_handlers)
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                pass  # Don't let handler errors break the runtime

    def create_execution(
        self,
        agent_id: str,
        agent_role: str,
        task: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a new agent execution and return its ID."""
        execution_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        execution = AgentExecution(
            id=execution_id,
            agent_id=agent_id,
            agent_role=agent_role,
            task=task,
            status=ExecutionStatus.QUEUED,
            created_at=now,
            metadata=metadata or {},
        )

        with self._lock:
            self._executions[execution_id] = execution

        return execution_id

    def start_execution(self, execution_id: str) -> None:
        """Mark execution as started and emit dispatch event."""
        with self._lock:
            execution = self._executions.get(execution_id)
            if not execution:
                return

            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            execution.status = ExecutionStatus.RUNNING
            execution.started_at = now

            # Store start time for duration calculation
            execution.metadata["_start_time_ms"] = time.time() * 1000

        self._emit_event(
            ExecutionEvent(
                execution_id=execution_id,
                agent_id=execution.agent_id,
                event_type="dispatch",
                timestamp=now,
                data={
                    "role": execution.agent_role,
                    "task": execution.task,
                    "risk_level": execution.metadata.get("risk_level", "medium"),
                    "profile": execution.metadata.get("profile", "balanced"),
                },
            )
        )

    def update_progress(
        self,
        execution_id: str,
        progress: float,
        message: str | None = None,
    ) -> None:
        """Report execution progress (0.0 to 1.0)."""
        with self._lock:
            execution = self._executions.get(execution_id)
            if not execution:
                return

            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        self._emit_event(
            ExecutionEvent(
                execution_id=execution_id,
                agent_id=execution.agent_id,
                event_type="progress",
                timestamp=now,
                data={
                    "progress": progress,
                    "message": message,
                    "role": execution.agent_role,
                },
            )
        )

    def complete_execution(
        self,
        execution_id: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Mark execution as completed successfully."""
        with self._lock:
            execution = self._executions.get(execution_id)
            if not execution:
                return

            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            execution.status = ExecutionStatus.COMPLETED
            execution.completed_at = now
            execution.result = result or {}

            # Calculate duration
            start_time_ms = execution.metadata.get("_start_time_ms")
            if start_time_ms:
                execution.duration_ms = int(time.time() * 1000 - start_time_ms)

        self._emit_event(
            ExecutionEvent(
                execution_id=execution_id,
                agent_id=execution.agent_id,
                event_type="complete",
                timestamp=now,
                data={
                    "role": execution.agent_role,
                    "duration_ms": execution.duration_ms,
                },
            )
        )

        self._persist_execution(execution)

    def fail_execution(self, execution_id: str, error: str) -> None:
        """Mark execution as failed with error message."""
        with self._lock:
            execution = self._executions.get(execution_id)
            if not execution:
                return

            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            execution.status = ExecutionStatus.FAILED
            execution.completed_at = now
            execution.error = error

            # Calculate duration
            start_time_ms = execution.metadata.get("_start_time_ms")
            if start_time_ms:
                execution.duration_ms = int(time.time() * 1000 - start_time_ms)

        self._emit_event(
            ExecutionEvent(
                execution_id=execution_id,
                agent_id=execution.agent_id,
                event_type="error",
                timestamp=now,
                data={
                    "role": execution.agent_role,
                    "error": error,
                    "duration_ms": execution.duration_ms,
                },
            )
        )

        self._persist_execution(execution)

    def get_execution(self, execution_id: str) -> AgentExecution | None:
        """Get execution details by ID."""
        with self._lock:
            return self._executions.get(execution_id)

    def get_active_executions(self) -> list[AgentExecution]:
        """Get all currently running executions."""
        with self._lock:
            return [
                e
                for e in self._executions.values()
                if e.status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING)
            ]

    def get_recent_executions(self, limit: int = 50) -> list[AgentExecution]:
        """Get recent executions, most recent first."""
        with self._lock:
            sorted_execs = sorted(
                self._executions.values(),
                key=lambda e: e.created_at,
                reverse=True,
            )
            return sorted_execs[:limit]

    def _persist_execution(self, execution: AgentExecution) -> None:
        """Append completed execution to history file."""
        if not self._history_file:
            return

        try:
            with self._history_file.open("a") as f:
                f.write(json.dumps(execution.to_dict()) + "\n")
        except Exception:
            pass  # Don't break execution on logging errors


# Global runtime instance
_runtime = ExecutionRuntime()


def get_runtime() -> ExecutionRuntime:
    """Get the global execution runtime instance."""
    return _runtime
