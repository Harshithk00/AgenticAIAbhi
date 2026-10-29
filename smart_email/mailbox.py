"""A small, file-backed mailbox the agent operates on.

The agent never sends mail. It reads, labels, prioritises, archives and
writes *drafts*; a human reviews drafts before anything leaves the inbox.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

CATEGORIES = (
    "urgent",
    "action_required",
    "meeting",
    "finance",
    "newsletter",
    "promotion",
    "personal",
    "notification",
    "suspicious",
    "other",
)
PRIORITIES = ("high", "medium", "low")


@dataclass
class Email:
    id: str
    sender: str
    subject: str
    body: str
    received_at: str
    to: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    category: str | None = None
    priority: str | None = None
    summary: str | None = None
    archived: bool = False
    follow_up: str | None = None

    def preview(self, length: int = 160) -> dict:
        snippet = " ".join(self.body.split())
        return {
            "id": self.id,
            "from": self.sender,
            "subject": self.subject,
            "received_at": self.received_at,
            "snippet": snippet[:length] + ("..." if len(snippet) > length else ""),
            "category": self.category,
            "priority": self.priority,
            "labels": self.labels,
        }


@dataclass
class Draft:
    email_id: str
    to: str
    subject: str
    body: str
    created_at: str


class MailboxError(ValueError):
    """Raised for invalid mailbox operations; surfaced to the agent as a tool error."""


class Mailbox:
    """Inbox state loaded from (and saved back to) a JSON file."""

    def __init__(self, emails: list[Email], drafts: list[Draft] | None = None, path: Path | None = None):
        self.emails = {e.id: e for e in emails}
        self.drafts = drafts or []
        self.path = path

    @classmethod
    def load(cls, path: str | Path) -> "Mailbox":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        emails = [Email(**e) for e in data.get("emails", [])]
        drafts = [Draft(**d) for d in data.get("drafts", [])]
        return cls(emails, drafts, path)

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self.path
        if target is None:
            raise MailboxError("No path to save the mailbox to.")
        payload = {
            "emails": [asdict(e) for e in self.emails.values()],
            "drafts": [asdict(d) for d in self.drafts],
        }
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return target

    def get(self, email_id: str) -> Email:
        try:
            return self.emails[email_id]
        except KeyError:
            raise MailboxError(f"No email with id {email_id!r}.") from None

    def list(self, include_archived: bool = False, only_untriaged: bool = False) -> list[Email]:
        emails = [e for e in self.emails.values() if include_archived or not e.archived]
        if only_untriaged:
            emails = [e for e in emails if e.category is None]
        return sorted(emails, key=lambda e: e.received_at, reverse=True)

    def search(self, query: str) -> list[Email]:
        q = query.lower()
        return [
            e
            for e in self.list(include_archived=True)
            if q in e.subject.lower() or q in e.sender.lower() or q in e.body.lower()
        ]

    def categorize(self, email_id: str, category: str, priority: str, summary: str) -> Email:
        if category not in CATEGORIES:
            raise MailboxError(f"Unknown category {category!r}; use one of {', '.join(CATEGORIES)}.")
        if priority not in PRIORITIES:
            raise MailboxError(f"Unknown priority {priority!r}; use one of {', '.join(PRIORITIES)}.")
        email = self.get(email_id)
        email.category = category
        email.priority = priority
        email.summary = summary.strip()
        return email

    def add_labels(self, email_id: str, labels: list[str]) -> Email:
        email = self.get(email_id)
        for label in labels:
            label = label.strip().lower()
            if label and label not in email.labels:
                email.labels.append(label)
        return email

    def archive(self, email_id: str) -> Email:
        email = self.get(email_id)
        if email.priority == "high":
            raise MailboxError("Refusing to archive a high-priority email; leave it in the inbox.")
        email.archived = True
        return email

    def set_follow_up(self, email_id: str, due_date: str, note: str) -> Email:
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            raise MailboxError("due_date must be in YYYY-MM-DD format.") from None
        email = self.get(email_id)
        email.follow_up = f"{due_date}: {note.strip()}"
        return email

    def create_draft(self, email_id: str, body: str) -> Draft:
        email = self.get(email_id)
        if email.category == "suspicious":
            raise MailboxError("Will not draft a reply to an email flagged as suspicious.")
        subject = email.subject if email.subject.lower().startswith("re:") else f"Re: {email.subject}"
        draft = Draft(
            email_id=email_id,
            to=email.sender,
            subject=subject,
            body=body.strip(),
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        # One draft per email: a newer draft replaces the older one.
        self.drafts = [d for d in self.drafts if d.email_id != email_id] + [draft]
        return draft
