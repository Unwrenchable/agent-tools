"""Slack and Teams webhook notifier.

Sends plain messages via incoming webhooks and interactive Slack approval
messages (with Approve / Reject buttons) via the Slack Web API.

Environment variables
---------------------
SLACK_WEBHOOK         Slack incoming webhook URL (for simple messages).
SLACK_BOT_TOKEN       Slack bot token (``xoxb-…``) for interactive messages
                      via ``chat.postMessage``.  Requires ``chat:write`` scope.
SLACK_SIGNING_SECRET  Used by ``approval_ui.py`` to verify Slack callbacks.
TEAMS_WEBHOOK         Microsoft Teams incoming webhook URL.

If none of the env vars are set the notifier silently no-ops so code that
calls it always works regardless of environment.
"""
from __future__ import annotations

import os
from typing import Any

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:  # pragma: no cover
    _HAS_REQUESTS = False

_SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK", "")
_SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
_TEAMS_WEBHOOK = os.getenv("TEAMS_WEBHOOK", "")

_SLACK_API_URL = "https://slack.com/api/chat.postMessage"


class Notifier:
    """Send notifications to Slack and/or Microsoft Teams.

    Args:
        slack_webhook:  Override ``SLACK_WEBHOOK`` env var.
        teams_webhook:  Override ``TEAMS_WEBHOOK`` env var.
        bot_token:      Override ``SLACK_BOT_TOKEN`` env var.
    """

    def __init__(
        self,
        slack_webhook: str | None = None,
        teams_webhook: str | None = None,
        bot_token: str | None = None,
    ) -> None:
        self._slack_webhook = slack_webhook or _SLACK_WEBHOOK
        self._teams_webhook = teams_webhook or _TEAMS_WEBHOOK
        self._bot_token = bot_token or _SLACK_BOT_TOKEN

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def notify(self, message: str, title: str | None = None) -> None:
        """Send a plain-text notification to all configured channels.

        Args:
            message: Body of the notification.
            title:   Optional prefix shown before the message.
        """
        if self._slack_webhook:
            self._post_slack_webhook(message, title)
        if self._teams_webhook:
            self._post_teams(message, title)

    def send_interactive_approval(
        self,
        channel: str,
        text: str,
        approval_id: str,
        approve_url: str,
        reject_url: str,
    ) -> None:
        """Post an interactive Slack message with Approve / Reject buttons.

        Uses ``chat.postMessage`` (requires ``SLACK_BOT_TOKEN`` with
        ``chat:write`` scope).  Falls back to a plain webhook message if
        the bot token is not set.

        The buttons use ``url`` links so they work even without a public
        Slack action callback endpoint.  To receive interactive payloads
        instead, expose ``/slack/actions`` publicly and configure the Slack
        app interactivity URL accordingly.

        Args:
            channel:     Slack channel ID or name (e.g. ``#approvals``).
            text:        Fallback/header text for the message.
            approval_id: Approval request ID (used as button ``value``).
            approve_url: URL for the Approve button.
            reject_url:  URL for the Reject button.
        """
        if not self._bot_token:
            self._post_slack_webhook(text)
            return

        blocks: list[dict[str, Any]] = [
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Approve"},
                        "style": "primary",
                        "value": approval_id,
                        "action_id": "approve_action",
                        "url": approve_url,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Reject"},
                        "style": "danger",
                        "value": approval_id,
                        "action_id": "reject_action",
                        "url": reject_url,
                    },
                ],
            },
        ]
        payload = {"channel": channel, "text": text, "blocks": blocks}
        headers = {
            "Authorization": f"Bearer {self._bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        self._post(_SLACK_API_URL, payload, headers=headers)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _post_slack_webhook(self, message: str, title: str | None = None) -> None:
        if not self._slack_webhook:
            return
        text = f"{title}: {message}" if title else message
        self._post(self._slack_webhook, {"text": text})

    def _post_teams(self, message: str, title: str | None = None) -> None:
        if not self._teams_webhook:
            return
        payload: dict[str, Any] = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": title or "Notification",
            "themeColor": "0076D7",
            "title": title or "Notification",
            "text": message,
        }
        self._post(self._teams_webhook, payload)

    @staticmethod
    def _post(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        if not _HAS_REQUESTS:
            return
        try:
            _requests.post(url, json=payload, headers=headers, timeout=10)
        except Exception:  # noqa: BLE001
            pass
