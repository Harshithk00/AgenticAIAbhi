"""Google OAuth 2.0 (authorization code flow with PKCE) for read-only Gmail access."""

from __future__ import annotations

import logging
import os

import requests
from google_auth_oauthlib.flow import Flow

from ..config import GMAIL_READONLY_SCOPE, Settings

log = logging.getLogger(__name__)

SCOPES = [GMAIL_READONLY_SCOPE]
REVOKE_URL = "https://oauth2.googleapis.com/revoke"


class OAuthConfigError(RuntimeError):
    pass


def _client_config(settings: Settings) -> dict:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def make_flow(settings: Settings, state: str | None = None, code_verifier: str | None = None) -> Flow:
    if not settings.google_oauth_configured:
        raise OAuthConfigError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are not configured on the server.")
    if settings.google_redirect_uri.startswith("http://localhost") or settings.google_redirect_uri.startswith(
        "http://127.0.0.1"
    ):
        # oauthlib refuses plain HTTP by default; Google allows it for localhost during development only.
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    flow = Flow.from_client_config(
        _client_config(settings), scopes=SCOPES, state=state, redirect_uri=settings.google_redirect_uri
    )
    if code_verifier:
        flow.code_verifier = code_verifier
    return flow


def authorization_url(settings: Settings, state: str) -> tuple[str, str]:
    """Return (url, code_verifier). The verifier is kept server-side in the session for the callback."""
    flow = make_flow(settings, state=state)
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="false")
    return url, flow.code_verifier


def exchange_code(settings: Settings, state: str, code: str, code_verifier: str | None):
    flow = make_flow(settings, state=state, code_verifier=code_verifier)
    flow.fetch_token(code=code)
    return flow.credentials


def revoke(token: str | None) -> None:
    """Best-effort revocation at Google. Local credentials are deleted regardless."""
    if not token:
        return
    try:
        requests.post(REVOKE_URL, params={"token": token}, timeout=10)
    except requests.RequestException:
        log.warning("Could not reach Google to revoke the token; local credentials were still removed.")
