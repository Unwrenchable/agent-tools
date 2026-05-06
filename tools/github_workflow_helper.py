"""GitHub Actions workflow dispatch and run-status polling helper.

Provides two functions used by the orchestration worker:

* :func:`dispatch_workflow_and_poll` — trigger a ``workflow_dispatch``
  event and poll until the run completes or times out.
* :func:`fetch_workflow_run_logs` — download the log ZIP for a completed
  run and return a ``{filename: bytes}`` mapping.

Requirements::

    pip install requests

Environment variables typically set by the worker
--------------------------------------------------
GITHUB_REPO            Repository in ``owner/repo`` form.
GITHUB_TOKEN           PAT with ``repo`` + ``workflow`` scopes.
GITHUB_CI_WORKFLOW     Workflow filename, e.g. ``ci_on_demand.yml``.
GITHUB_REF             Branch/tag/SHA to dispatch the workflow on.
CI_DISPATCH_TIMEOUT    Max seconds to wait for the run (default: 900).
CI_POLL_INTERVAL       Seconds between status checks (default: 10).
"""
from __future__ import annotations

import io
import time
import zipfile
from typing import Any

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:  # pragma: no cover
    _HAS_REQUESTS = False

_API = "https://api.github.com"


def dispatch_workflow_and_poll(
    repo: str,
    workflow_file: str,
    ref: str,
    token: str,
    inputs: dict[str, str] | None = None,
    timeout_seconds: int = 900,
    poll_interval: int = 10,
) -> tuple[bool, dict[str, Any]]:
    """Dispatch a ``workflow_dispatch`` event and wait for the run to finish.

    The function dispatches the workflow, then polls the list of runs for
    that workflow until the most-recent run moves to ``completed`` status
    or *timeout_seconds* elapses.

    Args:
        repo:             Repository in ``owner/repo`` form.
        workflow_file:    Workflow filename inside ``.github/workflows/``
                          (e.g. ``ci_on_demand.yml``).
        ref:              Git ref to run the workflow on (branch, tag, SHA).
        token:            GitHub token with ``repo`` + ``workflow`` scopes.
        inputs:           Optional ``workflow_dispatch`` input parameters.
        timeout_seconds:  Maximum seconds to wait before returning failure.
        poll_interval:    Seconds between status-check requests.

    Returns:
        ``(ok, result)`` where *ok* is ``True`` if the workflow concluded
        with ``"success"`` and *result* contains ``run_id``, ``conclusion``,
        and the raw run object, or error details on failure.
    """
    if not _HAS_REQUESTS:
        return False, {"error": "requests library not installed"}

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    dispatch_url = f"{_API}/repos/{repo}/actions/workflows/{workflow_file}/dispatches"
    body: dict[str, Any] = {"ref": ref}
    if inputs:
        body["inputs"] = inputs

    r = _requests.post(dispatch_url, json=body, headers=headers, timeout=30)
    if r.status_code not in (201, 204):
        return False, {
            "error": "dispatch_failed",
            "status": r.status_code,
            "body": r.text,
        }

    # Allow GitHub a moment to create the run before polling.
    time.sleep(3)

    list_url = f"{_API}/repos/{repo}/actions/workflows/{workflow_file}/runs"
    deadline = time.time() + timeout_seconds
    run_id: int | None = None

    while time.time() < deadline:
        try:
            r = _requests.get(
                list_url,
                headers=headers,
                params={"per_page": 1},
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            time.sleep(poll_interval)
            continue

        if r.status_code != 200:
            time.sleep(poll_interval)
            continue

        runs = r.json().get("workflow_runs", [])
        if not runs:
            time.sleep(poll_interval)
            continue

        run = runs[0]
        run_id = run.get("id")
        status = run.get("status", "")
        if status == "completed":
            conclusion = run.get("conclusion", "")
            return conclusion == "success", {
                "run_id": run_id,
                "conclusion": conclusion,
                "raw": run,
            }
        time.sleep(poll_interval)

    return False, {"error": "timeout_waiting_for_workflow", "run_id": run_id}


def fetch_workflow_run_logs(
    repo: str,
    run_id: int,
    token: str,
    timeout_seconds: int = 60,
) -> tuple[bool, dict[str, Any]]:
    """Download and unpack the log archive for a workflow run.

    GitHub returns run logs as a ZIP archive.  This function downloads
    the archive and returns a mapping of log file names to their raw bytes
    so the caller can persist them for auditing.

    Args:
        repo:             Repository in ``owner/repo`` form.
        run_id:           Numeric workflow run ID.
        token:            GitHub token with ``repo`` scope.
        timeout_seconds:  HTTP read timeout (default: 60).

    Returns:
        ``(ok, result)`` where *result* is ``{"files": {filename: bytes}}``
        on success or an error dict on failure.
    """
    if not _HAS_REQUESTS:
        return False, {"error": "requests library not installed"}

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    logs_url = f"{_API}/repos/{repo}/actions/runs/{run_id}/logs"

    try:
        r = _requests.get(logs_url, headers=headers, timeout=timeout_seconds, stream=True)
    except Exception as exc:  # noqa: BLE001
        return False, {"error": "request_failed", "exception": str(exc)}

    if r.status_code != 200:
        return False, {
            "error": "logs_fetch_failed",
            "status": r.status_code,
            "body": r.text,
        }

    try:
        buf = io.BytesIO(r.content)
        with zipfile.ZipFile(buf) as z:
            files: dict[str, bytes] = {name: z.read(name) for name in z.namelist()}
        return True, {"files": files}
    except zipfile.BadZipFile as exc:
        return False, {"error": "zip_parse_failed", "exception": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return False, {"error": "unexpected_error", "exception": str(exc)}
