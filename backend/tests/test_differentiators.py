"""Reference-class forecasting, the write-time ticket check and the forecast ledger (Phase 2B)."""

import time

import numpy as np

from app.services import reference_class

DETAILED_BUG = {
    "title": "Checkout fails when tax amount is empty",
    "description": (
        "When the tax amount is changed, the checkout returns an error instead of saving.\n\n"
        "Steps to reproduce:\n1. Open the checkout\n2. Update the tax amount\n3. Click save\n\n"
        "Expected result: the change is saved.\nActual result: error toast and nothing saved."
    ),
    "owner": "Arun",
    "due": "2030-01-10",
    "priority": "high",
    "kind": "bug",
}


# ---------- reference class ----------
def test_summarise_percentiles_and_plan_flag():
    sims = np.linspace(0.9, 0.2, 20)
    days = np.arange(1, 21, dtype=float)
    ref = reference_class.summarise(sims, days, np.zeros(20), planned_days=3)
    assert ref["available"] and ref["n"] == 20
    assert ref["p10"] < ref["p50"] < ref["p90"]
    assert ref["plan"]["under_planned"] is True and "Planned 3 days" in ref["plan"]["message"]
    assert reference_class.summarise(sims, days, np.zeros(20), planned_days=30)["plan"]["under_planned"] is False


def test_too_few_similar_tickets_says_so():
    sims = np.array([0.9, 0.5, 0.3, 0.1, 0.05])  # only 3 pass the 0.15 floor
    ref = reference_class.summarise(sims, np.ones(5), np.zeros(5))
    assert ref["available"] is False and ref["n"] == 3
    assert "Only 3 finished tickets" in ref["reason"]


def test_task_reference_class_excludes_itself(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    done = [t for t in client.get(f"/api/projects/{pid}/tasks", headers=h).json() if t["status"] == "done"]
    ref = client.get(f"/api/tasks/{done[0]['id']}/reference-class", headers=h).json()
    assert ref["available"] and ref["n"] >= 8
    assert done[0]["id"] not in [s["id"] for s in ref["similar"]]
    assert ref["actual_days"] >= 0 and "Tickets like this took" in ref["summary"]


def test_draft_reference_class(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    ref = client.post(f"/api/projects/{pid}/reference-class", json=DETAILED_BUG, headers=h).json()
    assert ref["available"] and len(ref["similar"]) == 3
    assert ref["plan"]["planned_days"] > 0
    nonsense = client.post(f"/api/projects/{pid}/reference-class", json={"title": "zzqx wobble"}, headers=h).json()
    assert nonsense["available"] is False and nonsense["reason"]


def test_reference_class_backtest_on_demo(client, demo):
    from app.db import get_db
    from app.main import app
    from app.services.analysis import get_analysis

    db = next(app.dependency_overrides[get_db]())
    result = reference_class.evaluate(get_analysis(db, demo["project_id"]).tickets)
    assert result["available"] and result["evaluated"] > 30
    assert 0.6 <= result["coverage_p10_p90"] <= 0.95  # target is about 80%
    assert result["p50_mae_days"] < result["baseline"]["p50_mae_days"]


# ---------- write-time ticket check ----------
def test_vague_ticket_scores_low_and_detailed_ticket_scores_high(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    vague = client.post(f"/api/projects/{pid}/ticket-check", json={"title": "Fix stuff"}, headers=h).json()
    assert vague["quality"]["score"] < 40
    reasons = " ".join(vague["quality"]["reasons"])
    assert "short" in reasons and "stuff" in reasons and "No description" in reasons
    good = client.post(f"/api/projects/{pid}/ticket-check", json=DETAILED_BUG, headers=h).json()
    assert good["quality"]["score"] >= 90 > vague["quality"]["score"]
    assert good["reference"]["available"]
    assert good["slip_risk"] is None or 0 <= good["slip_risk"]["risk"] <= 1


def test_ticket_check_finds_duplicates(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    again = next(
        t for t in client.get(f"/api/projects/{pid}/tasks", headers=h).json() if t["title"].startswith("Again: ")
    )
    original = again["title"].removeprefix("Again: ")
    r = client.post(
        f"/api/projects/{pid}/ticket-check",
        json={"title": original, "description": again["description"]},
        headers=h,
    ).json()
    assert any(d["id"] == again["id"] and d["similarity"] >= 0.72 for d in r["duplicates"])
    statuses = [d["status"] == "done" for d in r["duplicates"]]
    assert statuses == sorted(statuses), "open tickets are listed first"


def test_ticket_check_handles_empty_project(client, make_user):
    u = make_user()
    p = client.post(f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "New"}, headers=u["headers"]).json()
    r = client.post(f"/api/projects/{p['id']}/ticket-check", json={"title": "Fix stuff"}, headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["reference"]["available"] is False and r.json()["reference"]["reason"]


def test_ticket_check_is_fast_on_2000_tickets(client, make_user, monkeypatch):
    from app.routers import data
    from app.services import demo_data

    original = demo_data.generate
    monkeypatch.setattr(data.demo_data, "generate", lambda now: original(now, n=1990, days=365))
    u = make_user()
    pid = client.post(f"/api/workspaces/{u['workspace_id']}/demo-project", headers=u["headers"]).json()["id"]
    assert client.get(f"/api/projects/{pid}", headers=u["headers"]).json()["task_count"] >= 2000
    url = f"/api/projects/{pid}/ticket-check"
    client.post(url, json=DETAILED_BUG, headers=u["headers"])  # first call builds the cached analysis
    timings = []
    for i in range(5):
        start = time.perf_counter()
        r = client.post(url, json={**DETAILED_BUG, "title": DETAILED_BUG["title"] + f" {i}"}, headers=u["headers"])
        timings.append(time.perf_counter() - start)
        assert r.status_code == 200
    assert sorted(timings)[2] < 0.3, timings


# ---------- forecast ledger ----------
def test_demo_ledger_has_a_scored_track_record(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    led = client.get(f"/api/projects/{pid}/forecast-ledger", headers=h).json()
    assert led["available"] and led["resolved"] > 100
    assert led["project"]["resolved"] >= 10 and led["ticket"]["resolved"] >= 100
    assert 0.6 <= led["ticket"]["hit_rate_p85"] <= 0.98
    assert 0.6 <= led["project"]["hit_rate_p85"] <= 1
    assert len(led["entries"]) == 50 and led["unresolved"] > 0
    ticket_cal = {c["predicted"]: c["observed"] for c in led["calibration"] if c["kind"] == "ticket_reference_class"}
    assert ticket_cal[0.1] < ticket_cal[0.5] < ticket_cal[0.9]


def test_forecast_tab_records_once_per_day(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    before = client.get(f"/api/projects/{pid}/forecast-ledger", headers=h).json()["total"]
    for _ in range(3):
        client.get(f"/api/projects/{pid}/analytics/forecast", headers=h)
    after = client.get(f"/api/projects/{pid}/forecast-ledger", headers=h).json()
    assert after["total"] == before + 1
    newest = after["entries"][0]
    assert newest["kind"] == "project_completion" and newest["resolved"] is False


def test_ticket_start_is_recorded_then_scored_when_done(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    t = client.post(f"/api/projects/{pid}/tasks", json=DETAILED_BUG, headers=h).json()
    client.patch(f"/api/tasks/{t['id']}", json={"status": "in_progress"}, headers=h)
    client.patch(f"/api/tasks/{t['id']}", json={"status": "blocked"}, headers=h)
    client.patch(f"/api/tasks/{t['id']}", json={"status": "in_progress"}, headers=h)
    mine = [
        e
        for e in client.get(f"/api/projects/{pid}/forecast-ledger", headers=h).json()["entries"]
        if e.get("subject_id") == t["id"]
    ]
    assert len(mine) == 1 and not mine[0]["resolved"], "one forecast per ticket start"

    client.patch(f"/api/tasks/{t['id']}", json={"status": "done"}, headers=h)
    entry = next(
        e
        for e in client.get(f"/api/projects/{pid}/forecast-ledger", headers=h).json()["entries"]
        if e.get("subject_id") == t["id"]
    )
    assert entry["resolved"] and entry["actual"] is not None and entry["hit_p85"] is True  # finished instantly


def test_deleted_subject_is_voided(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    t = client.post(f"/api/projects/{pid}/tasks", json={**DETAILED_BUG, "status": "in_progress"}, headers=h).json()
    client.delete(f"/api/tasks/{t['id']}", headers=h)
    led = client.get(f"/api/projects/{pid}/forecast-ledger", headers=h).json()
    assert led["void"] == 1


def test_small_project_ledger_explains_itself(client, make_user):
    u = make_user()
    p = client.post(f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "New"}, headers=u["headers"]).json()
    led = client.get(f"/api/projects/{p['id']}/forecast-ledger", headers=u["headers"]).json()
    assert led["available"] is False and led["reason"] and led["total"] == 0
