"""Import history, profile updates and AI status (navigation pages)."""

CSV = (
    b"Issue key,Summary,Issue Type,Status,Created,Resolved\n"
    b"A-1,Fix login,Bug,Done,2026-09-01,2026-09-03\n"
    b"A-2,,Task,To Do,2026-09-02,\n"
    b"A-3,Add export,Story,In Progress,2026-09-04,\n"
)


def _import(client, u, name="jira.csv"):
    r = client.post(
        f"/api/workspaces/{u['workspace_id']}/import",
        files={"file": (name, CSV, "text/csv")},
        data={"project_name": "Billing"},
        headers=u["headers"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_imports_are_listed_with_their_report(client, make_user):
    u = make_user()
    first = _import(client, u, "first.csv")
    _import(client, u, "second.csv")
    rows = client.get(f"/api/workspaces/{u['workspace_id']}/imports", headers=u["headers"]).json()
    assert [r["filename"] for r in rows] == ["second.csv", "first.csv"], "newest first"
    r = rows[1]
    assert (r["rows_read"], r["imported"], r["skipped"]) == (3, 2, 1)
    assert r["project_id"] == first["project"]["id"] and r["project_name"] == "Billing"
    assert r["report"] == first["report"]
    one = client.get(f"/api/imports/{r['id']}", headers=u["headers"]).json()
    assert one["report"]["skipped_reasons"] == {"missing title": 1}


def test_import_history_survives_project_deletion(client, make_user):
    u = make_user()
    pid = _import(client, u)["project"]["id"]
    client.delete(f"/api/projects/{pid}", headers=u["headers"])
    rows = client.get(f"/api/workspaces/{u['workspace_id']}/imports", headers=u["headers"]).json()
    assert len(rows) == 1 and rows[0]["project_id"] is None and rows[0]["project_name"] == "Billing"


def test_profile_name_can_be_changed(client, make_user):
    u = make_user()
    r = client.patch("/api/auth/me", json={"name": "  Anirudh K  "}, headers=u["headers"])
    assert r.status_code == 200 and r.json()["name"] == "Anirudh K"
    assert client.get("/api/auth/me", headers=u["headers"]).json()["user"]["name"] == "Anirudh K"
    assert client.patch("/api/auth/me", json={"name": "   "}, headers=u["headers"]).status_code == 422


def test_ai_status_never_leaks_the_key(client, make_user, monkeypatch):
    from app.config import get_settings

    u = make_user()
    assert client.get("/api/auth/ai-status", headers=u["headers"]).json()["provider"] == "rules"
    monkeypatch.setattr(get_settings(), "groq_api_key", "gsk_secret_value")
    r = client.get("/api/auth/ai-status", headers=u["headers"])
    assert r.json()["provider"] == "groq" and r.json()["model"]
    assert "gsk_secret_value" not in r.text
    assert client.get("/api/auth/ai-status").status_code == 401


def test_imports_are_tenant_isolated(client, make_user):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    _import(client, alice)
    rec = client.get(f"/api/workspaces/{alice['workspace_id']}/imports", headers=alice["headers"]).json()[0]
    assert client.get(f"/api/workspaces/{alice['workspace_id']}/imports", headers=bob["headers"]).status_code == 404
    assert client.get(f"/api/imports/{rec['id']}", headers=bob["headers"]).status_code == 404
    assert client.get(f"/api/workspaces/{bob['workspace_id']}/imports", headers=bob["headers"]).json() == []
