"""Real-time engine: API keys, event ingestion, alerts and the live stream."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.config import get_settings
from app.services.live import limiter


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


def _project(client, u, name="Live project"):
    return client.post(
        f"/api/workspaces/{u['workspace_id']}/projects", json={"name": name}, headers=u["headers"]
    ).json()


def _key(client, u, pid):
    r = client.post(f"/api/projects/{pid}/api-keys", json={"name": "Order system"}, headers=u["headers"])
    assert r.status_code == 201, r.text
    return r.json()["key"]


def _post(client, pid, key, body):
    return client.post(f"/api/projects/{pid}/events", json=body, headers={"X-SlipCast-Key": key})


def _at(days_ago: float = 0, hour: int = 9) -> str:
    return (
        (datetime.now(UTC) - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()
    )


def test_software_projects_use_the_four_statuses_as_stages(client, make_user):
    u = make_user()
    p = _project(client, u)
    r = client.get(f"/api/projects/{p['id']}/stages", headers=u["headers"]).json()
    assert r["template"] == "software"
    assert [(s["key"], s["category"]) for s in r["stages"]][:4] == [
        ("planned", "todo"),
        ("in_progress", "doing"),
        ("blocked", "blocked"),
        ("done", "done"),
    ]
    assert {"pr_opened", "pr_merged", "release_tagged", "deployed"} <= {s["key"] for s in r["stages"]}


def test_keys_are_shown_once_admin_only_and_revocable(client, make_user):
    u = make_user()
    pid = _project(client, u)["id"]
    key = _key(client, u, pid)
    assert key.startswith("sck_") and len(key) > 40
    listed = client.get(f"/api/projects/{pid}/api-keys", headers=u["headers"]).json()
    assert len(listed) == 1 and listed[0]["key"] is None and key.startswith(listed[0]["prefix"])

    assert _post(client, pid, key, {"external_id": "A-1", "stage": "planned"}).status_code == 200
    assert client.delete(f"/api/projects/{pid}/api-keys/{listed[0]['id']}", headers=u["headers"]).status_code == 204
    r = _post(client, pid, key, {"external_id": "A-2", "stage": "planned"})
    assert r.status_code == 401 and "isn't valid" in r.json()["detail"]
    assert client.get(f"/api/projects/{pid}/api-keys", headers=u["headers"]).json() == []


def test_events_need_a_key_for_this_project(client, make_user):
    alice, bob = make_user("alice@example.com", "Alice"), make_user("bob@example.com", "Bob")
    pa, pb = _project(client, alice)["id"], _project(client, bob)["id"]
    bob_key = _key(client, bob, pb)
    assert client.post(f"/api/projects/{pa}/events", json={"external_id": "x", "stage": "planned"}).status_code == 401
    assert _post(client, pa, "sck_made-up", {"external_id": "x", "stage": "planned"}).status_code == 401
    assert _post(client, pa, bob_key, {"external_id": "x", "stage": "planned"}).status_code == 401  # wrong project
    assert client.get(f"/api/projects/{pa}/tasks", headers=alice["headers"]).json() == []


def test_events_create_items_move_them_and_ignore_duplicates(client, make_user):
    u = make_user()
    pid = _project(client, u)["id"]
    key = _key(client, u, pid)
    batch = {
        "events": [
            {
                "external_id": "ORD-1",
                "stage": "planned",
                "occurred_at": _at(5),
                "title": "Ship order 1",
                "due": str(date.today() + timedelta(days=3)),
                "attributes": {"carrier": "BlueDart"},
            },
            {"external_id": "ORD-1", "stage": "in_progress", "occurred_at": _at(3)},
            {"external_id": "ORD-2", "stage": "planned", "occurred_at": _at(4)},
            {"external_id": "ORD-2", "stage": "teleported", "occurred_at": _at(2)},
        ]
    }
    r = _post(client, pid, key, batch).json()
    assert (r["created"], r["updated"], r["duplicates"], r["accepted"]) == (2, 0, 0, 3)
    assert len(r["errors"]) == 1 and "Unknown stage 'teleported'" in r["errors"][0]["error"]

    tasks = client.get(f"/api/projects/{pid}/tasks", headers=u["headers"]).json()
    one = next(t for t in tasks if t["title"] == "Ship order 1")
    two = next(t for t in tasks if t["title"] == "ORD-2")  # no title: the id stands in
    assert one["status"] == "in_progress" and one["started_at"][:10] == _at(3)[:10]  # the real time, not now
    assert one["attributes"] == {"carrier": "BlueDart"} and two["status"] == "planned"

    # the same batch again changes nothing
    again = _post(client, pid, key, batch).json()
    assert (again["duplicates"], again["created"], again["updated"]) == (3, 0, 0)
    # without occurred_at each send is a new moment, but repeating the current stage still changes nothing
    same = _post(client, pid, key, {"external_id": "ORD-2", "stage": "planned"}).json()
    assert (same["unchanged"], same["updated"], same["duplicates"]) == (1, 0, 0)

    # finishing; then an older event arrives late and must not move it back
    done = _post(client, pid, key, {"external_id": "ORD-1", "stage": "done", "occurred_at": _at(1)}).json()
    assert done["updated"] == 1
    late = _post(client, pid, key, {"external_id": "ORD-1", "stage": "blocked", "occurred_at": _at(2, hour=10)}).json()
    assert late["out_of_order"] == 1
    one = next(
        t for t in client.get(f"/api/projects/{pid}/tasks", headers=u["headers"]).json() if t["title"] == "Ship order 1"
    )
    assert one["status"] == "done" and one["completed_at"][:10] == _at(1)[:10]

    future = _post(client, pid, key, {"external_id": "ORD-3", "stage": "planned", "occurred_at": _at(-2)}).json()
    assert future["errors"][0]["error"] == "occurred_at is in the future"


def test_rate_limit_counts_events_per_key(client, make_user, monkeypatch):
    monkeypatch.setenv("EVENTS_PER_MINUTE", "5")
    get_settings.cache_clear()
    try:
        u = make_user()
        pid = _project(client, u)["id"]
        key = _key(client, u, pid)
        events = [{"external_id": f"E-{i}", "stage": "planned"} for i in range(4)]
        assert _post(client, pid, key, {"events": events}).status_code == 200
        r = _post(client, pid, key, {"events": events[:2]})
        assert r.status_code == 429 and r.headers["retry-after"] == "60"
    finally:
        get_settings.cache_clear()


def test_new_work_that_moves_the_forecast_raises_an_alert(client, demo):
    h, pid, ws = demo["headers"], demo["project_id"], demo["workspace_id"]
    key = _key(client, demo, pid)
    # one small change barely moves the forecast, so no alert
    _post(client, pid, key, {"external_id": "BASE-1", "stage": "planned"})
    assert [
        a for a in client.get(f"/api/projects/{pid}/alerts", headers=h).json() if a["kind"].startswith("forecast")
    ] == []

    # a big batch of new work pushes the 85% date out
    events = [{"external_id": f"NEW-{i}", "stage": "planned", "title": f"Customer import job {i}"} for i in range(60)]
    r = _post(client, pid, key, {"events": events}).json()
    assert r["created"] == 60
    alerts = client.get(f"/api/projects/{pid}/alerts", headers=h).json()
    slip = [a for a in alerts if a["kind"] == "forecast_slip"]
    assert len(slip) == 1 and slip[0]["data"]["days"] >= 2 and "moved later" in slip[0]["message"]
    assert client.get(f"/api/workspaces/{ws}/alerts", headers=h).json()[0]["project_name"] == "Atlas Billing (demo)"


def test_many_risky_new_items_become_one_alert(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    key = _key(client, demo, pid)
    soon = str(date.today() + timedelta(days=1))
    events = [
        {
            "external_id": f"R-{i}",
            "stage": "planned",
            "title": f"Fix stuff {i}",
            "due": soon,
            "owner": "Arun",
            "priority": "high",
        }
        for i in range(6)
    ]
    _post(client, pid, key, {"events": events})
    risky = [a for a in client.get(f"/api/projects/{pid}/alerts", headers=h).json() if a["kind"] == "high_risk"]
    assert len(risky) == 1 and risky[0]["data"]["count"] == 6 and "6 new items" in risky[0]["message"]


def test_risky_new_item_raises_an_alert(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    key = _key(client, demo, pid)
    soon = str(date.today() + timedelta(days=1))
    _post(
        client,
        pid,
        key,
        {
            "external_id": "RISK-1",
            "stage": "planned",
            "title": "Fix stuff",
            "due": soon,
            "owner": "Arun",
            "priority": "high",
        },
    )
    risky = [a for a in client.get(f"/api/projects/{pid}/alerts", headers=h).json() if a["kind"] == "high_risk"]
    assert risky and "Fix stuff" in risky[0]["message"] and risky[0]["data"]["risk"] >= 0.6


def test_small_project_events_work_without_alerts(client, make_user):
    u = make_user()
    pid = _project(client, u)["id"]
    key = _key(client, u, pid)
    r = _post(client, pid, key, {"external_id": "ONLY-1", "stage": "done", "due": str(date.today())})
    assert r.status_code == 200 and r.json()["created"] == 1
    assert client.get(f"/api/projects/{pid}/alerts", headers=u["headers"]).json() == []


def test_member_and_viewer_cannot_manage_keys(client, make_user):
    alice, mia = make_user("alice@example.com", "Alice"), make_user("mia@example.com", "Mia")
    token = (
        client.post(
            f"/api/workspaces/{alice['workspace_id']}/invites", json={"role": "member"}, headers=alice["headers"]
        )
        .json()["url"]
        .rsplit("/", 1)[1]
    )
    client.post(f"/api/invites/{token}/accept", headers=mia["headers"])
    pid = _project(client, alice)["id"]
    assert client.post(f"/api/projects/{pid}/api-keys", json={"name": "x"}, headers=mia["headers"]).status_code == 403
    assert client.get(f"/api/projects/{pid}/api-keys", headers=mia["headers"]).status_code == 403
    # but members can watch live and read alerts
    assert client.post(f"/api/projects/{pid}/stream-token", headers=mia["headers"]).status_code == 200
    assert client.get(f"/api/projects/{pid}/alerts", headers=mia["headers"]).status_code == 200


def test_stream_rejects_bad_tokens(client, make_user):
    alice, bob = make_user("alice@example.com", "Alice"), make_user("bob@example.com", "Bob")
    pa, pb = _project(client, alice)["id"], _project(client, bob)["id"]
    assert client.get(f"/api/projects/{pa}/stream", params={"token": "nope"}).status_code == 401
    bob_token = client.post(f"/api/projects/{pb}/stream-token", headers=bob["headers"]).json()["token"]
    assert client.get(f"/api/projects/{pa}/stream", params={"token": bob_token}).status_code == 401  # other project
    # a stream token is never a login
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {bob_token}"}).status_code == 401


def test_stream_delivers_messages_published_while_open(client, make_user, monkeypatch):
    """The test client runs a stream to completion before returning it, so publish from a timer."""
    import threading

    from app.services.live import broker

    monkeypatch.setenv("STREAM_MAX_SECONDS", "2")
    get_settings.cache_clear()
    try:
        u = make_user()
        pid = _project(client, u)["id"]
        token = client.post(f"/api/projects/{pid}/stream-token", headers=u["headers"]).json()["token"]
        timer = threading.Timer(
            0.5, broker.publish, args=(pid, {"type": "change", "source": "events", "task_ids": ["t1"]})
        )
        timer.start()
        with client.stream("GET", f"/api/projects/{pid}/stream", params={"token": token}) as r:
            assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
            lines = [line for line in r.iter_lines() if line]
        timer.join()
        assert lines[:2] == ["retry: 3000", "event: ready"]
        i = lines.index("event: change")
        assert '"task_ids": ["t1"]' in lines[i + 1]
        assert broker.listeners(pid) == 0  # the subscription is cleaned up when the stream ends
    finally:
        get_settings.cache_clear()


def test_events_and_app_edits_notify_live_screens(client, demo, monkeypatch):
    from app.services import live

    sent = []
    monkeypatch.setattr(live.broker, "publish", lambda pid, msg: sent.append((pid, msg)))
    h, pid = demo["headers"], demo["project_id"]
    key = _key(client, demo, pid)
    _post(
        client,
        pid,
        key,
        {
            "external_id": "N-1",
            "stage": "planned",
            "title": "Fix stuff",
            "due": str(date.today() + timedelta(days=1)),
            "owner": "Arun",
            "priority": "high",
        },
    )
    kinds = [m["type"] for p, m in sent if p == pid]
    assert kinds[0] == "change" and "alert" in kinds  # the screen refreshes first, then the alert arrives
    sent.clear()
    t = client.post(f"/api/projects/{pid}/tasks", json={"title": "Typed in the app"}, headers=h).json()
    client.patch(f"/api/tasks/{t['id']}", json={"status": "in_progress"}, headers=h)
    client.delete(f"/api/tasks/{t['id']}", headers=h)
    assert [(m["source"], m["deleted"]) for _, m in sent] == [("app", False), ("app", False), ("app", True)]
