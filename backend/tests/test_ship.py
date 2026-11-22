"""Ship module: orders, on-time delivery by carrier and route, estimates and late risk."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.services.live import limiter


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def ship_demo(client, make_user):
    u = make_user()
    r = client.post(f"/api/workspaces/{u['workspace_id']}/demo-project?template=shipments", headers=u["headers"])
    assert r.status_code == 201, r.text
    return {**u, "project": r.json()}


def _orders_project(client, u):
    r = client.post(
        f"/api/workspaces/{u['workspace_id']}/projects",
        json={"name": "Shop", "template": "shipments"},
        headers=u["headers"],
    )
    assert r.status_code == 201, r.text
    assert r.json()["template"] == "shipments"
    pid = r.json()["id"]
    key = client.post(f"/api/projects/{pid}/api-keys", json={"name": "Shop"}, headers=u["headers"]).json()["key"]
    return pid, key


def _iso(at: datetime) -> str:
    return at.replace(microsecond=0).isoformat()


def _order(n: int, ordered: datetime, days: float | None, carrier: str, dest: str = "Delhi", promised: int = 4):
    """Events for one order: ordered, then delivered `days` later (None = still on the way)."""
    base = {
        "external_id": f"ORD-{n}", "title": f"Order #{n}", "owner": carrier, "item_type": "order",
        "due": (ordered + timedelta(days=promised)).date().isoformat(),
        "attributes": {"origin": "Chennai", "destination": dest, "carrier": carrier},
    }  # fmt: skip
    events = [{**base, "stage": "ordered", "occurred_at": _iso(ordered)}]
    events.append({**base, "stage": "in_transit", "occurred_at": _iso(ordered + timedelta(hours=6))})
    if days is not None:
        events.append({**base, "stage": "delivered", "occurred_at": _iso(ordered + timedelta(days=days))})
    return events


def test_demo_orders_find_the_planted_patterns(client, ship_demo):
    u, project = ship_demo, ship_demo["project"]
    assert project["template"] == "shipments" and 300 <= project["task_count"] <= 500
    again = client.post(f"/api/workspaces/{u['workspace_id']}/demo-project?template=shipments", headers=u["headers"])
    assert again.status_code == 200 and again.json()["id"] == project["id"]  # one demo per module

    stages = client.get(f"/api/projects/{project['id']}/stages", headers=u["headers"]).json()
    assert [s["key"] for s in stages["stages"]][:3] == ["ordered", "packed", "dispatched"]

    m = client.get(f"/api/projects/{project['id']}/analytics/ship", headers=u["headers"]).json()
    assert m["available"], m
    carriers = {c["carrier"]: c for c in m["carriers"]}
    assert set(carriers) == {"SwiftLine", "Coastal Express", "MetroPost", "Kite Logistics"}
    assert carriers["MetroPost"]["median_days"] > carriers["SwiftLine"]["median_days"]  # cheap and slow
    assert carriers["MetroPost"]["exception_rate"] > carriers["Coastal Express"]["exception_rate"]
    worst = m["routes"][0]
    assert worst["route"].endswith(("Guwahati", "Port Blair")), worst  # remote routes are under-promised
    assert m["counts"]["open"] >= 10 and m["at_risk"], m["counts"]
    assert [d["stage"] for d in m["dwell"]] == ["ordered", "packed", "dispatched", "in_transit", "out_for_delivery"]
    assert all(d["median_hours"] > 0 for d in m["dwell"])
    ev = m["evaluation"]
    assert ev["available"] and 0.6 <= ev["coverage_p10_p90"] <= 0.95, ev
    assert ev["mae_days"] < ev["baseline_mae_days"], ev  # route beats the overall median
    assert ev["risk_auc"] > ev["baseline_auc"], ev  # and the carrier's late rate

    health = client.get(f"/api/projects/{project['id']}/insights", headers=u["headers"]).json()
    text = " ".join(i["message"] for i in health["insights"])
    assert "order" in text and "task" not in text and "not started" not in text, text

    # Ticket-only analytics still run on orders (one engine), and the board lists them.
    assert client.get(f"/api/projects/{project['id']}/analytics/forecast", headers=u["headers"]).status_code == 200
    tasks = client.get(f"/api/projects/{project['id']}/tasks", headers=u["headers"]).json()
    assert len(tasks) == project["task_count"]


def test_write_time_estimate_for_a_new_order(client, ship_demo):
    u, pid = ship_demo, ship_demo["project"]["id"]
    due = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    body = {"origin": "Mumbai", "destination": "Guwahati", "carrier": "SwiftLine", "due": due}
    r = client.post(f"/api/projects/{pid}/ship/estimate", json=body, headers=u["headers"]).json()
    assert r["available"] and r["planned_days"] == 2
    assert "Guwahati" in r["basis"] and r["p10"] <= r["p50"] <= r["p90"]
    assert r["under_planned"] and r["late_share"] > 0.8

    busy = {"origin": "Chennai", "destination": "Bengaluru", "carrier": "MetroPost", "service": "standard"}
    r = client.post(f"/api/projects/{pid}/ship/estimate", json=busy, headers=u["headers"]).json()
    rates = [c["on_time_rate"] for c in r["carriers_on_route"]]
    assert len(rates) >= 2 and rates == sorted(rates, reverse=True)  # best carrier on the route first

    unknown = {"origin": "Nowhere", "destination": "Atlantis", "carrier": "Pigeon"}
    r = client.post(f"/api/projects/{pid}/ship/estimate", json=unknown, headers=u["headers"]).json()
    assert r["available"] is False and "Fewer than" in r["reason"]


def test_small_shop_says_why(client, make_user):
    u = make_user()
    pid, key = _orders_project(client, u)
    r = client.get(f"/api/projects/{pid}/analytics/ship", headers=u["headers"]).json()
    assert r["available"] is False and "0 delivered orders" in r["reason"]
    now = datetime.now(UTC)
    events = [e for i in range(5) for e in _order(i, now - timedelta(days=10 - i), 2, "A")]
    client.post(f"/api/projects/{pid}/events", json={"events": events}, headers={"X-SlipCast-Key": key})
    r = client.get(f"/api/projects/{pid}/analytics/ship", headers=u["headers"]).json()
    assert r["available"] is False and "5 delivered orders" in r["reason"] and r["counts"]["orders"] == 5
    est = client.post(f"/api/projects/{pid}/ship/estimate", json={"destination": "Delhi"}, headers=u["headers"])
    assert est.json()["available"] is False


def test_exact_numbers_and_risk_by_hand(client, make_user):
    """30 delivered orders with known times, so the rates and the risk can be checked by hand."""
    u = make_user()
    pid, key = _orders_project(client, u)
    now = datetime.now(UTC).replace(microsecond=0)
    events = []
    # Carrier A: 20 orders to Delhi, 2 days each (promised 4: all on time).
    for i in range(20):
        events += _order(i, now - timedelta(days=38 - i), 2, "A")
    # Carrier B: 10 orders to Delhi, 6 days each (promised 4: all late).
    for i in range(10):
        events += _order(100 + i, now - timedelta(days=30 - i), 6, "B")
    # Open orders, promised 4 days: one B and one A order 1 day old, and an A order 3 days old.
    events += _order(901, now - timedelta(days=1), None, "B")
    events += _order(902, now - timedelta(days=1), None, "A")
    events += _order(900, now - timedelta(days=3), None, "A")
    r = client.post(f"/api/projects/{pid}/events", json={"events": events}, headers={"X-SlipCast-Key": key})
    assert r.status_code == 200 and r.json()["errors"] == [], r.text

    m = client.get(f"/api/projects/{pid}/analytics/ship", headers=u["headers"]).json()
    assert m["available"], m
    assert m["on_time"]["all_time"] == round(20 / 30, 3)
    carriers = {c["carrier"]: c for c in m["carriers"]}
    assert carriers["A"]["on_time_rate"] == 1.0 and carriers["A"]["median_days"] == 2.0
    assert carriers["B"]["on_time_rate"] == 0.0 and carriers["B"]["median_days"] == 6.0
    assert m["routes"][0]["route"] == "Chennai → Delhi" and m["routes"][0]["delivered"] == 30

    risk = {r["external_id"]: r for r in m["at_risk"]}
    # Every order shares the route, so the route's late rate equals the overall 1/3 and the risk
    # is the carrier's late rate pulled toward 1/3 by 10 pseudo-orders:
    # B: (10 + 10/3) / (10 + 10) = 0.67; A: (0 + 10/3) / (20 + 10) = 0.11.
    assert risk["ORD-901"]["risk"] == 0.67 and risk["ORD-901"]["level"] == "high"
    assert risk["ORD-901"]["estimate"]["basis"] == "orders on Chennai → Delhi with B"
    assert "B: 67% late in the last 6 weeks" in risk["ORD-901"]["reasons"]
    assert risk["ORD-902"]["risk"] == 0.11 and risk["ORD-902"]["level"] == "low"
    # Every A order arrived in 2 days, so one still out at 3 days is flagged.
    assert risk["ORD-900"]["level"] == "high" and risk["ORD-900"]["reasons"][0].startswith("Already slower")
    assert risk["ORD-900"]["estimate"]["expected_by"] == now.date().isoformat()
    assert m["at_risk"][-1]["external_id"] == "ORD-902"


def test_past_due_and_exceptions_raise_risk(client, make_user):
    u = make_user()
    pid, key = _orders_project(client, u)
    now = datetime.now(UTC).replace(microsecond=0)
    events = [e for i in range(25) for e in _order(i, now - timedelta(days=40 - i), 2, "A")]
    late = _order(500, now - timedelta(days=6), None, "A", promised=3)
    stuck = _order(501, now - timedelta(days=1), None, "A")
    stuck.append({**stuck[0], "stage": "exception", "occurred_at": _iso(now - timedelta(hours=2))})
    events += late + stuck
    client.post(f"/api/projects/{pid}/events", json={"events": events}, headers={"X-SlipCast-Key": key})
    m = client.get(f"/api/projects/{pid}/analytics/ship", headers=u["headers"]).json()
    risk = {r["external_id"]: r for r in m["at_risk"]}
    assert risk["ORD-500"]["risk"] == 1.0 and risk["ORD-500"]["reasons"][0].startswith("Past the promised date")
    assert risk["ORD-501"]["level"] == "medium" and "exception" in " ".join(risk["ORD-501"]["reasons"])
    assert m["counts"]["exceptions_open"] == 1
    assert date.fromisoformat(risk["ORD-500"]["due"]) < now.date()


def test_orders_created_by_hand_with_stage_and_fields(client, make_user):
    u = make_user()
    pid, _ = _orders_project(client, u)
    body = {
        "title": "Order #77 · Chennai → Pune", "stage": "packed", "item_type": "order",
        "attributes": {"origin": "Chennai", "destination": "Pune", "carrier": "A"},
    }  # fmt: skip
    t = client.post(f"/api/projects/{pid}/tasks", json=body, headers=u["headers"])
    assert t.status_code == 201, t.text
    t = t.json()
    assert (t["stage"], t["status"], t["attributes"]["destination"]) == ("packed", "in_progress", "Pune")
    r = client.patch(f"/api/tasks/{t['id']}", json={"stage": "delivered"}, headers=u["headers"]).json()
    assert (r["stage"], r["status"]) == ("delivered", "done") and r["completed_at"]
    bad = client.patch(f"/api/tasks/{t['id']}", json={"stage": "teleported"}, headers=u["headers"])
    assert bad.status_code == 422 and "no stage called" in bad.text
    huge = {"title": "x", "attributes": {str(i): i for i in range(31)}}
    assert client.post(f"/api/projects/{pid}/tasks", json=huge, headers=u["headers"]).status_code == 422
