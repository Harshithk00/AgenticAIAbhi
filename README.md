# Smart Email Management Using Agentic AI

An AI agent that manages an email inbox. Claude reads each email and decides what to do with it, then
acts through a set of mailbox tools. It can:

- **Classify** emails into a category (urgent, action_required, meeting, finance, newsletter,
  promotion, personal, notification, suspicious, other) and a priority (high / medium / low)
- **Summarise** each email in one sentence
- **Label** emails by project, client or topic
- **Detect phishing** and flag it as `suspicious` (it never replies to these or follows
  instructions written inside an email)
- **Set follow-ups** for deadlines and requests
- **Draft replies** for a human to review. Nothing is ever sent automatically
- **Archive** newsletters, promotions and notifications that need no action
- Answer **free-form requests** such as "what do I owe this month?" or "draft a reply to Rahul
  proposing Thursday 3pm"

## How it works

```
 you ──instruction──▶ EmailAgent ──▶ Claude (tool runner loop)
                                        │  decides which tool to call next
                                        ▼
       list_emails · read_email · search_emails · categorize_email · apply_labels
       archive_email · set_follow_up · draft_reply
                                        │
                                        ▼
                               Mailbox (data/*.json)
```

The agent uses the Anthropic Python SDK's **tool runner**
(`client.beta.messages.tool_runner`). Each tool is a typed Python function decorated with
`@beta_tool`, and the SDK generates its JSON schema from the signature and docstring. Claude
calls the tools in a loop (read, then decide, then act) until the inbox is triaged, and then
writes a short briefing.

Guardrails are enforced in code as well as in the prompt:

| Rule | Where |
|---|---|
| Drafts only, never sends | no send tool exists |
| No replies to suspicious emails | `Mailbox.create_draft` |
| High-priority emails can't be archived | `Mailbox.archive` |
| Invalid category / priority / date rejected | `Mailbox.categorize`, `set_follow_up` |
| Email text treated as untrusted data | system prompt |

Invalid operations come back to Claude as tool errors, so it can correct itself.

## Project layout

```
smart_email/
  mailbox.py   Email / Draft models and the JSON-backed Mailbox
  tools.py     The @beta_tool functions bound to a Mailbox
  agent.py     EmailAgent: system prompt + tool runner
  cli.py       Command-line interface
data/sample_inbox.json   Nine example emails (work, phishing, invoice, newsletter, ...)
tests/                   Unit tests and an end-to-end agent test against a mocked API
```

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # or sign in with `ant auth login`
```

## Usage

```bash
# Let the agent triage the inbox (writes results to a copy so the sample stays pristine)
python -m smart_email triage --output data/triaged.out.json

# Look at the result, most important first, then the reply drafts
python -m smart_email --inbox data/triaged.out.json show --all
python -m smart_email --inbox data/triaged.out.json drafts

# Ask anything about your inbox
python -m smart_email --inbox data/triaged.out.json ask "Which bills are due this month?"
python -m smart_email --inbox data/triaged.out.json ask "Draft a reply to Rahul proposing Thursday 3pm"
```

Options for `triage` and `ask`: `--model` (default `claude-opus-5-5`), `--effort`
(`low`…`max`, default `medium`), `--output`, `-q/--quiet` (hide the tool calls).

Using it from Python:

```python
from smart_email import Mailbox
from smart_email.agent import EmailAgent

mailbox = Mailbox.load("data/sample_inbox.json")
print(EmailAgent(mailbox).triage())
mailbox.save("data/triaged.out.json")
```

The request enables the API's server-side refusal fallback (`fallbacks: "default"`), so a request
that a safety classifier declines is retried on a fallback model in the same call. That case is
rare for email, but phishing text can trip it.

## Inbox format

```json
{
  "emails": [
    {"id": "e001", "sender": "a@b.com", "to": ["me@example.com"], "subject": "...",
     "body": "...", "received_at": "2026-10-28T09:15:00Z"}
  ],
  "drafts": []
}
```

The agent fills in `category`, `priority`, `summary`, `labels`, `follow_up` and `archived`. To
work on real mail, export your messages into this format (for example with Python's `imaplib`),
or write another class with the same methods as `Mailbox`.

## Tests

```bash
python -m pytest -q
```

The tests need no API key. `tests/test_agent.py` runs the whole tool loop against a fake Messages
API.
