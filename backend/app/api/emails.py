"""Gmail inbox, message details, AI analysis and reply generation."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..agents.email_workflow import run_email_workflow
from ..config import Settings, get_settings
from ..database import get_db
from ..models.db_models import GmailAccount
from ..models.schemas import (
    AnalyzeOut,
    EmailDetailOut,
    EmailListOut,
    EmailSummaryOut,
    ReplyOut,
    ReplyRequest,
    WorkflowStep,
)
from ..security import get_current_account
from ..services import analysis_service, task_service
from ..services.gmail_service import GmailError, GmailService
from ..services.llm_service import GeminiService, LLMError
from .deps import get_gmail, get_llm, gmail_http_error, llm_http_error, workflow_http_error

router = APIRouter(prefix="/api/emails", tags=["emails"])

def _check_id(message_id: str) -> None:
    if not message_id.isalnum() or len(message_id) > 64:
        raise HTTPException(400, detail={"code": "invalid_message_id", "message": "Invalid Gmail message id."})


def _summary(email: dict, analysis) -> EmailSummaryOut:
    return EmailSummaryOut(
        id=email["id"],
        thread_id=email.get("thread_id"),
        sender=email["sender"],
        subject=email["subject"],
        snippet=email["snippet"],
        received_at=email["received_at"],
        unread=email["unread"],
        labels=email["labels"],
        category=analysis.category if analysis and analysis.analysis_status == "completed" else None,
        priority=analysis.priority if analysis and analysis.analysis_status == "completed" else None,
        analyzed=bool(analysis and analysis.analysis_status == "completed"),
    )


@router.get("", response_model=EmailListOut)
def list_emails(
    q: str = Query("", max_length=500, description="Gmail search syntax, e.g. 'from:alice is:unread'"),
    page_token: str | None = Query(None, max_length=200),
    max_results: int = Query(15, ge=1, le=50),
    label: str = Query("INBOX", pattern="^(INBOX|ALL|UNREAD|STARRED|IMPORTANT|SENT)$"),
    db: Session = Depends(get_db),
    account: GmailAccount = Depends(get_current_account),
    gmail: GmailService = Depends(get_gmail),
):
    try:
        page = gmail.list_messages(
            query=q, page_token=page_token, max_results=max_results, label=None if label == "ALL" else label
        )
    except GmailError as exc:
        raise gmail_http_error(exc) from exc
    analyses = analysis_service.analyses_by_message(db, account, [e["id"] for e in page["emails"]])
    return EmailListOut(
        emails=[_summary(e, analyses.get(e["id"])) for e in page["emails"]],
        next_page_token=page["next_page_token"],
        result_size_estimate=page["result_size_estimate"],
    )


@router.get("/{message_id}", response_model=EmailDetailOut)
def get_email(
    message_id: str,
    db: Session = Depends(get_db),
    account: GmailAccount = Depends(get_current_account),
    gmail: GmailService = Depends(get_gmail),
):
    _check_id(message_id)
    try:
        # Fetched with this account's own credentials: Gmail returns 404 for anyone else's message.
        email = gmail.get_message(message_id, full=True)
    except GmailError as exc:
        raise gmail_http_error(exc) from exc
    analysis = task_service.analysis_for(db, account, message_id)
    base = _summary(email, analysis)
    return EmailDetailOut(
        **base.model_dump(),
        to=email["to"],
        body_text=email["body_text"] or email["snippet"],
        body_was_html=email["body_was_html"],
        gmail_url=f"https://mail.google.com/mail/u/{account.email}/#all/{email['id']}",
        analysis=analysis_service.to_out(analysis) if analysis else None,
        task_ids=task_service.task_ids_for_message(db, account, message_id),
    )


@router.post("/{message_id}/analyze", response_model=AnalyzeOut)
def analyze_email(
    message_id: str,
    db: Session = Depends(get_db),
    account: GmailAccount = Depends(get_current_account),
    gmail: GmailService = Depends(get_gmail),
    llm: GeminiService = Depends(get_llm),
    settings: Settings = Depends(get_settings),
):
    _check_id(message_id)
    state = run_email_workflow(message_id, db=db, account=account, gmail=gmail, llm=llm, settings=settings)
    steps = [WorkflowStep(**s) for s in state.get("steps", [])]
    if state.get("error"):
        raise workflow_http_error(state["error"], [s.model_dump() for s in steps])

    created = state.get("created_task")
    return AnalyzeOut(
        analysis=analysis_service.to_out(state["analysis_row"]),
        steps=steps,
        suggested_task=state.get("suggested_task"),
        auto_created_task=task_service.to_out(created) if created else None,
    )


@router.post("/{message_id}/generate-reply", response_model=ReplyOut)
def generate_reply(
    message_id: str,
    body: ReplyRequest | None = None,
    gmail: GmailService = Depends(get_gmail),
    llm: GeminiService = Depends(get_llm),
):
    """Draft a reply suggestion. Nothing is sent: the app has no Gmail send permission."""
    _check_id(message_id)
    body = body or ReplyRequest()
    try:
        email = gmail.get_message(message_id, full=True)
        thread = gmail.get_thread_context(email["thread_id"], message_id) if email.get("thread_id") else []
    except GmailError as exc:
        raise gmail_http_error(exc) from exc
    try:
        reply = llm.generate_reply(email, thread, tone=body.tone, instructions=body.instructions)
    except LLMError as exc:
        raise llm_http_error(exc) from exc
    return ReplyOut(reply=reply, generated_at=datetime.now(timezone.utc))
