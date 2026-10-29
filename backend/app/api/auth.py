"""OAuth routes: connect, callback, status, disconnect."""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from oauthlib.oauth2.rfc6749.errors import OAuth2Error
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..models.db_models import GmailAccount
from ..models.schemas import AuthStatus
from ..security import (
    SESSION_ACCOUNT_KEY,
    SESSION_CODE_VERIFIER_KEY,
    SESSION_OAUTH_STATE_KEY,
    TokenCipher,
    get_cipher,
    new_oauth_state,
    oauth_state_is_valid,
)
from ..services import oauth_service
from ..services.gmail_service import GmailError, GmailService, credentials_to_dict

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _frontend(settings: Settings, path: str = "/", **params) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{settings.frontend_origin}{path}{query}", status_code=302)


@router.get("/google")
def start_google_oauth(request: Request, settings: Settings = Depends(get_settings)):
    """Redirect the browser to Google's consent screen."""
    try:
        state = new_oauth_state()
        url, verifier = oauth_service.authorization_url(settings, state)
    except oauth_service.OAuthConfigError as exc:
        raise HTTPException(503, detail={"code": "oauth_not_configured", "message": str(exc)}) from exc
    request.session[SESSION_OAUTH_STATE_KEY] = state
    request.session[SESSION_CODE_VERIFIER_KEY] = verifier
    return RedirectResponse(url, status_code=302)


@router.get("/google/callback")
def google_oauth_callback(
    request: Request,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    cipher: TokenCipher = Depends(get_cipher),
    settings: Settings = Depends(get_settings),
):
    expected_state = request.session.pop(SESSION_OAUTH_STATE_KEY, None)
    verifier = request.session.pop(SESSION_CODE_VERIFIER_KEY, None)

    if not oauth_state_is_valid(expected_state, state):
        # Possible CSRF, a stale tab, or cookies blocked. Never exchange the code in this case.
        return _frontend(settings, "/settings", auth_error="invalid_state")
    if error:
        return _frontend(settings, "/settings", auth_error="access_denied" if error == "access_denied" else "oauth_error")
    if not code:
        return _frontend(settings, "/settings", auth_error="missing_code")

    try:
        creds = oauth_service.exchange_code(settings, state, code, verifier)
    except (OAuth2Error, ValueError) as exc:
        log.warning("OAuth code exchange failed: %s", type(exc).__name__)
        return _frontend(settings, "/settings", auth_error="token_exchange_failed")

    if oauth_service.SCOPES[0] not in (creds.scopes or oauth_service.SCOPES):
        return _frontend(settings, "/settings", auth_error="scope_not_granted")

    try:
        profile = GmailService(creds).get_profile()
    except GmailError:
        return _frontend(settings, "/settings", auth_error="gmail_profile_failed")

    email = profile["emailAddress"].lower()
    account = db.scalar(select(GmailAccount).where(GmailAccount.email == email))
    if account is None:
        account = GmailAccount(email=email)
        db.add(account)
    account.encrypted_credentials = cipher.encrypt(credentials_to_dict(creds))
    account.scopes = " ".join(creds.scopes or oauth_service.SCOPES)
    db.commit()

    request.session.clear()  # fresh session after login
    request.session[SESSION_ACCOUNT_KEY] = account.id
    return _frontend(settings, "/", connected="1")


@router.get("/status", response_model=AuthStatus)
def auth_status(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    account_id = request.session.get(SESSION_ACCOUNT_KEY)
    account = db.get(GmailAccount, account_id) if account_id else None
    connected = bool(account and account.is_connected)
    return AuthStatus(
        connected=connected,
        email=account.email if connected else None,
        scopes=account.scopes.split() if connected else [],
        oauth_configured=settings.google_oauth_configured,
        gemini_configured=bool(settings.gemini_api_key),
        auto_create_tasks=settings.auto_create_tasks,
    )


@router.post("/disconnect")
def disconnect(request: Request, db: Session = Depends(get_db), cipher: TokenCipher = Depends(get_cipher)):
    """Revoke the token at Google (best effort) and delete the stored credentials."""
    account_id = request.session.get(SESSION_ACCOUNT_KEY)
    account = db.get(GmailAccount, account_id) if account_id else None
    if account and account.encrypted_credentials:
        try:
            data = cipher.decrypt(account.encrypted_credentials)
            oauth_service.revoke(data.get("refresh_token") or data.get("token"))
        except RuntimeError:
            pass
        account.encrypted_credentials = None
        db.commit()
    request.session.clear()
    return {"disconnected": True}
