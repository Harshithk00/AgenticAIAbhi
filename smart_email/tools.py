"""Claude tools that let the agent operate on a Mailbox."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from functools import wraps

from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from .mailbox import Mailbox, MailboxError


def _tool_errors(func: Callable[..., str]) -> Callable[..., str]:
    """Report MailboxError to Claude as a tool error it can recover from."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except MailboxError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def build_tools(mailbox: Mailbox) -> list:
    """Create the tool set, bound to one mailbox instance."""

    @beta_tool
    @_tool_errors
    def list_emails(only_untriaged: bool = False, include_archived: bool = False) -> str:
        """List emails in the inbox, newest first, as short previews.

        Args:
            only_untriaged: If true, return only emails that have not been categorized yet.
            include_archived: If true, also include archived emails.
        """
        emails = mailbox.list(include_archived=include_archived, only_untriaged=only_untriaged)
        return json.dumps([e.preview() for e in emails])

    @beta_tool
    @_tool_errors
    def read_email(email_id: str) -> str:
        """Read the full content and current triage state of one email.

        Args:
            email_id: The id of the email to read.
        """
        return json.dumps(asdict(mailbox.get(email_id)))

    @beta_tool
    @_tool_errors
    def search_emails(query: str) -> str:
        """Case-insensitive search across sender, subject and body of all emails.

        Args:
            query: Text to search for.
        """
        return json.dumps([e.preview() for e in mailbox.search(query)])

    @beta_tool
    @_tool_errors
    def categorize_email(email_id: str, category: str, priority: str, summary: str) -> str:
        """Record the triage result for an email: its category, priority and a one-sentence summary.

        Args:
            email_id: The id of the email.
            category: One of: urgent, action_required, meeting, finance, newsletter, promotion,
                personal, notification, suspicious, other.
            priority: One of: high, medium, low.
            summary: One sentence saying what the email is about and what (if anything) the user must do.
        """
        email = mailbox.categorize(email_id, category, priority, summary)
        return f"Categorized {email.id} as {email.category} ({email.priority})."

    @beta_tool
    @_tool_errors
    def apply_labels(email_id: str, labels: list[str]) -> str:
        """Attach free-form labels (e.g. project or client names) to an email.

        Args:
            email_id: The id of the email.
            labels: Short lowercase labels to add.
        """
        email = mailbox.add_labels(email_id, labels)
        return f"Labels on {email.id}: {', '.join(email.labels)}."

    @beta_tool
    @_tool_errors
    def archive_email(email_id: str) -> str:
        """Archive an email that needs no further attention (e.g. read newsletters, promotions, notifications).
        High-priority emails cannot be archived.

        Args:
            email_id: The id of the email.
        """
        mailbox.archive(email_id)
        return f"Archived {email_id}."

    @beta_tool
    @_tool_errors
    def set_follow_up(email_id: str, due_date: str, note: str) -> str:
        """Set a follow-up reminder for an email with a deadline or a pending task.

        Args:
            email_id: The id of the email.
            due_date: Due date in YYYY-MM-DD format.
            note: What needs to be done by then.
        """
        email = mailbox.set_follow_up(email_id, due_date, note)
        return f"Follow-up set on {email.id}: {email.follow_up}"

    @beta_tool
    @_tool_errors
    def draft_reply(email_id: str, body: str) -> str:
        """Save a reply draft for the user to review. This never sends the email.

        Args:
            email_id: The id of the email being replied to.
            body: The full reply text, including greeting and sign-off.
        """
        draft = mailbox.create_draft(email_id, body)
        return f"Draft saved for {draft.email_id} to {draft.to} ({draft.subject!r})."

    return [
        list_emails,
        read_email,
        search_emails,
        categorize_email,
        apply_labels,
        archive_email,
        set_follow_up,
        draft_reply,
    ]
