from app.services.importer import norm_kind, norm_priority, norm_status

JIRA = """\
Issue key,Summary,Issue Type,Status,Assignee,Priority,Created,Resolved,Due Date,Description
PAY-1,Refund fails for EUR invoices,Bug,Done,Arun,High,2026-05-01 10:00,2026-05-04 12:00,2026-05-03,Steps: ...
PAY-2,Add proration preview,Story,In Progress,Meera,Medium,2026-05-02,,2026-05-20,As an admin I want...
PAY-3,,Task,To Do,,Low,2026-05-03,,,
PAY-1,Refund fails for EUR invoices,Bug,Done,Arun,High,2026-05-01,2026-05-04,,dup row
PAY-4,Upgrade Stripe SDK,Tech Debt,Blocked,Karthik,P1,2026-05-05,,,
"""


def test_jira_csv_import(client, make_user):
    u = make_user()
    r = client.post(
        f"/api/workspaces/{u['workspace_id']}/import",
        files={"file": ("payments.csv", JIRA.encode(), "text/csv")},
        data={"project_name": "Payments"},
        headers=u["headers"],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    rep = body["report"]
    assert rep["rows_read"] == 5 and rep["imported"] == 3
    assert rep["skipped_reasons"] == {"missing title": 1, "duplicate key": 1}
    assert rep["columns_mapped"]["kind"] == "Issue Type"
    assert rep["status_counts"] == {"done": 1, "in_progress": 1, "blocked": 1}
    assert body["project"]["name"] == "Payments" and body["project"]["task_count"] == 3

    tasks = client.get(f"/api/projects/{body['project']['id']}/tasks", headers=u["headers"]).json()
    refund = next(t for t in tasks if t["title"].startswith("Refund"))
    assert refund["kind"] == "bug" and refund["completed_at"] and refund["priority"] == "high"


def test_import_rejects_files_without_titles(client, make_user):
    u = make_user()
    r = client.post(
        f"/api/workspaces/{u['workspace_id']}/import",
        files={"file": ("x.csv", b"foo,bar\n1,2\n", "text/csv")},
        headers=u["headers"],
    )
    assert r.status_code == 400 and "title" in r.json()["detail"].lower()


def test_value_normalisers():
    assert norm_status("In Review") == "in_progress" and norm_status("closed") == "done"
    assert norm_status("Backlog") == "planned"
    assert norm_kind("bug, ui") == "bug" and norm_kind("Story") == "feature"
    assert norm_kind("Tech Debt") == "tech_debt" and norm_kind("Service Request") == "support"
    assert norm_kind("Epic") == "feature" and norm_kind("") is None
    assert norm_priority("Blocker") == "high" and norm_priority("Trivial") == "low"
