"""Builds a GmailService for an account and keeps refreshed tokens persisted."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import Settings
from ..models.db_models import GmailAccount
from ..security import TokenCipher
from .gmail_service import GmailAuthError, GmailService, credentials_from_dict, credentials_to_dict


def gmail_for_account(db: Session, account: GmailAccount, cipher: TokenCipher, settings: Settings) -> GmailService:
    if not account.encrypted_credentials:
        raise GmailAuthError("Gmail is not connected.")
    creds = credentials_from_dict(cipher.decrypt(account.encrypted_credentials), settings)
    service = GmailService(creds)
    if service.ensure_fresh():
        account.encrypted_credentials = cipher.encrypt(credentials_to_dict(creds))
        db.commit()
    return service
