"""Drive EmailAgent end to end against a fake Messages API (no network, no API key)."""

import json

import anthropic
import httpx2 as httpx

from smart_email.agent import EmailAgent
from smart_email.mailbox import Email, Mailbox


def _message(content, stop_reason):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def test_agent_runs_tools_and_returns_briefing():
    requests = []
    replies = [
        _message(
            [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "categorize_email",
                    "input": {"email_id": "e1", "category": "meeting", "priority": "medium", "summary": "Sync request."},
                },
                {"type": "tool_use", "id": "toolu_2", "name": "draft_reply", "input": {"email_id": "e1", "body": "Thursday works."}},
            ],
            "tool_use",
        ),
        _message([{"type": "text", "text": "One meeting request; a draft is ready."}], "end_turn"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=replies[len(requests) - 1])

    client = anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    mailbox = Mailbox([Email(id="e1", sender="a@b.com", subject="Sync?", body="Thursday?", received_at="2026-10-28T00:00:00Z")])
    calls = []

    reply = EmailAgent(mailbox, client=client).triage(lambda name, args: calls.append(name))

    assert reply == "One meeting request; a draft is ready."
    assert calls == ["categorize_email", "draft_reply"]
    assert mailbox.get("e1").category == "meeting"
    assert mailbox.drafts[0].body == "Thursday works."

    first, second = requests
    assert first["model"] == "claude-opus-5-5"
    assert first["thinking"] == {"type": "adaptive"}
    assert first["fallbacks"] == "default"
    assert {t["name"] for t in first["tools"]} >= {"categorize_email", "draft_reply", "archive_email"}
    results = second["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["toolu_1", "toolu_2"]
    assert not any(r.get("is_error") for r in results)
