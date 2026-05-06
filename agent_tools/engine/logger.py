from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Any


@dataclass(slots=True)
class LogEvent:
    kind: str
    timestamp_ms: int
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "timestamp_ms": self.timestamp_ms,
            "data": self.data,
        }


class ExecutionLogger:
    def __init__(self, sink_file: Path | None = None) -> None:
        self._sink_file = sink_file
        self._events: list[LogEvent] = []

    @property
    def events(self) -> list[LogEvent]:
        return list(self._events)

    def log(self, kind: str, **data: Any) -> None:
        event = LogEvent(kind=kind, timestamp_ms=int(time() * 1000), data=dict(data))
        self._events.append(event)
        if self._sink_file is None:
            return
        self._sink_file.parent.mkdir(parents=True, exist_ok=True)
        with self._sink_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict()) + "\n")

    def to_jsonable(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events]
