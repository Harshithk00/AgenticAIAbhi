"""Task persistence with duplicate prevention."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.db_models import EmailAnalysis, GmailAccount, Task
from ..models.schemas import TaskCreate, TaskOut

UPCOMING_WINDOW = timedelta(days=7)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything is stored in UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def to_out(task: Task, now: datetime | None = None) -> TaskOut:
    now = now or datetime.now(timezone.utc)
    deadline = as_utc(task.parsed_deadline)
    out = TaskOut.model_validate(task)
    out.parsed_deadline = deadline
    out.created_at = as_utc(task.created_at)
    out.updated_at = as_utc(task.updated_at)
    if deadline and task.status == "Pending":
        out.is_overdue = deadline < now
        out.is_upcoming = now <= deadline <= now + UPCOMING_WINDOW
    return out


def create_task(
    db: Session, account: GmailAccount, data: TaskCreate, thread_id: str | None = None
) -> tuple[Task, bool]:
    """Create a task, or return the existing one if the same task already exists for this message."""
    key = title_key(data.title)
    existing = db.scalar(
        select(Task).where(
            Task.account_id == account.id, Task.gmail_message_id == data.gmail_message_id, Task.title_key == key
        )
    )
    if existing:
        return existing, False
    task = Task(
        account_id=account.id,
        gmail_message_id=data.gmail_message_id,
        gmail_thread_id=thread_id,
        title=data.title,
        title_key=key,
        deadline_text=data.deadline_text,
        parsed_deadline=as_utc(data.parsed_deadline),
        priority=data.priority,
    )
    db.add(task)
    try:
        db.commit()
    except IntegrityError:  # a concurrent request created it first
        db.rollback()
        existing = db.scalar(
            select(Task).where(
                Task.account_id == account.id, Task.gmail_message_id == data.gmail_message_id, Task.title_key == key
            )
        )
        return existing, False
    db.refresh(task)
    return task, True


def list_tasks(db: Session, account: GmailAccount, status: str | None = None) -> list[Task]:
    query = select(Task).where(Task.account_id == account.id)
    if status:
        query = query.where(Task.status == status)
    tasks = list(db.scalars(query))
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(tasks, key=lambda t: (t.status != "Pending", as_utc(t.parsed_deadline) or far_future, -t.id))


def get_task(db: Session, account: GmailAccount, task_id: int) -> Task | None:
    """Only returns the task if it belongs to this account."""
    return db.scalar(select(Task).where(Task.id == task_id, Task.account_id == account.id))


def task_ids_for_message(db: Session, account: GmailAccount, message_id: str) -> list[int]:
    return list(db.scalars(select(Task.id).where(Task.account_id == account.id, Task.gmail_message_id == message_id)))


def analysis_for(db: Session, account: GmailAccount, message_id: str) -> EmailAnalysis | None:
    return db.scalar(
        select(EmailAnalysis).where(EmailAnalysis.account_id == account.id, EmailAnalysis.gmail_message_id == message_id)
    )
