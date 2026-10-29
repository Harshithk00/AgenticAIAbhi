"""Database tables."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GmailAccount(Base):
    """A connected Gmail account. OAuth tokens are stored encrypted and never leave the backend."""

    __tablename__ = "gmail_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # Fernet-encrypted JSON (access token, refresh token, expiry, scopes). NULL once disconnected.
    encrypted_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[str] = mapped_column(String(1000), default="")
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    analyses: Mapped[list["EmailAnalysis"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="account", cascade="all, delete-orphan")

    @property
    def is_connected(self) -> bool:
        return self.encrypted_credentials is not None


class EmailAnalysis(Base):
    """The AI analysis of one Gmail message. The email body itself is NOT stored."""

    __tablename__ = "email_analyses"
    __table_args__ = (UniqueConstraint("account_id", "gmail_message_id", name="uq_analysis_account_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("gmail_accounts.id"), index=True)
    gmail_message_id: Mapped[str] = mapped_column(String(64), index=True)
    gmail_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender: Mapped[str] = mapped_column(String(500), default="")
    subject: Mapped[str] = mapped_column(String(1000), default="")
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(16), nullable=True)
    priority_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_required: Mapped[bool] = mapped_column(Boolean, default=False)
    response_required: Mapped[bool] = mapped_column(Boolean, default=False)
    extracted_task: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parsed_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meeting_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recommended_action_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_status: Mapped[str] = mapped_column(String(32), default="pending")
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped[GmailAccount] = relationship(back_populates="analyses")


class Task(Base):
    """A task created from an email (by the user, or automatically when enabled)."""

    __tablename__ = "tasks"
    __table_args__ = (
        # The same task cannot be created twice for the same message.
        UniqueConstraint("account_id", "gmail_message_id", "title_key", name="uq_task_account_message_title"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("gmail_accounts.id"), index=True)
    gmail_message_id: Mapped[str] = mapped_column(String(64), index=True)
    gmail_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    title_key: Mapped[str] = mapped_column(String(500))
    deadline_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parsed_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="Medium")
    status: Mapped[str] = mapped_column(String(16), default="Pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    account: Mapped[GmailAccount] = relationship(back_populates="tasks")
