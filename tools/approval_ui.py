#!/usr/bin/env python3
"""Minimal Flask approval UI for human-in-the-loop agent action reviews.

Agents submit approval requests via POST /request.  Humans open the web
UI, review pending requests, and click Approve or Reject.

When ``SLACK_BOT_TOKEN`` and ``SLACK_APPROVAL_CHANNEL`` are set the UI
also sends interactive Slack messages with Approve/Reject buttons.
Set ``SLACK_SIGNING_SECRET`` to verify inbound Slack action callbacks.

Requirements::

    pip install flask

Run::

    python tools/approval_ui.py
    # Open http://localhost:5001/

API summary
-----------
POST /request          — Create a new approval request.
                         Body: {"action": "…", "payload": {…}}
                         Returns 201 + JSON item.
GET  /api/requests     — List all requests as JSON.
POST /approve/<id>     — Approve a request.
POST /reject/<id>      — Reject a request.
POST /slack/actions    — Receive interactive Slack action callbacks.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

# Allow sibling modules to be imported when running directly as a script.
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from approval_store import create_request, get_request, list_requests, update_request

try:
    from flask import Flask, abort, jsonify, render_template_string, request
except ImportError as exc:
    print(
        "Flask is required to run the approval UI.\n"
        "Install it with:  pip install flask",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

# Notifier is optional — absence of env vars means it silently no-ops.
try:
    from notifier import Notifier as _Notifier
    _notifier: _Notifier | None = _Notifier()
except Exception:  # noqa: BLE001
    _notifier = None

app = Flask(__name__)

_INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Agent Approvals</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
    h1   { border-bottom: 2px solid #e0e0e0; padding-bottom: .5rem; }
    .item { border: 1px solid #ccc; border-radius: 6px; padding: 1rem; margin: 1rem 0; }
    .pending  { border-left: 4px solid #f59e0b; }
    .approved { border-left: 4px solid #10b981; }
    .rejected { border-left: 4px solid #ef4444; }
    pre { background: #f3f4f6; padding: .5rem; border-radius: 4px; overflow-x: auto; }
    button { padding: .4rem .9rem; border: none; border-radius: 4px; cursor: pointer; font-size: .9rem; }
    .approve-btn { background: #10b981; color: white; }
    .reject-btn  { background: #ef4444; color: white; margin-left: .5rem; }
  </style>
</head>
<body>
  <h1>&#128274; Agent Approval Queue</h1>
  {% if not items %}
    <p>No pending requests.</p>
  {% endif %}
  {% for it in items %}
  <div class="item {{ it.status }}">
    <strong>{{ it.action }}</strong>
    &nbsp;<small style="color:#888">{{ it.id }}</small>
    &nbsp;<span style="font-weight:bold">{{ it.status.upper() }}</span>
    <pre>{{ it.payload | tojson(indent=2) }}</pre>
    {% if it.status == 'pending' %}
    <form method="post" action="/approve/{{ it.id }}" style="display:inline">
      <button class="approve-btn" type="submit">&#10003; Approve</button>
    </form>
    <form method="post" action="/reject/{{ it.id }}" style="display:inline">
      <button class="reject-btn" type="submit">&#10007; Reject</button>
    </form>
    {% endif %}
  </div>
  {% endfor %}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Slack request verification
# ---------------------------------------------------------------------------

def _verify_slack_request(req) -> bool:
    """Verify an inbound Slack request using the signing secret.

    Returns ``True`` when ``SLACK_SIGNING_SECRET`` is not set (opt-in security).
    Returns ``False`` if the signature is missing, stale, or invalid.
    """
    signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        return True

    timestamp = req.headers.get("X-Slack-Request-Timestamp", "")
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False
    if abs(time.time() - ts) > 300:
        return False

    body = req.get_data(as_text=True)
    sig_base = f"v0:{timestamp}:{body}"
    expected = (
        "v0="
        + hmac.new(
            signing_secret.encode(),
            sig_base.encode(),
            hashlib.sha256,
        ).hexdigest()
    )
    slack_sig = req.headers.get("X-Slack-Signature", "")
    return hmac.compare_digest(expected, slack_sig)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    items = list_requests()
    return render_template_string(_INDEX_HTML, items=items)


@app.route("/api/requests")
def api_list():
    return jsonify(list_requests())


@app.route("/request", methods=["POST"])
def request_approval():
    body = request.get_json(force=True, silent=True)
    if not body or "action" not in body or "payload" not in body:
        abort(400, description="Body must contain 'action' and 'payload' keys.")
    item = create_request(action=body["action"], payload=body["payload"])

    # Send interactive Slack notification if configured.
    _try_send_slack_approval(item)

    return jsonify(item), 201


@app.route("/approve/<req_id>", methods=["POST"])
def approve(req_id: str):
    if not update_request(req_id, "approved"):
        abort(404)
    if request.accept_mimetypes.best == "application/json":
        return ("", 204)
    return (_redirect_to_index(), 303)


@app.route("/reject/<req_id>", methods=["POST"])
def reject(req_id: str):
    if not update_request(req_id, "rejected"):
        abort(404)
    if request.accept_mimetypes.best == "application/json":
        return ("", 204)
    return (_redirect_to_index(), 303)


@app.route("/slack/actions", methods=["POST"])
def slack_actions():
    """Receive interactive Slack button callbacks.

    Slack posts a form field named ``payload`` containing JSON.
    Requires the app interactivity URL to be set to
    ``https://<your-host>/slack/actions`` in the Slack app config.
    Set ``SLACK_SIGNING_SECRET`` to verify inbound requests.
    """
    if not _verify_slack_request(request):
        abort(403)

    raw = request.form.get("payload", "{}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        abort(400)

    actions = payload.get("actions", [])
    if not actions:
        return ("", 200)

    action = actions[0]
    action_id = action.get("action_id", "")
    req_id = action.get("value", "")

    if action_id == "approve_action" and req_id:
        update_request(req_id, "approved")
        if _notifier:
            _notifier.notify(f"Approval {req_id} approved via Slack")
    elif action_id == "reject_action" and req_id:
        update_request(req_id, "rejected")
        if _notifier:
            _notifier.notify(f"Approval {req_id} rejected via Slack")

    return ("", 200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _try_send_slack_approval(item: dict) -> None:
    """Fire-and-forget: send interactive Slack approval message if configured."""
    if _notifier is None:
        return
    channel = os.getenv("SLACK_APPROVAL_CHANNEL", "")
    if not channel:
        return
    base_url = os.getenv("APPROVAL_PUBLIC_BASE", "http://localhost:5001")
    try:
        _notifier.send_interactive_approval(
            channel=channel,
            text=f"Approval requested: `{item['action']}` — id `{item['id']}`",
            approval_id=item["id"],
            approve_url=f"{base_url}/approve/{item['id']}",
            reject_url=f"{base_url}/reject/{item['id']}",
        )
    except Exception:  # noqa: BLE001
        pass


def _redirect_to_index():
    from flask import redirect, url_for  # noqa: PLC0415
    return redirect(url_for("index"))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Agent approval UI")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode (development only — never use in production)",
    )
    args = parser.parse_args()
    print(f"Starting approval UI at http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=args.debug)

