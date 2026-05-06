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

    @abstractmethod
    def search(self, namespace: str, query: str, k: int = 5) -> list[dict[str, Any]]:
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

    def search(self, namespace: str, query: str, k: int = 5) -> list[dict[str, Any]]:
        # Keyword scan over JSON-serialised records.  Acceptable for moderate-size
        # namespaces; for high-volume use cases swap to a vector or FTS backend.
        lowered = query.lower()
        payload = self._read_all()
        records = payload.get(namespace, [])
        if not isinstance(records, list):
            return []
        hits = [r for r in records if isinstance(r, dict) and lowered in json.dumps(r).lower()]
        return hits[-k:]

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


    def search(self, namespace: str, query: str, k: int = 5) -> list[dict[str, Any]]:
        pattern = f"%{query.lower()}%"
        with sqlite3.connect(self._db_file) as conn:
            rows = conn.execute(
                "SELECT payload FROM memory WHERE namespace=? AND LOWER(payload) LIKE ?"
                " ORDER BY created_at DESC LIMIT ?",
                (namespace, pattern, k),
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

    def search(self, namespace: str, query: str, k: int = 5) -> list[dict[str, Any]]:
        raise RuntimeError("Redis adapter requires external dependency and runtime setup")


class VectorMemoryAdapter(MemoryAdapter):
    """In-memory adapter used for tests and lightweight in-process workloads.

    For persistent, semantically-indexed storage use :class:`ChromaVectorMemoryAdapter`.
    """

    def __init__(self) -> None:
        self._records: dict[str, list[dict[str, Any]]] = {}

    def append(self, namespace: str, value: dict[str, Any]) -> None:
        self._records.setdefault(namespace, []).append(value)

    def read(self, namespace: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._records.get(namespace, [])[-limit:]

    def search(self, namespace: str, query: str, k: int = 5) -> list[dict[str, Any]]:
        # Keyword scan over the in-memory dict.  Acceptable for testing and
        # moderate workloads; swap VectorMemoryAdapter for a Chroma-backed
        # adapter with real embeddings for production semantic retrieval.
        lowered = query.lower()
        items = self._records.get(namespace, [])
        hits = [item for item in items if lowered in json.dumps(item).lower()]
        return hits[-k:]


class ChromaVectorMemoryAdapter(MemoryAdapter):
    """Persistent vector-backed adapter using ChromaDB.

    By default uses a hash-based embedding function that requires no network
    access and no pre-downloaded model.  For production semantic retrieval,
    pass a real embedding function at construction time::

        from agent_tools.providers.realai_embeddings import RealAIEmbeddings

        class RealAIChromaEF:
            def __call__(self, input: list[str]) -> list[list[float]]:
                return RealAIEmbeddings().embed(input)

        adapter = ChromaVectorMemoryAdapter(root_dir, embedding_fn=RealAIChromaEF())

    Requires ``chromadb`` to be installed::

        pip install chromadb
    """

    def __init__(self, root_dir: Path, embedding_fn: Any = None) -> None:
        try:
            import chromadb  # noqa: PLC0415
            from chromadb.config import Settings  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "ChromaVectorMemoryAdapter requires chromadb. "
                "Install it with: pip install chromadb"
            ) from exc

        self._client = chromadb.PersistentClient(
            path=str(root_dir / "vector_memory"),
            settings=Settings(anonymized_telemetry=False),
        )
        # Default to a lightweight hash-based embedding function so no network
        # or model download is required out of the box.
        self._embedding_fn = embedding_fn or _HashEmbeddingFunction()

    def _collection(self, namespace: str) -> "Any":  # chromadb.Collection
        # ChromaDB collection names must be 3-63 chars, alphanumeric + hyphens/underscores.
        safe_name = _safe_chroma_name(namespace)
        return self._client.get_or_create_collection(
            name=safe_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # we supply embeddings manually
        )

    def append(self, namespace: str, value: dict[str, Any]) -> None:
        from uuid import uuid4  # noqa: PLC0415

        col = self._collection(namespace)
        text = json.dumps(value)
        embedding = self._embedding_fn([text])[0]
        col.add(documents=[text], ids=[str(uuid4())], embeddings=[embedding])

    def read(self, namespace: str, limit: int = 20) -> list[dict[str, Any]]:
        col = self._collection(namespace)
        results = col.get()
        docs: list[str] = results.get("documents") or []
        parsed: list[dict[str, Any]] = []
        for d in docs:
            try:
                obj = json.loads(d)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(obj, dict):
                parsed.append(obj)
        return parsed[-limit:]

    def search(self, namespace: str, query: str, k: int = 5) -> list[dict[str, Any]]:
        col = self._collection(namespace)
        # ChromaDB raises if the collection is empty; guard against it.
        count = col.count()
        if count == 0:
            return []
        query_embedding = self._embedding_fn([query])[0]
        results = col.query(query_embeddings=[query_embedding], n_results=min(k, count))
        raw_docs: list[list[str]] = results.get("documents") or [[]]
        parsed: list[dict[str, Any]] = []
        for d in raw_docs[0]:
            try:
                obj = json.loads(d)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(obj, dict):
                parsed.append(obj)
        return parsed


def _hash_embed(text: str, dim: int = 64) -> list[float]:
    """Deterministic, network-free embedding via FNV-1a hash spreading.

    Not semantically meaningful — purely structural.  Produces a unit-norm
    float vector of ``dim`` dimensions so cosine similarity is well-defined.
    Replace with a real embedding function for production semantic search.
    """
    import hashlib  # noqa: PLC0415
    import math  # noqa: PLC0415
    import struct  # noqa: PLC0415

    raw = hashlib.sha256(text.encode("utf-8")).digest()
    # Tile the 32-byte digest to fill `dim` floats.
    needed = dim * 4
    tiled = (raw * ((needed // len(raw)) + 1))[:needed]
    floats = list(struct.unpack(f"{dim}f", tiled))
    # Normalise to unit length so cosine space is meaningful.
    magnitude = math.sqrt(sum(f * f for f in floats)) or 1.0
    return [f / magnitude for f in floats]


class _HashEmbeddingFunction:
    """Callable embedding function backed by :func:`_hash_embed`.

    Follows the ChromaDB embedding-function calling convention
    ``(input: list[str]) -> list[list[float]]``.
    """

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return [_hash_embed(t) for t in texts]


def _safe_chroma_name(namespace: str) -> str:
    """Return a ChromaDB-safe collection name from an arbitrary namespace string.

    ChromaDB requires names that are 3–63 characters, start/end with an
    alphanumeric character, and contain only alphanumerics, hyphens, and
    underscores.  Colons (used in session-scoped namespaces like
    ``{session_id}:global``) are replaced with double-underscores.
    """
    import re  # noqa: PLC0415

    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", namespace)
    # Trim to 63 chars; ensure minimum 3 chars by padding.
    safe = safe[:63].strip("_-")
    if len(safe) < 3:
        safe = safe.ljust(3, "0")
    return safe


def create_memory_adapter(
    adapter: str,
    root_dir: Path,
    embeddings_provider: Any | None = None,
) -> MemoryAdapter:
    """Create and return a :class:`MemoryAdapter` for the requested backend.

    Args:
        adapter:             One of ``"json"``, ``"sqlite"``, ``"redis"``,
                             ``"chroma"``, or ``"vector"``.
        root_dir:            Repository root used as the base path for
                             file-backed adapters.
        embeddings_provider: Optional object with an
                             ``.embed(texts: list[str]) -> list[list[float]]``
                             method.  When supplied and *adapter* is
                             ``"chroma"``, the provider is wrapped into a
                             ChromaDB-compatible embedding function so that
                             documents are indexed with real semantic
                             embeddings instead of the built-in hash fallback.
    """
    adapter_name = adapter.strip().lower()
    if adapter_name == "json":
        return JsonFileMemoryAdapter(root_dir / ".agentx" / "memory.json")
    if adapter_name == "sqlite":
        return SQLiteMemoryAdapter(root_dir / ".agentx" / "memory.sqlite")
    if adapter_name == "redis":
        return RedisMemoryAdapter()
    if adapter_name == "chroma":
        embedding_fn: Any | None = None
        if embeddings_provider is not None:
            embedding_fn = _ProviderEmbeddingFunction(embeddings_provider)
        return ChromaVectorMemoryAdapter(root_dir, embedding_fn=embedding_fn)
    if adapter_name in {"vector", "lancedb", "pgvector"}:
        # In-memory adapter for lightweight/test workloads.
        # Use "chroma" for persistent, semantically-indexed storage.
        return VectorMemoryAdapter()
    raise ValueError(f"Unsupported memory adapter: {adapter}")


class _ProviderEmbeddingFunction:
    """Wraps an embeddings provider into the ChromaDB embedding-function protocol.

    ChromaDB embedding functions are callables that accept
    ``input: list[str]`` and return ``list[list[float]]``.

    Any provider with an ``.embed(texts: list[str]) -> list[list[float]]``
    method is compatible — including :class:`~agent_tools.providers.realai_embeddings.RealAIEmbeddings`.

    Example::

        from agent_tools.providers.realai_embeddings import RealAIEmbeddings
        from agent_tools.engine.memory import create_memory_adapter

        adapter = create_memory_adapter(
            "chroma",
            repo_root,
            embeddings_provider=RealAIEmbeddings(),
        )
    """

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return self._provider.embed(texts)
