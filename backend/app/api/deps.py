"""Shared FastAPI dependencies. Tests override `get_gmail` and `get_llm` with fakes."""

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..models.db_models import GmailAccount
from ..security import TokenCipher, get_cipher, get_current_account
from ..services.accounts import gmail_for_account
from ..services.gmail_service import GmailAuthError, GmailError, GmailNotFound, GmailService
from ..services.llm_service import GeminiService, LLMError


def get_gmail(
    db: Session = Depends(get_db),
    account: GmailAccount = Depends(get_current_account),
    cipher: TokenCipher = Depends(get_cipher),
    settings: Settings = Depends(get_settings),
) -> GmailService:
    try:
        return gmail_for_account(db, account, cipher, settings)
    except GmailAuthError as exc:
        raise gmail_http_error(exc) from exc


def get_llm(settings: Settings = Depends(get_settings)) -> GeminiService:
    return GeminiService(settings)


def gmail_http_error(exc: GmailError) -> HTTPException:
    if isinstance(exc, GmailNotFound):
        return HTTPException(404, detail={"code": "message_not_found", "message": str(exc)})
    if isinstance(exc, GmailAuthError):
        return HTTPException(401, detail={"code": "gmail_reauth_required", "message": str(exc)})
    return HTTPException(502, detail={"code": "gmail_error", "message": str(exc)})


_LLM_CODES = {
    "LLMNotConfigured": "llm_not_configured",
    "LLMRateLimited": "llm_rate_limited",
    "LLMUnavailable": "llm_unavailable",
    "LLMInvalidResponse": "llm_invalid_response",
}
_GMAIL_STATUS = {"GmailNotFound": (404, "message_not_found"), "GmailAuthError": (401, "gmail_reauth_required")}


def llm_http_error(exc: LLMError) -> HTTPException:
    code = _LLM_CODES.get(type(exc).__name__, "llm_error")
    return HTTPException(
        exc.status_code,
        detail={"code": code, "message": exc.message, "retryable": code != "llm_not_configured"},
    )


def workflow_http_error(error: dict, steps: list[dict]) -> HTTPException:
    """Turn the error recorded in the workflow state into an HTTP error that carries the step trace."""
    if error["source"] == "gmail":
        status, code = _GMAIL_STATUS.get(error["kind"], (502, "gmail_error"))
        detail = {"code": code, "message": error["message"]}
    else:
        status = error["status_code"]
        code = _LLM_CODES.get(error["kind"], "llm_error")
        detail = {"code": code, "message": error["message"], "retryable": code != "llm_not_configured"}
    return HTTPException(status, detail=detail | {"steps": steps})
