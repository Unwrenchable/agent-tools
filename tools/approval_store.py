"""Approval request store backed by a JSON file.

Agents create approval requests for high-risk actions (e.g. committing to
main, running deploys).  A human reviews them via the approval UI and either
approves or rejects.  Once approved the orchestrator picks up the request and
executes the corresponding action.

The store file defaults to ``.approvals.json`` in the current working directory
but can be overridden by setting the ``APPROVALS_STORE`` environment variable.

This module is intentionally dependency-free (stdlib only) so it can be
imported without installing Flask.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

_DEFAULT_STORE = Path(os.getenv("APPROVALS_STORE", ".approvals.json"))


def _load(store_path: Path = _DEFAULT_STORE) -> dict[str, Any]:
    if not store_path.exists():
        return {"items": []}
    try:
        return json.loads(store_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"items": []}


def _save(data: dict[str, Any], store_path: Path = _DEFAULT_STORE) -> None:
    store_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def create_request(
    action: str,
    payload: dict[str, Any],
    store_path: Path = _DEFAULT_STORE,
) -> dict[str, Any]:
    """Create a new pending approval request and return it."""
    data = _load(store_path)
    item: dict[str, Any] = {
        "id": str(uuid4()),
        "action": action,
        "payload": payload,
        "status": "pending",
    }
    data["items"].append(item)
    _save(data, store_path)
    return item


def list_requests(store_path: Path = _DEFAULT_STORE) -> list[dict[str, Any]]:
    """Return all approval requests."""
    return _load(store_path).get("items", [])


def update_request(
    req_id: str,
    status: str,
    store_path: Path = _DEFAULT_STORE,
) -> bool:
    """Update the status of a request.  Returns ``True`` if found, else ``False``."""
    data = _load(store_path)
    for item in data["items"]:
        if item["id"] == req_id:
            item["status"] = status
            _save(data, store_path)
            return True
    return False


def get_request(
    req_id: str,
    store_path: Path = _DEFAULT_STORE,
) -> dict[str, Any] | None:
    """Return a single request by ID, or ``None`` if not found."""
    for item in _load(store_path).get("items", []):
        if item["id"] == req_id:
            return item
    return None


def annotate_request(
    req_id: str,
    store_path: Path = _DEFAULT_STORE,
    **kwargs: Any,
) -> bool:
    """Merge arbitrary keyword fields into a request entry.

    Use this to attach execution results, metadata, or flags without
    touching the ``status`` field directly.  Returns ``True`` if the
    request was found, ``False`` otherwise.

    Example::

        annotate_request(req_id, executed=True, result={"ok": True, "commit_sha": "abc…"})
    """
    data = _load(store_path)
    for item in data["items"]:
        if item["id"] == req_id:
            item.update(kwargs)
            _save(data, store_path)
            return True
    return False
