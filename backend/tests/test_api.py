from app.services.llm_service import LLMNotConfigured, LLMUnavailable

from .conftest import PROMO_ANALYSIS, REPORT_ANALYSIS


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_endpoints_require_connected_account(client):
    for method, path in [("get", "/api/emails"), ("get", "/api/tasks"), ("get", "/api/dashboard/stats"),
                         ("post", "/api/emails/m1/analyze")]:
        response = getattr(client, method)(path)
        assert response.status_code == 401, path
        assert response.json()["detail"]["code"] == "not_connected"


def test_auth_status_disconnected(client):
    body = client.get("/api/auth/status").json()
    assert body["connected"] is False and body["email"] is None


def test_list_emails_with_pagination(make_account, login):
    client = login(make_account())
    first = client.get("/api/emails", params={"max_results": 2}).json()
    assert [e["id"] for e in first["emails"]] == ["m1", "m2"]
    assert first["next_page_token"] == "2"
    second = client.get("/api/emails", params={"max_results": 2, "page_token": first["next_page_token"]}).json()
    assert [e["id"] for e in second["emails"]] == ["m3"] and second["next_page_token"] is None


def test_email_detail_html_is_sanitized_text(make_account, login):
    client = login(make_account())
    body = client.get("/api/emails/m3").json()
    assert body["body_was_html"] is True
    assert body["body_text"] == "Hello"
    assert "<script>" not in body["body_text"] and "alert" not in body["body_text"]


def test_invalid_and_unknown_message_ids(make_account, login):
    client = login(make_account())
    assert client.get("/api/emails/bad$id").status_code == 400
    assert client.get("/api/emails/doesnotexist").status_code == 404


def test_analyze_creates_analysis_and_suggests_task(make_account, login, llm):
    llm.analysis = REPORT_ANALYSIS
    client = login(make_account())
    response = client.post("/api/emails/m1/analyze")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["analysis"]["category"] == "Academic"
    assert body["analysis"]["priority"] == "High"
    assert body["analysis"]["extracted_task"] == "Submit the project report"
    assert body["analysis"]["deadline_text"] == "Friday at 5 PM"
    assert body["analysis"]["parsed_deadline"] is None  # "Friday" alone is not converted
    assert body["analysis"]["recommended_action"] == "create_task"
    assert body["suggested_task"]["title"] == "Submit the project report"
    assert body["auto_created_task"] is None  # tasks need approval by default
    assert client.get("/api/tasks").json() == []
    nodes = [s["node"] for s in body["steps"]]
    assert nodes == ["load_message", "detect_signals", "analyze_email", "classify_priority",
                     "extract_tasks_deadlines", "decide_action", "save_analysis"]
    # Re-analysing updates the same row instead of creating a duplicate.
    client.post("/api/emails/m1/analyze")
    stats = client.get("/api/dashboard/stats").json()
    assert stats["analyzed_emails"] == 1 and stats["high_priority_emails"] == 1


def test_promotion_is_low_priority_and_creates_no_task(make_account, login, llm):
    llm.analysis = PROMO_ANALYSIS
    client = login(make_account())
    body = client.post("/api/emails/m2/analyze").json()
    assert body["analysis"]["priority"] == "Low"
    assert body["analysis"]["recommended_action"] == "no_action"
    assert body["suggested_task"] is None
    assert "extract_tasks_deadlines" not in [s["node"] for s in body["steps"]]


def test_auto_create_tasks_setting(make_account, login, llm, settings_override):
    settings_override(auto_create_tasks=True)
    llm.analysis = REPORT_ANALYSIS
    client = login(make_account())
    body = client.post("/api/emails/m1/analyze").json()
    assert body["auto_created_task"]["title"] == "Submit the project report"
    client.post("/api/emails/m1/analyze")
    assert len(client.get("/api/tasks").json()) == 1  # no duplicate on re-analysis


def test_missing_gemini_key_returns_clear_error_and_inbox_still_works(make_account, login, llm):
    llm.error = LLMNotConfigured("GEMINI_API_KEY is not set on the server, so AI features are unavailable.")
    client = login(make_account())
    response = client.post("/api/emails/m1/analyze")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "llm_not_configured" and detail["retryable"] is False
    assert any(s["status"] == "error" for s in detail["steps"])
    assert client.get("/api/emails").status_code == 200
    assert client.get("/api/emails/m1").json()["analysis"]["analysis_status"] == "failed"


def test_llm_outage_keeps_previous_good_analysis(make_account, login, llm):
    llm.analysis = REPORT_ANALYSIS
    client = login(make_account())
    client.post("/api/emails/m1/analyze")
    llm.error = LLMUnavailable("Gemini is temporarily unavailable (HTTP 503). Please retry.")
    response = client.post("/api/emails/m1/analyze")
    assert response.status_code == 503 and response.json()["detail"]["retryable"] is True
    assert client.get("/api/emails/m1").json()["analysis"]["analysis_status"] == "completed"


def test_generate_reply(make_account, login):
    client = login(make_account())
    response = client.post("/api/emails/m1/generate-reply", json={"tone": "friendly"})
    assert response.status_code == 200
    body = response.json()
    assert body["ai_generated"] is True and "Friday at 5 PM" in body["reply"]


def test_generate_reply_llm_error(make_account, login, llm):
    llm.error = LLMUnavailable("Could not reach Gemini (network error or timeout). Please retry.")
    response = login(make_account()).post("/api/emails/m1/generate-reply")
    assert response.status_code == 503 and response.json()["detail"]["code"] == "llm_unavailable"


def test_task_create_duplicate_and_complete(make_account, login):
    client = login(make_account())
    payload = {"gmail_message_id": "m1", "title": "Submit the project report", "deadline_text": "Friday at 5 PM",
               "priority": "High"}
    first = client.post("/api/tasks", json=payload).json()
    assert first["created"] is True and first["task"]["gmail_thread_id"] == "t-m1"
    again = client.post("/api/tasks", json={**payload, "title": "  submit the PROJECT report! "}).json()
    assert again["created"] is False and again["task"]["id"] == first["task"]["id"]
    assert len(client.get("/api/tasks").json()) == 1

    task_id = first["task"]["id"]
    done = client.patch(f"/api/tasks/{task_id}", json={"status": "Completed"}).json()
    assert done["status"] == "Completed"
    assert client.get("/api/tasks", params={"status": "Pending"}).json() == []
    assert client.patch(f"/api/tasks/{task_id}", json={"status": "Done"}).status_code == 422


def test_task_for_message_outside_mailbox_is_rejected(make_account, login):
    client = login(make_account())
    response = client.post("/api/tasks", json={"gmail_message_id": "x1", "title": "Steal"})
    assert response.status_code == 404


def test_overdue_and_upcoming_tasks(make_account, login):
    from datetime import datetime, timedelta, timezone

    client = login(make_account())
    now = datetime.now(timezone.utc)
    client.post("/api/tasks", json={"gmail_message_id": "m1", "title": "Old", "parsed_deadline": (now - timedelta(days=1)).isoformat()})
    client.post("/api/tasks", json={"gmail_message_id": "m1", "title": "Soon", "parsed_deadline": (now + timedelta(days=2)).isoformat()})
    tasks = {t["title"]: t for t in client.get("/api/tasks").json()}
    assert tasks["Old"]["is_overdue"] and not tasks["Old"]["is_upcoming"]
    assert tasks["Soon"]["is_upcoming"] and not tasks["Soon"]["is_overdue"]
    stats = client.get("/api/dashboard/stats").json()
    assert stats["overdue_tasks"] == 1 and [t["title"] for t in stats["upcoming_deadlines"]] == ["Soon"]


def test_accounts_cannot_see_each_others_data(make_account, client, login, llm):
    llm.analysis = REPORT_ANALYSIS
    alice, bob = make_account("student@gmail.com"), make_account("other@gmail.com")

    login(alice)
    task_id = client.post("/api/tasks", json={"gmail_message_id": "m1", "title": "Alice task"}).json()["task"]["id"]
    client.post("/api/emails/m1/analyze")

    login(bob)
    assert client.get("/api/tasks").json() == []
    assert client.patch(f"/api/tasks/{task_id}", json={"status": "Completed"}).status_code == 404
    assert client.get("/api/emails/m1").status_code == 404  # not in Bob's mailbox
    stats = client.get("/api/dashboard/stats").json()
    assert stats["analyzed_emails"] == 0 and stats["pending_tasks"] == 0


def test_disconnect_removes_credentials(make_account, login, db):
    from app.models.db_models import GmailAccount

    account = make_account()
    client = login(account)
    assert client.post("/api/auth/disconnect").json() == {"disconnected": True}
    db.expire_all()
    assert db.get(GmailAccount, account.id).encrypted_credentials is None
    assert client.get("/api/emails").status_code == 401


def test_analyze_unknown_message_stops_workflow(make_account, login, llm):
    llm.analysis = REPORT_ANALYSIS
    response = login(make_account()).post("/api/emails/x1/analyze")  # exists only in another mailbox
    assert response.status_code == 404
    assert response.json()["detail"]["steps"][0] == {"node": "load_message", "status": "error",
                                                    "detail": "Message not found in this Gmail account."}
    assert llm.calls == 0  # Gemini is never called
