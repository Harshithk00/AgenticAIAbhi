import json
import shutil
from pathlib import Path

import pytest
from anthropic.lib.tools import ToolError

from smart_email.mailbox import CATEGORIES, Mailbox, MailboxError
from smart_email.tools import build_tools

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_inbox.json"


@pytest.fixture
def mailbox(tmp_path):
    path = tmp_path / "inbox.json"
    shutil.copy(SAMPLE, path)
    return Mailbox.load(path)


@pytest.fixture
def tools(mailbox):
    return {t.name: t for t in build_tools(mailbox)}


def test_list_is_newest_first(mailbox):
    emails = mailbox.list()
    assert emails[0].id == "e009"
    assert [e.received_at for e in emails] == sorted((e.received_at for e in emails), reverse=True)


def test_categorize_validates_values(mailbox):
    mailbox.categorize("e001", "action_required", "high", "Review the Q4 budget by Friday.")
    assert mailbox.get("e001").category == "action_required"
    with pytest.raises(MailboxError):
        mailbox.categorize("e001", "spam-ish", "high", "x")
    with pytest.raises(MailboxError):
        mailbox.categorize("e001", "other", "critical", "x")


def test_untriaged_filter(mailbox):
    mailbox.categorize("e003", "newsletter", "low", "Weekly tech newsletter.")
    assert "e003" not in {e.id for e in mailbox.list(only_untriaged=True)}


def test_cannot_archive_high_priority(mailbox):
    mailbox.categorize("e009", "urgent", "high", "Payment service outage.")
    with pytest.raises(MailboxError):
        mailbox.archive("e009")
    mailbox.archive("e006")
    assert "e006" not in {e.id for e in mailbox.list()}


def test_no_drafts_to_suspicious_email(mailbox):
    mailbox.categorize("e002", "suspicious", "high", "Phishing attempt.")
    with pytest.raises(MailboxError):
        mailbox.create_draft("e002", "Here is my password")


def test_draft_replaces_previous(mailbox):
    mailbox.create_draft("e004", "First")
    draft = mailbox.create_draft("e004", "Second")
    assert draft.subject == "Re: Sync on Acme migration timeline?"
    assert [d.body for d in mailbox.drafts] == ["Second"]


def test_follow_up_date_format(mailbox):
    mailbox.set_follow_up("e001", "2026-10-30", "Send budget comments")
    assert mailbox.get("e001").follow_up == "2026-10-30: Send budget comments"
    with pytest.raises(MailboxError):
        mailbox.set_follow_up("e001", "Friday", "x")


def test_save_round_trip(mailbox):
    mailbox.add_labels("e001", ["Acme", "acme", "proposal"])
    mailbox.create_draft("e008", "Yes, see you Sunday!")
    mailbox.save()
    reloaded = Mailbox.load(mailbox.path)
    assert reloaded.get("e001").labels == ["acme", "proposal"]
    assert reloaded.drafts[0].to == "mom@familymail.com"


def test_tools_operate_on_mailbox(mailbox, tools):
    previews = json.loads(tools["list_emails"].call({"only_untriaged": True}))
    assert len(previews) == 9
    tools["categorize_email"].call(
        {"email_id": "e005", "category": "finance", "priority": "medium", "summary": "October invoice."}
    )
    assert mailbox.get("e005").category == "finance"
    assert json.loads(tools["search_emails"].call({"query": "invoice"}))[0]["id"] == "e005"


def test_tool_errors_are_reported_as_tool_errors(tools):
    with pytest.raises(ToolError):
        tools["read_email"].call({"email_id": "missing"})


def test_category_description_lists_every_category(tools):
    description = tools["categorize_email"].input_schema["properties"]["category"]["description"]
    for category in CATEGORIES:
        assert category in description
