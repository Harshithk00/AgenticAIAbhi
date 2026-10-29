"""Read-only access to Gmail through the official Gmail API client."""

from __future__ import annotations

import logging
from datetime import timezone

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..config import GMAIL_READONLY_SCOPE, Settings
from .gmail_parser import parse_message

log = logging.getLogger(__name__)

TOKEN_URI = "https://oauth2.googleapis.com/token"


class GmailError(Exception):
    """Generic Gmail API failure."""


class GmailAuthError(GmailError):
    """The stored credentials are expired, revoked or invalid: the user must reconnect."""


class GmailNotFound(GmailError):
    """The message doesn't exist in this account (or belongs to someone else)."""


def credentials_from_dict(data: dict, settings: Settings) -> Credentials:
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", TOKEN_URI),
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=data.get("scopes") or [GMAIL_READONLY_SCOPE],
    )
    if data.get("expiry"):
        from datetime import datetime

        creds.expiry = datetime.fromisoformat(data["expiry"]).replace(tzinfo=None)  # google-auth uses naive UTC
    return creds


def credentials_to_dict(creds: Credentials) -> dict:
    """Serialisable form for encrypted storage. The client secret is deliberately left out."""
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "scopes": list(creds.scopes or []),
        "expiry": creds.expiry.replace(tzinfo=timezone.utc).isoformat() if creds.expiry else None,
    }


def _translate(exc: HttpError) -> GmailError:
    status = getattr(exc.resp, "status", None)
    if status in (400, 404):
        return GmailNotFound("Message not found in this Gmail account.")
    if status in (401, 403):
        return GmailAuthError("Gmail access was denied or revoked. Please reconnect your account.")
    if status == 429:
        return GmailError("Gmail rate limit reached. Please wait a moment and try again.")
    return GmailError(f"Gmail API error (HTTP {status}). Please try again.")


class GmailService:
    """Wraps one account's Gmail API client. Only read methods exist; nothing is sent or modified."""

    def __init__(self, credentials: Credentials, api=None):
        self.credentials = credentials
        self._api = api  # injected in tests

    @property
    def api(self):
        if self._api is None:
            self._api = build("gmail", "v1", credentials=self.credentials, cache_discovery=False)
        return self._api

    def ensure_fresh(self) -> bool:
        """Refresh the access token if it has expired. Returns True if it changed."""
        if self.credentials.valid:
            return False
        if not self.credentials.refresh_token:
            raise GmailAuthError("Gmail session expired. Please reconnect your account.")
        try:
            self.credentials.refresh(GoogleRequest())
        except RefreshError as exc:
            raise GmailAuthError("Gmail access was revoked or expired. Please reconnect your account.") from exc
        return True

    def _execute(self, request):
        try:
            return request.execute()
        except HttpError as exc:
            raise _translate(exc) from exc
        except RefreshError as exc:
            raise GmailAuthError("Gmail access was revoked or expired. Please reconnect your account.") from exc
        except OSError as exc:  # network problems
            raise GmailError("Could not reach Gmail. Check your internet connection.") from exc

    def get_profile(self) -> dict:
        return self._execute(self.api.users().getProfile(userId="me"))

    def list_messages(
        self, query: str = "", page_token: str | None = None, max_results: int = 15, label: str | None = "INBOX"
    ) -> dict:
        """One page of messages with headers and snippet (bodies are not downloaded here)."""
        params = {"userId": "me", "maxResults": max(1, min(max_results, 50))}
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token
        if label:
            params["labelIds"] = [label]
        listing = self._execute(self.api.users().messages().list(**params))

        emails = []
        for ref in listing.get("messages", []) or []:
            try:
                emails.append(self.get_message(ref["id"], full=False))
            except GmailNotFound:
                continue  # deleted between list and get
        return {
            "emails": emails,
            "next_page_token": listing.get("nextPageToken"),
            "result_size_estimate": listing.get("resultSizeEstimate", len(emails)),
        }

    def get_message(self, message_id: str, full: bool = True) -> dict:
        if full:
            request = self.api.users().messages().get(userId="me", id=message_id, format="full")
        else:
            request = self.api.users().messages().get(
                userId="me", id=message_id, format="metadata", metadataHeaders=["From", "To", "Subject", "Date"]
            )
        return parse_message(self._execute(request))

    def get_thread_context(self, thread_id: str, exclude_message_id: str, max_messages: int = 3) -> list[dict]:
        """Earlier messages in the same thread, oldest first, for reply context."""
        thread = self._execute(self.api.users().threads().get(userId="me", id=thread_id, format="full"))
        messages = [parse_message(m) for m in thread.get("messages", []) if m.get("id") != exclude_message_id]
        return messages[-max_messages:]
