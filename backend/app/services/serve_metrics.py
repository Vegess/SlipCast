"""Serve module metrics: missed visits, real job durations, technician load and breakdowns.

- A visit is **missed** when the technician arrives after the appointment window ends, or the
  job is rescheduled. Cancelled jobs that were never rescheduled don't count either way.
- **Missed-visit risk** combines three miss rates: the technician's over the last 6 weeks,
  visits on days as busy as this one for the technician (up to 2 jobs, 3, or 4 or more), and
  visits in the same window of the day. Each is pulled toward the overall rate when based on
  few visits, and they are combined in log-odds, so each can be shown as a reason. (The
  area was tested too and added nothing, so it appears only in the breakdowns.)
- **Job duration** (on site to done) comes from a reference class: the same service by the
  same technician, else the same service, else the technician's jobs, with at least 8 jobs.
  The baseline is the estimate written on the booking.
- Both are back-tested on the newest 30% of visits, using only visits finished 12 hours
  before each one's window.
"""

from datetime import date, datetime, timedelta

import numpy as np
from sklearn.metrics import roc_auc_score
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BUILD_TYPES, IngestedEvent, Task
from app.services.ship_metrics import _logit, _pct, _r, _rate
from app.timeutil import naive_utc

IST = timedelta(hours=5, minutes=30)  # appointment windows are shown in local time
MIN_VISITS = 20
MIN_CLASS = 8
MIN_GROUP = 5
WEEKS = 10
RECENT = timedelta(days=42)
SMOOTHING = 10
HIGH, MEDIUM = 0.5, 0.25
CLOSED = ("done", "cancelled")
FLOW = ["booked", "scheduled", "assigned", "en_route", "on_site", "done"]
FLOW_LABELS = {
    "booked": "Booked → scheduled", "scheduled": "Scheduled → assigned", "assigned": "Assigned → en route",
    "en_route": "Travel (en route → on site)", "on_site": "On site → done",
}  # fmt: skip


def _parse(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return naive_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _num(value) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def band(n: int) -> str:
    return "light" if n <= 2 else "normal" if n == 3 else "heavy"


BAND_LABEL = {"light": "up to 2 jobs", "normal": "3 jobs", "heavy": "4 or more jobs"}


def slot_of(start: datetime | None) -> str:
    if start is None:
        return ""
    h = (start + IST).hour
    return "morning" if h < 12 else "midday" if h < 14 else "afternoon" if h < 16 else "late afternoon"


def local_day(start: datetime | None, due: date | None) -> date | None:
    return (start + IST).date() if start else due


def load_jobs(db: Session, project_id: str) -> list[dict]:
    rows = db.execute(
        select(
            Task.id, Task.external_id, Task.title, Task.owner, Task.status, Task.stage, Task.due,
            Task.attributes, Task.created_at,
        ).where(Task.project_id == project_id, Task.item_type.notin_(BUILD_TYPES))
    ).all()  # fmt: skip
    timeline: dict[str, dict[str, datetime]] = {}
    for ext, stage, at in db.execute(
        select(IngestedEvent.external_id, IngestedEvent.stage, IngestedEvent.occurred_at).where(
            IngestedEvent.project_id == project_id
        )
    ):
        at = naive_utc(at)
        st = timeline.setdefault(ext, {})
        if stage not in st or at < st[stage]:
            st[stage] = at
    jobs = []
    for tid, ext, title, owner, status, stage, due, attrs, created in rows:
        a, tl = attrs or {}, timeline.get(ext or "", {})
        start, end = _parse(a.get("window_start")), _parse(a.get("window_end"))
        on_site, done = tl.get("on_site"), tl.get("done")
        resched = "rescheduled" in tl
        missed = True if resched else (on_site > end if on_site and end else None)
        jobs.append({
            "id": tid, "external_id": ext, "title": title, "status": status, "stage": stage,
            "tech": (a.get("technician") or owner or "").strip(), "area": (a.get("area") or "").strip(),
            "service": (a.get("service_type") or "").strip(), "estimate": _num(a.get("estimate_hours")),
            "start": start, "end": end, "day": local_day(start, due), "created": naive_utc(created),
            "on_site": on_site, "done_at": done, "rescheduled": resched, "cancelled": stage == "cancelled",
            "missed": missed, "timeline": tl,
            "hours": (done - on_site).total_seconds() / 3600 if done and on_site and done > on_site else None,
            # When the outcome was known: arrival (or the reschedule), for the back-test.
            "known_at": tl.get("rescheduled") or on_site,
        })  # fmt: skip
    loads: dict[tuple, int] = {}
    for j in jobs:
        if j["tech"] and j["day"] and not j["cancelled"]:
            loads[(j["tech"], j["day"])] = loads.get((j["tech"], j["day"]), 0) + 1
    for j in jobs:
        j["load"] = loads.get((j["tech"], j["day"]), 0)
        j["band"] = band(j["load"])
        j["slot"] = slot_of(j["start"])
    return jobs


def miss_risk(pool: list[dict], job: dict, at: datetime) -> dict | None:
    """Chance a visit is missed, from the technician's recent record, the day's load and the slot."""
    visits = [p for p in pool if p["missed"] is not None]
    if len(visits) < MIN_VISITS:
        return None
    base = sum(p["missed"] for p in visits) / len(visits)

    def smoothed(group: list[dict]) -> tuple[float, int]:
        return (sum(p["missed"] for p in group) + SMOOTHING * base) / (len(group) + SMOOTHING), len(group)

    tech, n_tech = smoothed([p for p in visits if p["tech"] == job["tech"] and at - p["known_at"] <= RECENT])
    load, n_load = smoothed([p for p in visits if p["band"] == job["band"]])
    slot, n_slot = smoothed([p for p in visits if p["slot"] == job["slot"]])
    z = _logit(tech) + _logit(load) + _logit(slot) - 2 * _logit(base)
    return {
        "risk": 1 / (1 + np.exp(-z)), "tech_rate": round(tech, 3), "tech_n": n_tech, "load_rate": round(load, 3),
        "load_n": n_load, "slot_rate": round(slot, 3), "slot_n": n_slot, "overall_rate": round(base, 3),
    }  # fmt: skip


def duration_class(pool: list[dict], service: str, tech: str) -> dict | None:
    done = [p for p in pool if p["hours"] is not None]
    tiers = [
        (service and tech, f"{service} jobs by {tech}", lambda p: p["service"] == service and p["tech"] == tech),
        (service, f"{service} jobs", lambda p: p["service"] == service),
        (tech, f"jobs by {tech}", lambda p: p["tech"] == tech),
    ]
    for usable, basis, keep in tiers:
        if not usable:
            continue
        group = [p["hours"] for p in done if keep(p)]
        if len(group) >= MIN_CLASS:
            return {"basis": basis, "n": len(group), "p10": _pct(group, 10), "p25": _pct(group, 25),
                    "p50": _pct(group, 50), "p90": _pct(group, 90)}  # fmt: skip
    return None


def _reasons(job: dict, lr: dict | None, dur: dict | None) -> list[str]:
    out = []
    if lr:
        if lr["load_rate"] > lr["overall_rate"] * 1.25 and lr["load_n"] >= MIN_GROUP:
            out.append(f"{job['tech']} has {job['load']} jobs that day; {round(lr['load_rate'] * 100)}% of visits "
                       f"on days with {BAND_LABEL[job['band']]} were missed")  # fmt: skip
        if lr["tech_rate"] > lr["overall_rate"] * 1.25 and lr["tech_n"] >= MIN_GROUP:
            out.append(f"{job['tech']} missed {round(lr['tech_rate'] * 100)}% in the last 6 weeks")
        if lr["slot_rate"] > lr["overall_rate"] * 1.25 and lr["slot_n"] >= MIN_GROUP:
            out.append(f"{job['slot'].capitalize()} windows are missed {round(lr['slot_rate'] * 100)}% of the time")
    if dur and job["estimate"] is not None and job["estimate"] < dur["p25"]:
        out.append(f"Booked as {job['estimate']:g} h; {dur['basis']} took {dur['p10']}–{dur['p90']} h")
    return out


def _upcoming(job: dict, pool: list[dict], now: datetime) -> dict:
    lr = miss_risk(pool, job, now)
    dur = duration_class(pool, job["service"], job["tech"])
    risk = lr["risk"] if lr else None
    reasons = _reasons(job, lr, dur)
    if job["end"] and now > job["end"] and not job["on_site"]:
        risk = 1.0
        reasons.insert(0, "The window has passed and nobody is on site yet")
    level = None if risk is None else "high" if risk >= HIGH else "medium" if risk >= MEDIUM else "low"
    return {
        "id": job["id"], "external_id": job["external_id"], "title": job["title"], "tech": job["tech"],
        "area": job["area"], "service": job["service"], "stage": job["stage"],
        "window_start": job["start"].isoformat() + "Z" if job["start"] else None,
        "window_end": job["end"].isoformat() + "Z" if job["end"] else None,
        "load": job["load"], "estimate": job["estimate"], "duration": dur, "risk": _r(risk, 2), "level": level,
        "reasons": reasons[:3],
    }  # fmt: skip


def _group(jobs: list[dict], key: str) -> list[dict]:
    out = []
    for name in sorted({j[key] for j in jobs if j[key]}):
        mine = [j for j in jobs if j[key] == name]
        visits = [j["missed"] for j in mine if j["missed"] is not None]
        if len(visits) < MIN_GROUP:
            continue
        hours = [j["hours"] for j in mine if j["hours"] is not None]
        ratio = [j["hours"] / j["estimate"] for j in mine if j["hours"] is not None and j["estimate"]]
        estimates = [j["estimate"] for j in mine if j["estimate"]]
        out.append({
            key: name, "visits": len(visits), "on_time_rate": _r(1 - sum(visits) / len(visits), 3),
            "rescheduled_rate": _rate([j["rescheduled"] for j in mine if not j["cancelled"] or j["rescheduled"]]),
            "median_hours": _pct(hours, 50), "p10_hours": _pct(hours, 10), "p90_hours": _pct(hours, 90),
            "vs_estimate": _r(np.median(ratio), 2) if ratio else None,
            "estimate_hours": _r(np.median(estimates)) if estimates else None,
        })  # fmt: skip
    return out


def _evaluate(jobs: list[dict]) -> dict:
    visits = sorted((j for j in jobs if j["missed"] is not None and j["start"]), key=lambda j: j["start"])
    test = visits[int(len(visits) * 0.7) :]
    truth, scores, base_scores = [], [], []
    hits, err, base_err = [], [], []
    for j in test:
        pool = [p for p in visits if p["known_at"] and p["known_at"] < j["start"] - timedelta(hours=12)]
        lr = miss_risk(pool, j, j["start"])
        if lr is None:
            continue
        truth.append(j["missed"])
        scores.append(lr["risk"])
        mine = [p["missed"] for p in pool if p["tech"] == j["tech"]]
        base_scores.append(sum(mine) / len(mine) if mine else lr["overall_rate"])
        if j["hours"] is not None:
            dur = duration_class(pool, j["service"], j["tech"])
            if dur and j["estimate"]:
                hits.append(dur["p10"] <= j["hours"] <= dur["p90"])
                err.append(abs(j["hours"] - dur["p50"]))
                base_err.append(abs(j["hours"] - j["estimate"]))
    if len(truth) < 10 or len(set(truth)) < 2:
        return {"available": False, "reason": "Not enough finished visits yet to back-test the estimates."}
    return {
        "available": True, "tested": len(truth),
        "risk_auc": _r(roc_auc_score(truth, scores), 3), "baseline_auc": _r(roc_auc_score(truth, base_scores), 3),
        "duration_tested": len(hits), "coverage_p10_p90": _r(np.mean(hits), 3) if hits else None,
        "mae_hours": _r(np.mean(err), 2) if err else None,
        "baseline_mae_hours": _r(np.mean(base_err), 2) if err else None,
    }  # fmt: skip


def compute(db: Session, project_id: str, now: datetime) -> dict:
    now = naive_utc(now)
    jobs = load_jobs(db, project_id)
    visits = [j for j in jobs if j["missed"] is not None]
    if len(visits) < MIN_VISITS:
        return {
            "available": False,
            "reason": f"{len(visits)} finished visits so far. Missed-visit rates and job durations need at least "
            f"{MIN_VISITS}; send stage updates with the event API (Live feed tab) or open the demo jobs.",
            "counts": {"jobs": len(jobs), "visits": len(visits)},
        }

    def window(start: datetime, end: datetime) -> list[bool]:
        return [j["missed"] for j in visits if j["start"] and start <= j["start"] < end]

    recent, before = window(now - timedelta(days=28), now), window(now - timedelta(days=56), now - timedelta(days=28))
    hours = [j["hours"] for j in jobs if j["hours"] is not None]

    weekly = []
    week0 = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    for w in range(WEEKS, 0, -1):
        start = week0 - timedelta(weeks=w)
        flags = window(start, start + timedelta(weeks=1))
        resched = [j["rescheduled"] for j in visits if j["start"] and start <= j["start"] < start + timedelta(weeks=1)]
        weekly.append({
            "week": start.date().isoformat(), "visits": len(flags),
            "on_time_rate": _r(1 - sum(flags) / len(flags), 3) if flags else None,
            "rescheduled": sum(resched),
        })  # fmt: skip

    dwell = []
    for a, b in zip(FLOW, FLOW[1:], strict=False):
        gaps = [(j["timeline"][b] - j["timeline"][a]).total_seconds() / 3600 for j in jobs
                if a in j["timeline"] and b in j["timeline"] and j["timeline"][b] >= j["timeline"][a]]  # fmt: skip
        dwell.append({"stage": a, "label": FLOW_LABELS[a], "n": len(gaps),
                      "median_hours": _pct(gaps, 50), "p85_hours": _pct(gaps, 85)})  # fmt: skip

    finished = [j for j in jobs if j["known_at"] is not None]
    horizon = now + timedelta(days=7)
    open_jobs = [j for j in jobs if j["stage"] not in CLOSED and j["status"] != "done" and j["start"]
                 and j["start"] <= horizon]  # fmt: skip
    upcoming = [_upcoming(j, finished, now) for j in open_jobs]
    upcoming.sort(key=lambda u: (-(u["risk"] if u["risk"] is not None else -1), u["window_start"] or ""))

    techs = _group(jobs, "tech")
    for t in techs:
        ahead = [j for j in open_jobs if j["tech"] == t["tech"]]
        days: dict[date, list[dict]] = {}
        for j in ahead:
            days.setdefault(j["day"], []).append(j)
        busiest = max(days.items(), key=lambda kv: len(kv[1]), default=(None, []))
        t["upcoming"] = len(ahead)
        t["upcoming_hours"] = _r(sum(j["estimate"] or 0 for j in ahead))
        t["busiest_day"] = busiest[0].isoformat() if busiest[0] else None
        t["busiest_jobs"] = len(busiest[1])
    techs.sort(key=lambda t: -(t["on_time_rate"] or 0))
    areas = sorted(_group(jobs, "area"), key=lambda a: a["on_time_rate"] or 0)
    services = sorted(_group(jobs, "service"), key=lambda s: -(s["vs_estimate"] or 0))

    by_band = []
    for b in ("light", "normal", "heavy"):
        flags = [j["missed"] for j in visits if j["band"] == b]
        by_band.append({"band": b, "label": BAND_LABEL[b], "visits": len(flags), "missed_rate": _rate(flags)})

    return {
        "available": True,
        "counts": {
            "jobs": len(jobs),
            "visits": len(visits),
            "done": len(hours),
            "upcoming": len(open_jobs),
            "high_risk": sum(u["level"] == "high" for u in upcoming),
            "rescheduled": sum(j["rescheduled"] for j in jobs),
            "cancelled": sum(j["cancelled"] for j in jobs),
        },  # fmt: skip
        "on_time": {
            "value": _rate([not x for x in recent]),
            "previous": _rate([not x for x in before]),
            "all_time": _rate([not x for x in (j["missed"] for j in visits)]),
        },  # fmt: skip
        "duration": {"p50": _pct(hours, 50), "p85": _pct(hours, 85)},
        "weekly": weekly,
        "dwell": dwell,
        "load": by_band,
        "technicians": techs,
        "areas": areas,
        "services": services,
        "upcoming": upcoming[:25],
        "evaluation": _evaluate(jobs),
    }


def check(db: Session, project_id: str, service: str, area: str, tech: str, window_start: datetime | None,
          estimate: float | None, now: datetime) -> dict:  # fmt: skip
    """Write-time check for a job being booked: duration, missed-visit risk and who's free that day."""
    now = naive_utc(now)
    jobs = load_jobs(db, project_id)
    finished = [j for j in jobs if j["known_at"] is not None]
    start = naive_utc(window_start) if window_start else None
    day = local_day(start, None)
    booked = {}
    for j in jobs:
        if j["day"] == day and j["tech"] and not j["cancelled"] and j["stage"] != "done":
            booked[j["tech"]] = booked.get(j["tech"], 0) + 1
    out: dict = {"available": True}
    dur = duration_class(finished, service.strip(), tech.strip())
    out["duration"] = dur
    if dur and estimate is not None:
        out["estimate_short"] = estimate < dur["p25"]
    risk = None
    if tech.strip() and start:
        load = booked.get(tech.strip(), 0) + 1
        draft = {"tech": tech.strip(), "load": load, "band": band(load), "slot": slot_of(start), "estimate": estimate}
        lr = miss_risk(finished, draft, now)
        if lr:
            risk = {"risk": _r(lr["risk"], 2), "jobs_that_day": load, "reasons": _reasons(draft, lr, dur)}
    out["miss_risk"] = risk
    # Other technicians who do this service, with their record and how busy they are that day.
    options = []
    for t in sorted({j["tech"] for j in finished if j["tech"]}):
        mine = [j["missed"] for j in finished if j["tech"] == t and j["missed"] is not None]
        if len(mine) < MIN_GROUP or (service.strip() and not any(
                j["tech"] == t and j["service"] == service.strip() for j in finished)):  # fmt: skip
            continue
        options.append({"tech": t, "on_time_rate": _r(1 - sum(mine) / len(mine), 3),
                        "jobs_that_day": booked.get(t, 0) if day else None})  # fmt: skip
    out["technicians"] = sorted(options, key=lambda o: (o["jobs_that_day"] or 0, -(o["on_time_rate"] or 0)))
    if dur is None and risk is None:
        return {"available": False, "reason": f"Fewer than {MIN_CLASS} finished jobs like this yet, so there's "
                "nothing reliable to compare with.", "technicians": out["technicians"]}  # fmt: skip
    return out
