from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from app.security import oauth_state_is_valid
from app.services import oauth_service
from app.services.gmail_service import GmailService

OAUTH = dict(google_client_id="cid.apps.googleusercontent.com", google_client_secret="secret")


def test_state_comparison():
    assert oauth_state_is_valid("abc", "abc")
    assert not oauth_state_is_valid("abc", "abd")
    assert not oauth_state_is_valid(None, "abc")
    assert not oauth_state_is_valid("abc", None)


def test_oauth_not_configured(client):
    response = client.get("/api/auth/google", follow_redirects=False)
    assert response.status_code == 503


def _start(client):
    response = client.get("/api/auth/google", follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"]
    return query["state"][0]


def test_callback_rejects_wrong_state(client, settings_override, monkeypatch):
    settings_override(**OAUTH)
    called = []
    monkeypatch.setattr(oauth_service, "exchange_code", lambda *a: called.append(1))
    _start(client)
    response = client.get("/api/auth/google/callback", params={"state": "forged", "code": "c"}, follow_redirects=False)
    assert "auth_error=invalid_state" in response.headers["location"]
    assert called == []  # code is never exchanged on a state mismatch


def test_callback_handles_denied_consent(client, settings_override):
    settings_override(**OAUTH)
    state = _start(client)
    response = client.get("/api/auth/google/callback", params={"state": state, "error": "access_denied"},
                          follow_redirects=False)
    assert "auth_error=access_denied" in response.headers["location"]


def test_successful_callback_connects_account(client, settings_override, monkeypatch, db):
    settings_override(**OAUTH)
    creds = SimpleNamespace(token="access", refresh_token="refresh", token_uri="https://oauth2.googleapis.com/token",
                            scopes=["https://www.googleapis.com/auth/gmail.readonly"], expiry=None)
    monkeypatch.setattr(oauth_service, "exchange_code", lambda settings, state, code, verifier: creds)
    monkeypatch.setattr(GmailService, "get_profile", lambda self: {"emailAddress": "Student@Gmail.com"})

    state = _start(client)
    response = client.get("/api/auth/google/callback", params={"state": state, "code": "c"}, follow_redirects=False)
    assert response.headers["location"].endswith("/?connected=1")
    status = client.get("/api/auth/status").json()
    assert status["connected"] is True and status["email"] == "student@gmail.com"

    from app.models.db_models import GmailAccount

    account = db.query(GmailAccount).one()
    assert "refresh" not in account.encrypted_credentials  # stored encrypted, not in plain text
    # Replaying the same callback fails: the state is single-use.
    replay = client.get("/api/auth/google/callback", params={"state": state, "code": "c"}, follow_redirects=False)
    assert "auth_error=invalid_state" in replay.headers["location"]


def test_access_log_redacts_oauth_code():
    import logging

    from app.main import RedactOAuthQuery

    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                               ("127.0.0.1", "GET", "/api/auth/google/callback?state=s&code=SECRET", "1.1", 302), None)
    RedactOAuthQuery().filter(record)
    assert "SECRET" not in record.getMessage()
