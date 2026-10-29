"""The agentic workflow, built with LangGraph.

    START
      -> load_message            perception: fetch the real Gmail message
      -> detect_signals          perception: deterministic rule signals
      -> analyze_email           reasoning: Gemini structured analysis (validated)
      -> classify_priority       reasoning: combine LLM output with Python rules
      -> extract_tasks_deadlines planning: task + deadline (only when action is required)
      -> decide_action           planning: choose the recommended next action
      -> create_task             action: only if AUTO_CREATE_TASKS is enabled
      -> save_analysis           state: persist the analysis
    END

Conditional edges route around failures (Gmail or Gemini errors), skip task extraction when
no action is required, and skip task creation unless the user enabled it. Each node appends
to `steps`, which is returned to the frontend as execution status.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from ..config import Settings
from ..models.db_models import GmailAccount
from ..models.schemas import LLMEmailAnalysis, TaskCreate
from ..services import analysis_service, rules, task_service
from ..services.gmail_service import GmailError, GmailService
from ..services.llm_service import GeminiService, LLMError


class EmailState(TypedDict, total=False):
    message_id: str
    email: dict
    signals: rules.Signals
    llm_result: LLMEmailAnalysis
    analysis: LLMEmailAnalysis
    priority_notes: list[str]
    parsed_deadline: Any
    suggested_task: TaskCreate | None
    recommended_action: str
    recommended_action_reason: str
    created_task: Any
    analysis_row: Any
    error: dict | None
    steps: Annotated[list[dict], operator.add]


def _step(node: str, status: str = "ok", detail: str = "") -> dict:
    return {"steps": [{"node": node, "status": status, "detail": detail}]}


# ---------- routing functions (pure; unit-tested) ----------


def route_after_load(state: EmailState) -> str:
    return "stop" if state.get("error") else "detect_signals"


def route_after_analysis(state: EmailState) -> str:
    return "record_failure" if state.get("error") else "classify_priority"


def route_after_priority(state: EmailState) -> str:
    return "extract_tasks_deadlines" if state["analysis"].action_required else "decide_action"


def make_route_after_decision(auto_create_tasks: bool):
    def route_after_decision(state: EmailState) -> str:
        return "create_task" if auto_create_tasks and state.get("suggested_task") else "save_analysis"

    return route_after_decision


# ---------- graph ----------


def build_email_workflow(
    *, db: Session, account: GmailAccount, gmail: GmailService, llm: GeminiService, settings: Settings
):
    def load_message(state: EmailState) -> dict:
        try:
            email = gmail.get_message(state["message_id"], full=True)
        except GmailError as exc:
            kind = type(exc).__name__
            return {"error": {"source": "gmail", "kind": kind, "message": str(exc)}} | _step(
                "load_message", "error", str(exc)
            )
        return {"email": email} | _step("load_message", detail=f"Loaded '{email['subject'][:80]}'")

    def detect_signals(state: EmailState) -> dict:
        signals = rules.detect_signals(state["email"])
        return {"signals": signals} | _step("detect_signals", detail=f"Rule signals: {signals.as_text()}")

    def analyze_email(state: EmailState) -> dict:
        try:
            result = llm.analyze_email(state["email"])
        except LLMError as exc:
            error = {"source": "llm", "kind": type(exc).__name__, "message": exc.message, "status_code": exc.status_code}
            return {"error": error} | _step(
                "analyze_email", "error", exc.message
            )
        return {"llm_result": result} | _step(
            "analyze_email", detail=f"Gemini: {result.category}, {result.priority} priority"
        )

    def record_failure(state: EmailState) -> dict:
        row = analysis_service.upsert_analysis(db, account, state["email"], None, status="failed")
        return {"analysis_row": row} | _step("record_failure", "error", "Analysis not saved; you can retry.")

    def classify_priority(state: EmailState) -> dict:
        analysis, notes = rules.reconcile(state["llm_result"], state["signals"])
        detail = " ".join(notes) if notes else "Rules agreed with the AI classification."
        return {"analysis": analysis, "priority_notes": notes} | _step("classify_priority", detail=detail)

    def extract_tasks_deadlines(state: EmailState) -> dict:
        a = state["analysis"]
        parsed = rules.parse_deadline(a.deadline_text, settings.user_timezone)
        suggested = None
        if a.task:
            suggested = TaskCreate(
                gmail_message_id=state["email"]["id"],
                title=a.task,
                deadline_text=a.deadline_text,
                parsed_deadline=parsed,
                priority=a.priority,
            )
        if a.deadline_text and parsed is None:
            deadline_note = f"Deadline '{a.deadline_text}' kept as text (no explicit date to convert)."
        elif parsed:
            deadline_note = f"Deadline '{a.deadline_text}' resolved to {parsed.isoformat()}."
        else:
            deadline_note = "No deadline stated."
        detail = (f"Task: {a.task}. " if a.task else "Action required but no concrete task. ") + deadline_note
        return {"parsed_deadline": parsed, "suggested_task": suggested} | _step("extract_tasks_deadlines", detail=detail)

    def decide_action(state: EmailState) -> dict:
        action, reason = rules.recommend_action(state["analysis"])
        update = {"recommended_action": action, "recommended_action_reason": reason}
        if not state["analysis"].action_required:
            update |= {"suggested_task": None, "parsed_deadline": None}
        return update | _step("decide_action", detail=f"{action}: {reason}")

    def create_task(state: EmailState) -> dict:
        task, created = task_service.create_task(db, account, state["suggested_task"], state["email"].get("thread_id"))
        detail = "Task created automatically (AUTO_CREATE_TASKS)." if created else "Task already existed; not duplicated."
        return {"created_task": task} | _step("create_task", detail=detail)

    def save_analysis(state: EmailState) -> dict:
        a = state["analysis"]
        reason = a.priority_reason
        if state.get("priority_notes"):
            reason = f"{reason} (Rule: {' '.join(state['priority_notes'])})"
        row = analysis_service.upsert_analysis(
            db,
            account,
            state["email"],
            a,
            parsed_deadline=state.get("parsed_deadline"),
            priority_reason=reason,
            recommended_action=state["recommended_action"],
            recommended_action_reason=state["recommended_action_reason"],
        )
        return {"analysis_row": row} | _step("save_analysis", detail="Analysis saved.")

    graph = StateGraph(EmailState)
    for node in (
        load_message, detect_signals, analyze_email, record_failure, classify_priority,
        extract_tasks_deadlines, decide_action, create_task, save_analysis,
    ):
        graph.add_node(node.__name__, node)

    graph.add_edge(START, "load_message")
    graph.add_conditional_edges("load_message", route_after_load, {"detect_signals": "detect_signals", "stop": END})
    graph.add_edge("detect_signals", "analyze_email")
    graph.add_conditional_edges(
        "analyze_email", route_after_analysis,
        {"classify_priority": "classify_priority", "record_failure": "record_failure"},
    )
    graph.add_edge("record_failure", END)
    graph.add_conditional_edges(
        "classify_priority", route_after_priority,
        {"extract_tasks_deadlines": "extract_tasks_deadlines", "decide_action": "decide_action"},
    )
    graph.add_edge("extract_tasks_deadlines", "decide_action")
    graph.add_conditional_edges(
        "decide_action", make_route_after_decision(settings.auto_create_tasks),
        {"create_task": "create_task", "save_analysis": "save_analysis"},
    )
    graph.add_edge("create_task", "save_analysis")
    graph.add_edge("save_analysis", END)
    return graph.compile()


def run_email_workflow(message_id: str, **deps) -> EmailState:
    workflow = build_email_workflow(**deps)
    return workflow.invoke({"message_id": message_id, "steps": [], "error": None})
