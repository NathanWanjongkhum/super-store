"""Weekly action-item digest senders. DRY RUN ONLY: nothing is ever sent.

The senders build the full message payload, log it and return it. They make no
network calls and read no credentials. A real implementation would plug in at
`send()`: e.g. `smtplib.SMTP(...).send_message()` for email, or an HTTPS POST to
a Slack incoming webhook (`chat.postMessage`) for Slack, with secrets read from
the environment or a secrets manager.
"""

import json
import logging
from dataclasses import dataclass

from super_store.actions import Action

log = logging.getLogger(__name__)

STATUS_LABELS = {"red": "Off track", "yellow": "Monitor"}
SLACK_EMOJI = {"red": ":red_circle:", "yellow": ":large_yellow_circle:"}


def subject(title: str, actions: list[Action]) -> str:
    red = sum(a.status == "red" for a in actions)
    return f"{title}: {len(actions)} action items ({red} need action)"


def action_line(a: Action) -> str:
    """e.g. "[Off track] Tables lost $30.5K ... · Avg discount ... (Furniture Category Manager, ...)"."""
    return f"[{STATUS_LABELS.get(a.status, a.status)}] {a.what} · {a.why} ({a.who}, {a.when})"


@dataclass
class DryRunEmailSender:
    """Builds an email (subject, plain-text body) and logs it. No SMTP, no credentials."""
    to: str = "exec-team@example.com"
    sender: str = "superstore-digest@example.com"

    def build(self, title: str, summary: list[str], actions: list[Action]) -> dict:
        lines = [title, "", *summary, "", "Action items:"]
        items = [f"{i}. {action_line(a)}" for i, a in enumerate(actions, 1)]
        lines += items or ["None: every KPI is on track."]
        return {"from": self.sender, "to": self.to, "subject": subject(title, actions),
                "body": "\n".join(lines)}

    def send(self, title: str, summary: list[str], actions: list[Action]) -> dict:
        payload = self.build(title, summary, actions)
        # A real sender would call smtplib here; this one deliberately does not.
        log.info("DRY RUN, email not sent:\n%s", json.dumps(payload, indent=2, ensure_ascii=False))
        return payload


@dataclass
class DryRunSlackSender:
    """Builds a Slack Block Kit message and logs it. No webhook call, no token."""
    channel: str = "#exec-summary"

    def build(self, title: str, summary: list[str], actions: list[Action]) -> dict:
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": title}},
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(summary)}},
            {"type": "divider"},
        ]
        for a in actions:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
                f"{SLACK_EMOJI.get(a.status, '')} *{a.what}* · {a.why}\n:bust_in_silhouette: {a.who}"
                f"  :calendar: {a.when}"}})
        if not actions:
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                                                       "text": "Every KPI is on track."}})
        return {"channel": self.channel, "text": subject(title, actions), "blocks": blocks}

    def send(self, title: str, summary: list[str], actions: list[Action]) -> dict:
        payload = self.build(title, summary, actions)
        # A real sender would POST to a Slack webhook here; this one deliberately does not.
        log.info("DRY RUN, Slack message not sent:\n%s", json.dumps(payload, indent=2, ensure_ascii=False))
        return payload
