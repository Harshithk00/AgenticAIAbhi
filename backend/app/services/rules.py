"""Deterministic Python rules used alongside the LLM.

The LLM understands language; these rules make the clear-cut application decisions
(promotions stay low priority, no-reply senders can't be answered, which action to recommend)
and parse deadlines only when the date can be resolved without guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..models.schemas import LLMEmailAnalysis
from .gmail_parser import sender_email

PROMO_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"}
_NOREPLY = re.compile(r"^(no[-_.]?reply|do[-_.]?not[-_.]?reply|notifications?|mailer-daemon)@", re.I)
_INTERVIEW = re.compile(r"\binterview\b", re.I)
_DEADLINE_WORDS = re.compile(r"\b(deadline|due (on|by|date)|submit|no later than|by (mon|tue|wed|thu|fri|sat|sun)\w*|by tomorrow|by today|by eod)\b", re.I)

_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",),
            ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"),
            ("oct", "october"), ("nov", "november"), ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?\b")
_DAY_MONTH_YEAR = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_RE})\.?,?\s+(\d{{4}})\b", re.I)
_MONTH_DAY_YEAR = re.compile(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
_TIME_12H = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\b", re.I)
_TIME_24H = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


@dataclass
class Signals:
    promotional_label: bool
    noreply_sender: bool
    mentions_interview: bool
    mentions_deadline: bool

    def as_text(self) -> str:
        flags = [name for name, on in vars(self).items() if on]
        return ", ".join(flags) if flags else "none"


def detect_signals(email: dict) -> Signals:
    text = f"{email.get('subject', '')}\n{email.get('body_text') or email.get('snippet', '')}"
    return Signals(
        promotional_label=bool(PROMO_LABELS & set(email.get("labels", []))),
        noreply_sender=bool(_NOREPLY.match(sender_email(email.get("sender", "")))),
        mentions_interview=bool(_INTERVIEW.search(text)),
        mentions_deadline=bool(_DEADLINE_WORDS.search(text)),
    )


def reconcile(analysis: LLMEmailAnalysis, signals: Signals) -> tuple[LLMEmailAnalysis, list[str]]:
    """Apply rule-based corrections to the LLM result. Returns the result and notes on what changed."""
    a = analysis.model_copy()
    notes: list[str] = []

    if a.suspicious:
        a.action_required = False
        a.response_required = False
        a.task = None
        notes.append("Looks like phishing: no task or reply is suggested.")

    if (a.category == "Promotion" or signals.promotional_label) and not a.action_required and a.priority != "Low":
        a.priority = "Low"
        notes.append("Promotional email with no required action, so priority set to Low.")

    if signals.mentions_interview and a.action_required and a.priority != "High" and a.category != "Promotion":
        a.priority = "High"
        notes.append("Interview that needs action, so priority raised to High.")

    if signals.noreply_sender and a.response_required:
        a.response_required = False
        notes.append("Sender is a no-reply address, so no reply is expected.")
    return a, notes


def _zone(name: str):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _find_time(text: str) -> time | None:
    m = _TIME_12H.search(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if not 1 <= hour <= 12 or minute > 59:
            return None
        hour = hour % 12 + (12 if m.group(3).lower() == "p" else 0)
        return time(hour, minute)
    m = _TIME_24H.search(text)
    if m:
        return time(int(m.group(1)), int(m.group(2)))
    return None


def parse_deadline(deadline_text: str | None, timezone_name: str = "UTC") -> datetime | None:
    """Turn deadline wording into a timestamp ONLY when it contains an explicit date with a year.

    Relative wording ("Friday", "next week", "tomorrow") returns None: the original text is kept
    instead of guessing. Without a stated time the deadline is the end of that day. Times are
    interpreted in the user's configured timezone (USER_TIMEZONE).
    """
    if not deadline_text:
        return None
    text = deadline_text.strip()
    try:
        if m := _ISO.search(text):
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            explicit_time = time(int(m.group(4)), int(m.group(5))) if m.group(4) else None
        elif m := _DAY_MONTH_YEAR.search(text):
            day, month, year = int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3))
            explicit_time = None
        elif m := _MONTH_DAY_YEAR.search(text):
            month, day, year = _MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
            explicit_time = None
        else:
            return None
        remainder = text[: m.start()] + " " + text[m.end():]
        at = explicit_time or _find_time(remainder)
        tz = _zone(timezone_name)
        if at is None:
            return datetime(year, month, day, tzinfo=tz) + timedelta(days=1, seconds=-1)
        return datetime.combine(datetime(year, month, day).date(), at, tzinfo=tz)
    except (ValueError, KeyError):
        return None  # e.g. 31 February


def recommend_action(a: LLMEmailAnalysis) -> tuple[str, str]:
    """Deterministic choice of the next action, based on the validated analysis."""
    if a.suspicious:
        return "no_action", "This looks like phishing. Don't click links or reply; report it in Gmail if unsure."
    if a.action_required and a.task and a.response_required:
        return "create_task_and_reply", "There is a task to track and the sender is waiting for your reply."
    if a.action_required and a.task:
        reason = "Create a reminder so the task isn't missed."
        if a.deadline_text:
            reason = f"Create a reminder: the task is due {a.deadline_text}."
        return "create_task", reason
    if a.response_required:
        return "reply", "The sender is waiting for a response."
    if a.is_meeting:
        return "review_meeting", "Check the meeting details and add it to your calendar if you plan to attend."
    if a.category == "Promotion":
        return "no_action", "Promotional email; no action needed."
    return "read_later", "Informational; read when convenient."
