"""Saving and reading email analyses."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.db_models import EmailAnalysis, GmailAccount
from ..models.schemas import AnalysisOut, LLMEmailAnalysis
from .task_service import analysis_for, as_utc


def upsert_analysis(
    db: Session,
    account: GmailAccount,
    email: dict,
    result: LLMEmailAnalysis | None,
    *,
    parsed_deadline: datetime | None = None,
    priority_reason: str | None = None,
    recommended_action: str | None = None,
    recommended_action_reason: str | None = None,
    status: str = "completed",
) -> EmailAnalysis:
    """One row per (account, message): re-analysing updates the row instead of duplicating it."""
    row = analysis_for(db, account, email["id"])
    if row is None:
        row = EmailAnalysis(account_id=account.id, gmail_message_id=email["id"])
        db.add(row)
    elif status == "failed" and row.analysis_status == "completed":
        return row  # keep the last good analysis if a re-analysis fails

    row.gmail_thread_id = email.get("thread_id")
    row.sender = email.get("sender", "")[:500]
    row.subject = email.get("subject", "")[:1000]
    row.received_at = email.get("received_at")
    row.analysis_status = status
    row.analyzed_at = datetime.now(timezone.utc)
    if result is not None:
        row.category = result.category
        row.priority = result.priority
        row.priority_reason = priority_reason or result.priority_reason
        row.summary = result.summary
        row.action_required = result.action_required
        row.response_required = result.response_required
        row.extracted_task = result.task
        row.deadline_text = result.deadline_text
        row.parsed_deadline = parsed_deadline
        row.meeting_details = result.meeting_details if result.is_meeting else None
        row.recommended_action = recommended_action
        row.recommended_action_reason = recommended_action_reason
    db.commit()
    db.refresh(row)
    return row


def to_out(row: EmailAnalysis) -> AnalysisOut:
    out = AnalysisOut.model_validate(row)
    out.parsed_deadline = as_utc(row.parsed_deadline)
    out.analyzed_at = as_utc(row.analyzed_at)
    out.received_at = as_utc(row.received_at)
    return out


def analyses_by_message(db: Session, account: GmailAccount, message_ids: list[str]) -> dict[str, EmailAnalysis]:
    if not message_ids:
        return {}
    rows = db.scalars(
        select(EmailAnalysis).where(
            EmailAnalysis.account_id == account.id, EmailAnalysis.gmail_message_id.in_(message_ids)
        )
    )
    return {r.gmail_message_id: r for r in rows}
