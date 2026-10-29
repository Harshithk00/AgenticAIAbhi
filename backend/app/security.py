"""Credential encryption, OAuth state checks and the current-account dependency."""

from __future__ import annotations

import hmac
import json
import secrets

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .models.db_models import GmailAccount

SESSION_ACCOUNT_KEY = "account_id"
SESSION_OAUTH_STATE_KEY = "oauth_state"
SESSION_CODE_VERIFIER_KEY = "oauth_code_verifier"


class TokenCipher:
    """Encrypts OAuth credentials at rest with a Fernet key from TOKEN_ENCRYPTION_KEY."""

    def __init__(self, key: str):
        if not key:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY is not set. Generate one with: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        self._fernet = Fernet(key.encode())

    def encrypt(self, data: dict) -> str:
        return self._fernet.encrypt(json.dumps(data).encode()).decode()

    def decrypt(self, token: str) -> dict:
        try:
            return json.loads(self._fernet.decrypt(token.encode()))
        except InvalidToken as exc:
            raise RuntimeError("Stored credentials could not be decrypted (was TOKEN_ENCRYPTION_KEY changed?)") from exc


def get_cipher(settings: Settings = Depends(get_settings)) -> TokenCipher:
    try:
        return TokenCipher(settings.token_encryption_key)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "server_misconfigured", "message": "TOKEN_ENCRYPTION_KEY is missing or invalid in backend/.env."},
        ) from exc


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def oauth_state_is_valid(expected: str | None, received: str | None) -> bool:
    """Constant-time comparison of the state we issued with the state Google sent back."""
    if not expected or not received:
        return False
    return hmac.compare_digest(expected, received)


def get_current_account(request: Request, db: Session = Depends(get_db)) -> GmailAccount:
    """The Gmail account bound to this browser session. Every account-specific route depends on this."""
    account_id = request.session.get(SESSION_ACCOUNT_KEY)
    account = db.get(GmailAccount, account_id) if account_id else None
    if account is None or not account.is_connected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "not_connected", "message": "Connect your Gmail account first."},
        )
    return account
