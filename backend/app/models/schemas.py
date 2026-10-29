"""Pydantic models: LLM output schemas and API request/response bodies."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["Academic", "Work", "Personal", "Meeting", "Finance", "Promotion", "Other"]
Priority = Literal["High", "Medium", "Low"]
TaskStatus = Literal["Pending", "Completed"]
RecommendedAction = Literal[
    "create_task_and_reply",
    "create_task",
    "reply",
    "review_meeting",
    "read_later",
    "no_action",
]
CATEGORIES: tuple[str, ...] = Category.__args__
PRIORITIES: tuple[str, ...] = Priority.__args__


# ---------- LLM structured output ----------


class LLMEmailAnalysis(BaseModel):
    """What Gemini must return for one email. Validated before anything is saved."""

    category: Category
    priority: Priority
    priority_reason: str = Field(description="One or two sentences explaining the priority, citing the email.")
    summary: str = Field(description="2-4 sentences: purpose, key information, deadlines and requested actions.")
    action_required: bool = Field(description="True if the recipient must do something.")
    response_required: bool = Field(description="True if the sender is waiting for a reply.")
    task: str | None = Field(default=None, description="Short imperative task, e.g. 'Submit the project report'.")
    deadline_text: str | None = Field(
        default=None, description="The deadline exactly as worded in the email, e.g. 'Friday at 5 PM'. Null if none."
    )
    is_meeting: bool = Field(default=False, description="True if the email proposes or schedules a meeting/interview.")
    meeting_details: str | None = Field(default=None, description="When/where/who for the meeting, as stated.")
    suspicious: bool = Field(default=False, description="True if the email looks like phishing or a scam.")

    @field_validator("priority_reason", "summary")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("task", "deadline_text", "meeting_details")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value if value and value.lower() not in {"none", "null", "n/a"} else None


class LLMReply(BaseModel):
    reply: str


# ---------- API: auth ----------


class AuthStatus(BaseModel):
    connected: bool
    email: str | None = None
    scopes: list[str] = []
    oauth_configured: bool
    gemini_configured: bool
    auto_create_tasks: bool


# ---------- API: emails ----------


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gmail_message_id: str
    gmail_thread_id: str | None
    sender: str
    subject: str
    received_at: datetime | None
    category: str | None
    priority: str | None
    priority_reason: str | None
    summary: str | None
    action_required: bool
    response_required: bool
    extracted_task: str | None
    deadline_text: str | None
    parsed_deadline: datetime | None
    meeting_details: str | None
    recommended_action: str | None
    recommended_action_reason: str | None
    analysis_status: str
    analyzed_at: datetime | None


class EmailSummaryOut(BaseModel):
    id: str
    thread_id: str | None
    sender: str
    subject: str
    snippet: str
    received_at: datetime | None
    unread: bool
    labels: list[str]
    category: str | None = None
    priority: str | None = None
    analyzed: bool = False


class EmailListOut(BaseModel):
    emails: list[EmailSummaryOut]
    next_page_token: str | None
    result_size_estimate: int


class EmailDetailOut(EmailSummaryOut):
    to: str
    body_text: str
    body_was_html: bool
    gmail_url: str
    analysis: AnalysisOut | None = None
    task_ids: list[int] = []


class WorkflowStep(BaseModel):
    node: str
    status: Literal["ok", "skipped", "error"]
    detail: str = ""


class AnalyzeOut(BaseModel):
    analysis: AnalysisOut
    steps: list[WorkflowStep]
    suggested_task: "TaskCreate | None" = None
    auto_created_task: "TaskOut | None" = None


class ReplyRequest(BaseModel):
    tone: Literal["professional", "friendly", "brief"] = "professional"
    instructions: str | None = Field(default=None, max_length=500)


class ReplyOut(BaseModel):
    reply: str
    ai_generated: bool = True
    generated_at: datetime


# ---------- API: tasks ----------


class TaskCreate(BaseModel):
    gmail_message_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    deadline_text: str | None = Field(default=None, max_length=500)
    parsed_deadline: datetime | None = None
    priority: Priority = "Medium"

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be empty")
        return value


class TaskUpdate(BaseModel):
    status: TaskStatus


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gmail_message_id: str
    gmail_thread_id: str | None
    title: str
    deadline_text: str | None
    parsed_deadline: datetime | None
    priority: str
    status: str
    created_at: datetime
    updated_at: datetime
    is_overdue: bool = False
    is_upcoming: bool = False


class TaskCreateOut(BaseModel):
    task: TaskOut
    created: bool


# ---------- API: dashboard ----------


class DashboardStats(BaseModel):
    account_email: str
    mailbox_messages_total: int | None
    analyzed_emails: int
    high_priority_emails: int
    response_required_emails: int
    pending_tasks: int
    completed_tasks: int
    overdue_tasks: int
    upcoming_deadlines: list[TaskOut]
    recent_important: list[AnalysisOut]
    pending_task_list: list[TaskOut]


AnalyzeOut.model_rebuild()
