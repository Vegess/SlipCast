"""Control Room: promises due in the next 7 days across a workspace, and its live stream."""

import threading
from datetime import UTC, date, datetime, timedelta

from app.config import get_settings
from app.services.live import broker


def _demo(client, u, template):
    r = client.post(f"/api/workspaces/{u['workspace_id']}/demo-project?template={template}", headers=u["headers"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_empty_workspace_says_why(client, make_user):
    u = make_user()
    r = client.get(f"/api/workspaces/{u['workspace_id']}/control-room", headers=u["headers"]).json()
    assert r["available"] is False and "No projects yet" in r["reason"] and r["promises"] == []


def test_all_three_modules_in_one_view(client, make_user):
    u = make_user()
    ids = {t: _demo(client, u, t) for t in ("software", "shipments", "services")}
    r = client.get(f"/api/workspaces/{u['workspace_id']}/control-room", headers=u["headers"]).json()
    assert r["available"], r

    assert [m["template"] for m in r["modules"]] == ["software", "shipments", "services"]
    for m in r["modules"]:  # every module has a scored track record from the shared ledger
        assert m["scored"] > 0 and 0 <= m["hit_rate"] <= 1, m
    assert {p["id"] for p in r["projects"]} == set(ids.values())

    promises = r["promises"]
    assert {p["template"] for p in promises} == {"software", "shipments", "services"}
    last = (date.fromisoformat(r["days"][0]) + timedelta(days=7)).isoformat()
    assert all(p["due"] and p["due"] <= last for p in promises)
    order = {"high": 0, "medium": 1, "low": 2, None: 3}
    levels = [order[p["level"]] for p in promises]
    assert levels == sorted(levels)  # riskiest first
    assert r["counts"]["due_soon"] == sum(c["due_soon"] for c in r["projects"])

    # The risk shown here is the module's own: compare with the project's screen.
    order_promise = next(p for p in promises if p["template"] == "shipments")
    ship = client.get(f"/api/projects/{ids['shipments']}/analytics/ship", headers=u["headers"]).json()
    assert {o["id"]: o["risk"] for o in ship["at_risk"]}[order_promise["id"]] == order_promise["risk"]
    job = next(p for p in promises if p["template"] == "services")
    serve = client.get(f"/api/projects/{ids['services']}/analytics/serve", headers=u["headers"]).json()
    assert {j["id"]: j["risk"] for j in serve["upcoming"]}[job["id"]] == job["risk"]

    feed = r["activity"]
    assert feed and [a["at"] for a in feed] == sorted((a["at"] for a in feed), reverse=True)
    assert {a["project_id"] for a in feed} <= set(ids.values())


def test_small_project_overdue_ticket_shows_up(client, make_user):
    u = make_user()
    pid = client.post(
        f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "Tiny"}, headers=u["headers"]
    ).json()["id"]
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    later = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
    client.post(f"/api/projects/{pid}/tasks", json={"title": "Fix login", "due": yesterday}, headers=u["headers"])
    client.post(f"/api/projects/{pid}/tasks", json={"title": "Later", "due": later}, headers=u["headers"])
    r = client.get(f"/api/workspaces/{u['workspace_id']}/control-room", headers=u["headers"]).json()
    assert [p["title"] for p in r["promises"]] == ["Fix login"]  # the one due next month isn't shown
    p = r["promises"][0]
    assert p["risk"] == 1.0 and p["level"] == "high" and p["reasons"][0].startswith("Overdue since")
    assert r["counts"]["overdue"] == 1 and r["modules"][0]["hit_rate"] is None  # nothing scored yet
    assert [a["title"] for a in r["activity"]][:1] in (["Later"], ["Fix login"])


def test_workspace_stream_hears_every_project(client, make_user, monkeypatch):
    monkeypatch.setenv("STREAM_MAX_SECONDS", "2")
    get_settings.cache_clear()
    try:
        u = make_user()
        a = client.post(f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "A"}, headers=u["headers"])
        b = client.post(f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "B"}, headers=u["headers"])
        pa, pb = a.json()["id"], b.json()["id"]
        ws = u["workspace_id"]
        token = client.post(f"/api/workspaces/{ws}/stream-token", headers=u["headers"]).json()["token"]
        timers = [
            threading.Timer(0.4, broker.publish, args=(pa, {"type": "change", "task_ids": ["t1"]})),
            threading.Timer(0.6, broker.publish, args=(pb, {"type": "alert", "alert": {"title": "Forecast slipped"}})),
        ]
        for t in timers:
            t.start()
        with client.stream("GET", f"/api/workspaces/{ws}/stream", params={"token": token}) as r:
            assert r.status_code == 200
            lines = [line for line in r.iter_lines() if line]
        for t in timers:
            t.join()
        data = "\n".join(lines)
        assert "event: change" in data and f'"project_id": "{pa}"' in data
        assert "event: alert" in data and f'"project_id": "{pb}"' in data
        assert broker.listeners(pa) == 0 and broker.listeners(pb) == 0  # cleaned up

        # A project-stream token doesn't open the workspace stream.
        project_token = client.post(f"/api/projects/{pa}/stream-token", headers=u["headers"]).json()["token"]
        assert client.get(f"/api/workspaces/{ws}/stream", params={"token": project_token}).status_code == 401
    finally:
        get_settings.cache_clear()
