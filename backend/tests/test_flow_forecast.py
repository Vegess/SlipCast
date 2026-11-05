"""Flow metrics and Monte Carlo forecasting (Phase 2A)."""

from datetime import date, datetime, timedelta

import numpy as np

from app.services import flow, forecast
from app.services.analysis import build_frames


def test_constant_throughput_gives_exact_answer():
    weeks = forecast.simulate(np.array([5] * 12), remaining=20, sims=500)
    assert np.allclose(weeks, 4.0)
    result = forecast.forecast(np.array([5] * 12), 20, date(2026, 1, 5))["forecast"]
    assert result["weeks_p50"] == result["weeks_p85"] == result["weeks_p95"] == 4.0
    assert result["p85"] == "2026-02-02"  # 28 days later


def test_final_week_is_interpolated():
    # 7 per week and 10 remaining: one full week, then 3 of the next 7 -> 1.43 weeks
    weeks = forecast.simulate(np.array([7, 7, 7, 7]), remaining=10, sims=10)
    assert np.allclose(weeks, 1 + 3 / 7)


def test_forecast_reports_reasons_instead_of_crashing():
    today = date(2026, 1, 5)
    assert "nothing left" in forecast.forecast(np.array([3] * 12), 0, today)["forecast"]["reason"]
    assert "at least 4" in forecast.forecast(np.array([3, 2]), 10, today)["forecast"]["reason"]
    zero = forecast.forecast(np.array([0] * 12), 10, today)["forecast"]
    assert zero["available"] is False and "No tickets were finished" in zero["reason"]


def test_demo_forecast_is_ordered_and_sums_to_one(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    data = client.get(f"/api/projects/{pid}/analytics/forecast", headers=h).json()
    f = data["forecast"]
    assert f["available"] and f["simulations"] == 10_000
    assert f["weeks_p50"] < f["weeks_p85"] < f["weeks_p95"]
    assert f["p50"] <= f["p85"] <= f["p95"]
    assert abs(sum(b["probability"] for b in f["histogram"]) - 1) < 0.01
    assert len(f["history_weeks"]) == 12
    b = data["burnup"]
    assert b["scope"][-1] == len(client.get(f"/api/projects/{pid}/tasks", headers=h).json())
    assert b["projection"]["p85"][1] == [f["p85"], b["scope"][-1]]


def test_target_probability_rises_with_later_targets(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    url = f"/api/projects/{pid}/analytics/forecast"
    today = date.today()
    probs = [
        client.get(url, params={"target": (today + timedelta(days=d)).isoformat()}, headers=h).json()["forecast"][
            "target_probability"
        ]
        for d in (3, 14, 120)
    ]
    assert probs == sorted(probs)
    assert probs[0] < 0.5 and probs[-1] == 1.0


def test_demo_flow_metrics(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    f = client.get(f"/api/projects/{pid}/analytics/flow", headers=h).json()
    tasks = client.get(f"/api/projects/{pid}/tasks", headers=h).json()
    p = f["cycle_time"]["percentiles"]
    assert f["available"] and p["p50"] < p["p85"] < p["p95"]
    assert len(f["cycle_time"]["points"]) == sum(t["status"] == "done" for t in tasks)
    assert len(f["throughput"]["weeks"]) == 26 == len(f["throughput"]["counts"])
    # On the last day, the cumulative flow matches the board exactly
    assert len(f["cfd"]["dates"]) == 120
    for status in ("planned", "in_progress", "blocked", "done"):
        assert f["cfd"]["series"][status][-1] == sum(t["status"] == status for t in tasks)
    assert {r["key"] for r in f["by_kind"]} >= {"bug", "feature", "tech_debt", "support"}
    assert sum(r["open"] + r["done"] for r in f["by_owner"]) == len(tasks)
    ages = [a["age_days"] for a in f["aging"]]
    assert ages == sorted(ages, reverse=True)
    assert any(a["over_p85"] for a in f["aging"])


def test_overview(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    o = client.get(f"/api/projects/{pid}/analytics/overview", headers=h).json()
    assert o["open"] + o["done"] == o["tickets"]
    assert o["cycle"]["p50"] < o["cycle"]["p85"]
    assert o["throughput_avg"] > 0 and o["forecast_p85"]


def test_small_project_returns_reasons(client, make_user):
    u = make_user()
    p = client.post(f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "Tiny"}, headers=u["headers"]).json()
    for title in ("One", "Two"):
        client.post(f"/api/projects/{p['id']}/tasks", json={"title": title}, headers=u["headers"])
    base = f"/api/projects/{p['id']}/analytics"
    fl = client.get(f"{base}/flow", headers=u["headers"]).json()
    assert fl["available"] is False and "at least 5 finished" in fl["reason"]
    fc = client.get(f"{base}/forecast", headers=u["headers"]).json()["forecast"]
    assert fc["available"] is False and fc["reason"]
    ov = client.get(f"{base}/overview", headers=u["headers"]).json()
    assert ov["open"] == 2 and ov["forecast_p85"] is None


def test_empty_project_does_not_crash(client, make_user):
    u = make_user()
    p = client.post(
        f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "Empty"}, headers=u["headers"]
    ).json()
    for path in ("overview", "flow", "forecast"):
        r = client.get(f"/api/projects/{p['id']}/analytics/{path}", headers=u["headers"])
        assert r.status_code == 200, (path, r.text)


def test_cycle_time_falls_back_to_created_and_cfd_uses_history():
    now = datetime(2026, 3, 2, 12)
    created = now - timedelta(days=10)
    rows = [
        # never marked in progress: cycle measured from creation
        ("a", "A", "", "", "done", "medium", None, "bug", "label", created, None, created + timedelta(days=4), now),
        ("b", "B", "", "", "in_progress", "medium", None, None, "", created, created + timedelta(days=1), None, now),
    ]
    tickets, events = build_frames(rows, [])
    assert tickets.loc[tickets["id"] == "a", "cycle_days"].item() == 4.0
    cfd = flow.cumulative_flow(tickets, events, now, days=10)
    assert cfd["series"]["done"][-1] == 1 and cfd["series"]["in_progress"][-1] == 1
    assert cfd["series"]["planned"][0] == 1  # first day: a still planned, b already started
