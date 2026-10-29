"""Test setup: isolated SQLite database, fake Gmail and fake Gemini. No network is used."""

import base64
import json
import os
import tempfile

_DB_DIR = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL=f"sqlite:///{_DB_DIR}/test.db",
    SESSION_SECRET="test-session-secret",
    TOKEN_ENCRYPTION_KEY="pY3oQb0n2m2yQf9n8wJ7l3v2G0jvJ9mH0y8b9kq1o6c=",
    GEMINI_API_KEY="",
    GOOGLE_CLIENT_ID="",
    GOOGLE_CLIENT_SECRET="",
    AUTO_CREATE_TASKS="false",
)

from datetime import datetime, timezone  # noqa: E402

import itsdangerous  # noqa: E402
import pytest  # noqa: E402
from fastapi import Depends  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_gmail, get_llm  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.db_models import GmailAccount  # noqa: E402
from app.models.schemas import LLMEmailAnalysis  # noqa: E402
from app.security import TokenCipher, get_current_account  # noqa: E402
from app.services.gmail_service import GmailNotFound  # noqa: E402
from app.services.llm_service import LLMError, LLMNotConfigured  # noqa: E402


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def gmail_message(msg_id, subject, body, sender="Prof. Rao <rao@university.edu>", labels=("INBOX", "UNREAD"), html=False):
    mime = "text/html" if html else "text/plain"
    return {
        "id": msg_id,
        "threadId": f"t-{msg_id}",
        "labelIds": list(labels),
        "snippet": body[:80],
        "internalDate": "1761645600000",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": "student@gmail.com"},
                {"name": "Subject", "value": subject},
            ],
            "parts": [{"mimeType": mime, "body": {"data": b64(body)}}],
        },
    }


class FakeGmail:
    """Stands in for GmailService; holds one account's mailbox."""

    def __init__(self, raw_messages):
        from app.services.gmail_parser import parse_message

        self.messages = {m["id"]: parse_message(m) for m in raw_messages}

    def get_profile(self):
        return {"emailAddress": "x", "messagesTotal": len(self.messages)}

    def list_messages(self, query="", page_token=None, max_results=15, label="INBOX"):
        ids = sorted(self.messages)
        start = int(page_token or 0)
        page = ids[start : start + max_results]
        nxt = str(start + max_results) if start + max_results < len(ids) else None
        return {"emails": [self.messages[i] for i in page], "next_page_token": nxt, "result_size_estimate": len(ids)}

    def get_message(self, message_id, full=True):
        if message_id not in self.messages:
            raise GmailNotFound("Message not found in this Gmail account.")
        return self.messages[message_id]

    def get_thread_context(self, thread_id, exclude_message_id, max_messages=3):
        return []


class FakeLLM:
    def __init__(self):
        self.analysis: LLMEmailAnalysis | None = None
        self.error: LLMError | None = None
        self.reply = "Dear Prof. Rao,\n\nThank you. I will submit the report by Friday at 5 PM.\n\nBest regards,\n[Your Name]"
        self.calls = 0

    def analyze_email(self, email):
        self.calls += 1
        if self.error:
            raise self.error
        return self.analysis

    def generate_reply(self, email, thread, tone="professional", instructions=None):
        if self.error:
            raise self.error
        return self.reply


REPORT_ANALYSIS = LLMEmailAnalysis(
    category="Academic",
    priority="High",
    priority_reason="The report has a firm deadline this week.",
    summary="The project report must be submitted by Friday at 5 PM.",
    action_required=True,
    response_required=False,
    task="Submit the project report",
    deadline_text="Friday at 5 PM",
)
PROMO_ANALYSIS = LLMEmailAnalysis(
    category="Promotion",
    priority="High",
    priority_reason="Limited time offer.",
    summary="A store advertises a 50% sale.",
    action_required=False,
    response_required=False,
)


def session_cookie(data: dict) -> str:
    signer = itsdangerous.TimestampSigner("test-session-secret")
    return signer.sign(base64.b64encode(json.dumps(data).encode())).decode()


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def make_account(db):
    cipher = TokenCipher(os.environ["TOKEN_ENCRYPTION_KEY"])

    def _make(email="student@gmail.com"):
        account = GmailAccount(
            email=email,
            encrypted_credentials=cipher.encrypt({"token": "t", "refresh_token": "r", "scopes": []}),
            scopes="https://www.googleapis.com/auth/gmail.readonly",
            connected_at=datetime.now(timezone.utc),
        )
        db.add(account)
        db.commit()
        return account

    return _make


@pytest.fixture
def mailboxes():
    """email address -> FakeGmail. Each account only ever sees its own mailbox."""
    return {
        "student@gmail.com": FakeGmail(
            [
                gmail_message("m1", "Project report", "Please submit the project report by Friday at 5 PM."),
                gmail_message("m2", "50% off sale", "Huge sale ends tonight!", sender="Shop <deals@shop.com>",
                              labels=("INBOX", "CATEGORY_PROMOTIONS")),
                gmail_message("m3", "Newsletter", "<p>Hello</p><script>alert(1)</script>", html=True),
            ]
        ),
        "other@gmail.com": FakeGmail([gmail_message("x1", "Private", "Other user's secret email")]),
    }


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def client(mailboxes, llm):
    def fake_gmail(account: GmailAccount = Depends(get_current_account)):
        return mailboxes[account.email]

    app.dependency_overrides[get_gmail] = fake_gmail
    app.dependency_overrides[get_llm] = lambda: llm
    with TestClient(app) as c:
        yield c


@pytest.fixture
def login(client):
    def _login(account):
        client.cookies.set("smart_email_session", session_cookie({"account_id": account.id}))
        return client

    return _login


@pytest.fixture
def settings_override():
    def _apply(**values):
        settings = Settings(**{**get_settings().model_dump(), **values})
        app.dependency_overrides[get_settings] = lambda: settings
        return settings

    return _apply


__all__ = ["LLMNotConfigured"]
