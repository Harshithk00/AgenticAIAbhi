"""Dashboard statistics, calculated from the database and the live Gmail profile."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import EmailAnalysis, GmailAccount
from ..models.schemas import DashboardStats
from ..security import get_current_account
from ..services import analysis_service, task_service
from ..services.gmail_service import GmailError, GmailService
from .deps import get_gmail

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def stats(
    db: Session = Depends(get_db),
    account: GmailAccount = Depends(get_current_account),
    gmail: GmailService = Depends(get_gmail),
):
    try:
        mailbox_total = gmail.get_profile().get("messagesTotal")
    except GmailError:
        mailbox_total = None  # dashboard still works from local data

    completed = (EmailAnalysis.account_id == account.id) & (EmailAnalysis.analysis_status == "completed")

    def count(*conditions) -> int:
        return db.scalar(select(func.count()).select_from(EmailAnalysis).where(completed, *conditions)) or 0

    now = datetime.now(timezone.utc)
    tasks = [task_service.to_out(t, now) for t in task_service.list_tasks(db, account)]
    pending = [t for t in tasks if t.status == "Pending"]
    recent = db.scalars(
        select(EmailAnalysis)
        .where(completed, EmailAnalysis.priority == "High")
        .order_by(EmailAnalysis.received_at.desc())
        .limit(5)
    )
    return DashboardStats(
        account_email=account.email,
        mailbox_messages_total=mailbox_total,
        analyzed_emails=count(),
        high_priority_emails=count(EmailAnalysis.priority == "High"),
        response_required_emails=count(EmailAnalysis.response_required.is_(True)),
        pending_tasks=len(pending),
        completed_tasks=len(tasks) - len(pending),
        overdue_tasks=sum(t.is_overdue for t in pending),
        upcoming_deadlines=[t for t in pending if t.is_upcoming][:5],
        recent_important=[analysis_service.to_out(r) for r in recent],
        pending_task_list=pending[:5],
    )
