"""Serve module: service jobs, missed visits, job durations and technician load."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.live import limiter

IST = timedelta(hours=5, minutes=30)


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def serve_demo(client, make_user):
    u = make_user()
    r = client.post(f"/api/workspaces/{u['workspace_id']}/demo-project?template=services", headers=u["headers"])
    assert r.status_code == 201, r.text
    return {**u, "project": r.json()}


def _jobs_project(client, u):
    r = client.post(
        f"/api/workspaces/{u['workspace_id']}/projects",
        json={"name": "Repairs", "template": "services"},
        headers=u["headers"],
    )
    assert r.status_code == 201 and r.json()["template"] == "services", r.text
    pid = r.json()["id"]
    key = client.post(f"/api/projects/{pid}/api-keys", json={"name": "Desk"}, headers=u["headers"]).json()["key"]
    return pid, key


def _window(days_from_today: int, hour: int = 9) -> tuple[datetime, datetime]:
    """A 2-hour appointment window starting at `hour` local time (UTC+5:30), as UTC."""
    local = (datetime.now(UTC) + IST).date() + timedelta(days=days_from_today)
    start = datetime(local.year, local.month, local.day, tzinfo=UTC) + timedelta(hours=hour) - IST
    return start, start + timedelta(hours=2)


def _z(at: datetime) -> str:
    return at.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _job(n, tech, day, late=False, hours=1.0, service="AC service", stages=("on_site", "done"), hour=9):
    start, end = _window(day, hour)
    base = {
        "external_id": f"JOB-{n}", "title": f"Job #{n}", "owner": tech, "item_type": "job",
        "due": (start + IST).date().isoformat(),
        "attributes": {"service_type": service, "area": "Indiranagar", "technician": tech,
                       "window_start": _z(start), "window_end": _z(end), "estimate_hours": 1.0},
    }  # fmt: skip
    arrive = end + timedelta(minutes=40) if late else start + timedelta(minutes=10)
    times = {"booked": start - timedelta(days=2), "assigned": start - timedelta(hours=12), "on_site": arrive,
             "done": arrive + timedelta(hours=hours), "rescheduled": start - timedelta(hours=5),
             "cancelled": start - timedelta(hours=6)}  # fmt: skip
    now = datetime.now(UTC)
    stages = [s for s in ("booked", "assigned", *stages) if times[s] <= now]  # nothing from the future
    return [{**base, "stage": s, "occurred_at": _z(times[s])} for s in stages]


def _send(client, pid, key, events):
    r = client.post(f"/api/projects/{pid}/events", json={"events": events}, headers={"X-SlipCast-Key": key})
    assert r.status_code == 200 and r.json()["errors"] == [], r.text


def test_demo_jobs_find_the_planted_patterns(client, serve_demo):
    u, project = serve_demo, serve_demo["project"]
    assert project["template"] == "services" and 300 <= project["task_count"] <= 500
    again = client.post(f"/api/workspaces/{u['workspace_id']}/demo-project?template=services", headers=u["headers"])
    assert again.status_code == 200 and again.json()["id"] == project["id"]

    m = client.get(f"/api/projects/{project['id']}/analytics/serve", headers=u["headers"]).json()
    assert m["available"], m
    techs = {t["tech"]: t for t in m["technicians"]}
    assert set(techs) == {"Deepa", "Ravi", "Imran", "Manoj", "Kavya"}
    assert techs["Manoj"]["vs_estimate"] > techs["Deepa"]["vs_estimate"]  # slow vs fast
    assert techs["Manoj"]["on_time_rate"] == min(t["on_time_rate"] for t in techs.values())
    services = {s["service"]: s for s in m["services"]}
    assert m["services"][0]["service"] == "AC repair" and services["AC repair"]["vs_estimate"] > 1.2  # under-booked
    load = {b["band"]: b["missed_rate"] for b in m["load"]}
    assert load["heavy"] > load["normal"] > load["light"]  # busy days run late
    assert [d["stage"] for d in m["dwell"]] == ["booked", "scheduled", "assigned", "en_route", "on_site"]
    assert m["counts"]["rescheduled"] > 0 and m["counts"]["cancelled"] > 0 and m["upcoming"]
    ev = m["evaluation"]
    assert ev["available"] and ev["risk_auc"] > ev["baseline_auc"], ev  # beats the technician's record alone
    assert ev["mae_hours"] < ev["baseline_mae_hours"], ev  # beats the booked estimate
    assert 0.6 <= ev["coverage_p10_p90"] <= 0.95, ev

    health = client.get(f"/api/projects/{project['id']}/insights", headers=u["headers"]).json()
    text = " ".join(i["message"] for i in health["insights"])
    assert "task" not in text and "not started" not in text, text
    assert client.get(f"/api/projects/{project['id']}/analytics/forecast", headers=u["headers"]).status_code == 200


def test_booking_check_for_a_new_job(client, serve_demo):
    u, pid = serve_demo, serve_demo["project"]["id"]
    start, _ = _window(2, 16)
    body = {"service_type": "AC repair", "area": "Whitefield", "technician": "Manoj", "window_start": _z(start),
            "estimate_hours": 2}  # fmt: skip
    r = client.post(f"/api/projects/{pid}/serve/estimate", json=body, headers=u["headers"]).json()
    assert r["available"] and r["duration"]["basis"].startswith("AC repair jobs")
    assert r["estimate_short"] is True and r["duration"]["p50"] > 2
    assert 0 < r["miss_risk"]["risk"] < 1 and r["miss_risk"]["jobs_that_day"] >= 1
    assert r["technicians"] and all("on_time_rate" in t for t in r["technicians"])

    unknown = {"service_type": "Moon landing", "technician": "Nobody"}
    r = client.post(f"/api/projects/{pid}/serve/estimate", json=unknown, headers=u["headers"]).json()
    assert r["available"] is False and "Fewer than" in r["reason"]


def test_small_team_says_why(client, make_user):
    u = make_user()
    pid, key = _jobs_project(client, u)
    r = client.get(f"/api/projects/{pid}/analytics/serve", headers=u["headers"]).json()
    assert r["available"] is False and "0 finished visits" in r["reason"]
    _send(client, pid, key, [e for i in range(4) for e in _job(i, "A", -5 + i)])
    r = client.get(f"/api/projects/{pid}/analytics/serve", headers=u["headers"]).json()
    assert r["available"] is False and "4 finished visits" in r["reason"] and r["counts"]["jobs"] == 4


def test_exact_numbers_and_risk_by_hand(client, make_user):
    """30 visits, all in the morning slot and one a day per technician, so slot and load rates
    equal the overall rate and the risk is the technician's late rate, which can be checked by hand."""
    u = make_user()
    pid, key = _jobs_project(client, u)
    events = []
    for i in range(20):  # A: on time, 1 hour each
        events += _job(i, "A", -30 + i)
    for i in range(10):  # B: arrives 40 minutes after the window, 2 hours each
        events += _job(100 + i, "B", -25 + i, late=True, hours=2)
    events += _job(200, "B", 1, stages=())  # upcoming, assigned
    events += _job(201, "A", 1, stages=())
    events += _job(202, "A", -1, stages=())  # yesterday's window passed with nobody on site
    events += _job(203, "A", -3, stages=("cancelled",))  # cancelled: not a visit
    _send(client, pid, key, events)

    m = client.get(f"/api/projects/{pid}/analytics/serve", headers=u["headers"]).json()
    assert m["available"], m
    assert m["counts"]["visits"] == 30 and m["counts"]["cancelled"] == 1
    assert m["on_time"]["all_time"] == round(20 / 30, 3)
    techs = {t["tech"]: t for t in m["technicians"]}
    assert techs["A"]["on_time_rate"] == 1.0 and techs["A"]["median_hours"] == 1.0
    assert techs["B"]["on_time_rate"] == 0.0 and techs["B"]["vs_estimate"] == 2.0
    assert techs["B"]["upcoming"] == 1

    up = {j["external_id"]: j for j in m["upcoming"]}
    # B: (10 + 10/3) / (10 + 10) = 0.67; A: (0 + 10/3) / (20 + 10) = 0.11.
    assert up["JOB-200"]["risk"] == 0.67 and up["JOB-200"]["level"] == "high"
    assert "B missed 67% in the last 6 weeks" in up["JOB-200"]["reasons"]
    assert up["JOB-200"]["duration"]["basis"] == "AC service jobs by B" and up["JOB-200"]["duration"]["p50"] == 2.0
    assert up["JOB-201"]["risk"] == 0.11 and up["JOB-201"]["level"] == "low"
    assert up["JOB-202"]["risk"] == 1.0 and up["JOB-202"]["reasons"][0].startswith("The window has passed")
    assert "JOB-203" not in up


def test_reschedules_count_as_missed(client, make_user):
    u = make_user()
    pid, key = _jobs_project(client, u)
    events = [e for i in range(20) for e in _job(i, "A", -25 + i)]
    events += [e for i in range(5) for e in _job(50 + i, "A", -4 + i // 3, stages=("rescheduled",), hour=15)]
    _send(client, pid, key, events)
    m = client.get(f"/api/projects/{pid}/analytics/serve", headers=u["headers"]).json()
    assert m["counts"]["rescheduled"] == 5 and m["on_time"]["all_time"] == round(20 / 25, 3)
    assert {t["tech"]: t for t in m["technicians"]}["A"]["rescheduled_rate"] == round(5 / 25, 3)
