#!/usr/bin/env python3
"""Orchestration worker — polls the approval store and executes approved actions.

The worker loop:

1. Polls ``.approvals.json`` every ``ORCHESTRATION_POLL_INTERVAL`` seconds.
2. For each approved, non-executed item:
   a. If ``run_tests=true``: runs pytest inside the Docker sandbox image first.
      Aborts and marks the item ``failed`` if tests fail.
   b. Applies the patch — inside the Docker sandbox (``sandbox=true``, default)
      or directly on the host (``sandbox=false``).
   c. Marks the item ``executed`` and attaches the result.
   d. Sends a Slack/Teams notification for success or failure.

Environment variables
---------------------
ORCHESTRATION_POLL_INTERVAL  Seconds between polls (default: 5).
REPO_ROOT                    Absolute path to the repository root (default: ".").
SANDBOX_IMAGE                Docker image for sandbox runs (default: realai-sandbox:latest).
SLACK_WEBHOOK / TEAMS_WEBHOOK  Notification targets (see tools/notifier.py).

Run::

    python tools/orchestration_worker.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

# ------------------------------------------------------------------
# sys.path — allow sibling tools/ modules and the repo package to be imported
# ------------------------------------------------------------------
_TOOLS_DIR = Path(__file__).resolve().parent
_REPO_ROOT_DEFAULT = _TOOLS_DIR.parent
for _p in [str(_TOOLS_DIR), str(_REPO_ROOT_DEFAULT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from approval_store import annotate_request, list_requests, update_request
from notifier import Notifier
from agent_tools.agents_impl.code_engineer_agent import CodeEngineerAgent

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
_POLL_INTERVAL = int(os.environ.get("ORCHESTRATION_POLL_INTERVAL", "5"))
_REPO_ROOT = Path(os.environ.get("REPO_ROOT", str(_REPO_ROOT_DEFAULT))).resolve()
_SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "realai-sandbox:latest")

_notifier = Notifier()


# ------------------------------------------------------------------
# Action handlers
# ------------------------------------------------------------------

def _execute_apply_patch(item: dict[str, Any]) -> dict[str, Any]:
    """Handle an ``apply_patch`` approval item."""
    payload = item.get("payload", {})
    patch = payload.get("patch", "")
    commit_message = payload.get("commit_message", "apply patch")
    author = payload.get("author")
    use_sandbox = payload.get("sandbox", True)
    run_tests = payload.get("run_tests", True)

    agent = CodeEngineerAgent(repo_root=_REPO_ROOT)

    if use_sandbox and run_tests:
        _notifier.notify(f"Running tests in sandbox for approval `{item['id']}`")
        test_res = agent.run_tests_in_sandbox(image=_SANDBOX_IMAGE)
        if not test_res.get("ok"):
            _notifier.notify(
                f"Tests FAILED in sandbox for approval `{item['id']}`",
                title="Test failure",
            )
            return {"ok": False, "stage": "tests", "result": test_res}
        _notifier.notify(f"Tests passed in sandbox for approval `{item['id']}`")

    if use_sandbox:
        return agent.apply_patch_and_commit_sandbox(
            patch_text=patch,
            commit_message=commit_message,
            author=author,
            image=_SANDBOX_IMAGE,
        )
    return agent.apply_patch_and_commit(
        patch_text=patch,
        commit_message=commit_message,
        author=author,
    )


def _execute(item: dict[str, Any]) -> dict[str, Any]:
    action = item.get("action", "")
    if action == "apply_patch":
        return _execute_apply_patch(item)
    return {"ok": False, "error": f"unsupported action: {action!r}"}


# ------------------------------------------------------------------
# Main loop
# ------------------------------------------------------------------

def main_loop() -> None:
    _notifier.notify("Orchestration worker starting")
    print("Orchestration worker starting — polling every", _POLL_INTERVAL, "s")

    while True:
        try:
            _tick()
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] unhandled error in tick: {exc}")
        time.sleep(_POLL_INTERVAL)


def _tick() -> None:
    items = list_requests()
    for item in items:
        if item.get("status") != "approved" or item.get("executed"):
            continue
        req_id = item["id"]
        print(f"[worker] executing approved item {req_id}: {item.get('action')}")
        _notifier.notify(
            f"Executing approved action `{item.get('action')}` (id: `{req_id}`)"
        )
        try:
            res = _execute(item)
        except Exception as exc:  # noqa: BLE001
            res = {"ok": False, "error": str(exc)}

        if res.get("ok"):
            annotate_request(req_id, status="executed", executed=True, result=res)
            _notifier.notify(f"Execution succeeded for approval `{req_id}`")
            print(f"[worker] succeeded: {req_id}")
        else:
            annotate_request(req_id, status="failed", result=res)
            detail = res.get("error") or str(res.get("result", ""))
            _notifier.notify(
                f"Execution FAILED for approval `{req_id}`: {detail}",
                title="Execution failure",
            )
            print(f"[worker] failed: {req_id} — {detail}")


if __name__ == "__main__":
    main_loop()
