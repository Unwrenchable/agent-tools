from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class MemoryAdapter(ABC):
    @abstractmethod
    def append(self, namespace: str, value: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def read(self, namespace: str, limit: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError


class JsonFileMemoryAdapter(MemoryAdapter):
    def __init__(self, memory_file: Path) -> None:
        self._memory_file = memory_file
        self._memory_file.parent.mkdir(parents=True, exist_ok=True)

    def append(self, namespace: str, value: dict[str, Any]) -> None:
        payload = self._read_all()
        payload.setdefault(namespace, []).append(value)
        self._memory_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def read(self, namespace: str, limit: int = 20) -> list[dict[str, Any]]:
        payload = self._read_all()
        records = payload.get(namespace, [])
        if not isinstance(records, list):
            return []
        return [record for record in records[-limit:] if isinstance(record, dict)]

    def _read_all(self) -> dict[str, Any]:
        if not self._memory_file.exists():
            return {}
        try:
            raw = json.loads(self._memory_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(raw, dict):
            return {}
        return raw


class SQLiteMemoryAdapter(MemoryAdapter):
    def __init__(self, db_file: Path) -> None:
        self._db_file = db_file
        self._db_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self._db_file) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory (
                    namespace TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def append(self, namespace: str, value: dict[str, Any]) -> None:
        with sqlite3.connect(self._db_file) as conn:
            conn.execute(
                "INSERT INTO memory(namespace, payload) VALUES(?, ?)",
                (namespace, json.dumps(value)),
            )

    def read(self, namespace: str, limit: int = 20) -> list[dict[str, Any]]:
        with sqlite3.connect(self._db_file) as conn:
            rows = conn.execute(
                "SELECT payload FROM memory WHERE namespace=? ORDER BY created_at DESC LIMIT ?",
                (namespace, limit),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in reversed(rows):
            try:
                payload = json.loads(row[0])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                result.append(payload)
        return result


class RedisMemoryAdapter(MemoryAdapter):
    def append(self, namespace: str, value: dict[str, Any]) -> None:
        raise RuntimeError("Redis adapter requires external dependency and runtime setup")

    def read(self, namespace: str, limit: int = 20) -> list[dict[str, Any]]:
        raise RuntimeError("Redis adapter requires external dependency and runtime setup")


class VectorMemoryAdapter(MemoryAdapter):
    def __init__(self) -> None:
        self._records: dict[str, list[dict[str, Any]]] = {}

    def append(self, namespace: str, value: dict[str, Any]) -> None:
        self._records.setdefault(namespace, []).append(value)

    def read(self, namespace: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._records.get(namespace, [])[-limit:]


def create_memory_adapter(adapter: str, root_dir: Path) -> MemoryAdapter:
    adapter_name = adapter.strip().lower()
    if adapter_name == "json":
        return JsonFileMemoryAdapter(root_dir / ".agentx" / "memory.json")
    if adapter_name == "sqlite":
        return SQLiteMemoryAdapter(root_dir / ".agentx" / "memory.sqlite")
    if adapter_name == "redis":
        return RedisMemoryAdapter()
    if adapter_name in {"vector", "chroma", "lancedb", "pgvector"}:
        return VectorMemoryAdapter()
    raise ValueError(f"Unsupported memory adapter: {adapter}")
