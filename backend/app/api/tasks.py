"""Task management routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.db_models import GmailAccount
from ..models.schemas import TaskCreate, TaskCreateOut, TaskOut, TaskUpdate
from ..security import get_current_account
from ..services import task_service
from ..services.gmail_service import GmailError, GmailService
from .deps import get_gmail, gmail_http_error

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
def list_tasks(
    status: str | None = Query(None, pattern="^(Pending|Completed)$"),
    db: Session = Depends(get_db),
    account: GmailAccount = Depends(get_current_account),
):
    return [task_service.to_out(t) for t in task_service.list_tasks(db, account, status)]


@router.post("", response_model=TaskCreateOut)
def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    account: GmailAccount = Depends(get_current_account),
    gmail: GmailService = Depends(get_gmail),
):
    """Create a task for a message in the user's own mailbox. Duplicates return the existing task."""
    analysis = task_service.analysis_for(db, account, data.gmail_message_id)
    if analysis is not None:
        thread_id = analysis.gmail_thread_id
    else:
        # Not analysed yet: confirm with Gmail that this message belongs to the connected account.
        try:
            thread_id = gmail.get_message(data.gmail_message_id, full=False).get("thread_id")
        except GmailError as exc:
            raise gmail_http_error(exc) from exc
    task, created = task_service.create_task(db, account, data, thread_id)
    return TaskCreateOut(task=task_service.to_out(task), created=created)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    data: TaskUpdate,
    db: Session = Depends(get_db),
    account: GmailAccount = Depends(get_current_account),
):
    task = task_service.get_task(db, account, task_id)
    if task is None:  # also returned for other accounts' tasks, so ids can't be probed
        raise HTTPException(404, detail={"code": "task_not_found", "message": "Task not found."})
    task.status = data.status
    db.commit()
    db.refresh(task)
    return task_service.to_out(task)
