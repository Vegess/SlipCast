"""Forecast ledger: store every forecast, score it when the outcome arrives.

Two kinds of forecast are recorded:

* project_completion: made at most once per project per day when the Forecast tab
  loads. It predicts when the team will have finished as many tickets as were open
  at the time. That is exactly what a throughput Monte Carlo models, so it is also
  how the entry is scored: the actual date is the day the N-th ticket finished
  after the forecast was made.
* ticket_reference_class: made when a ticket moves to in progress. It predicts the
  ticket's cycle time from similar finished tickets, and is scored when it is done.
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Forecast
from app.services import flow, forecast, reference_class
from app.timeutil import naive_utc

if TYPE_CHECKING:
    from app.services.analysis import Analysis

PROJECT = "project_completion"
TICKET = "ticket_reference_class"
MIN_FINISHED_FOR_TICKET = 30


def _nth_completion_after(done_times: np.ndarray, after: datetime, n: int) -> pd.Timestamp | None:
    later = done_times[done_times > np.datetime64(after)]
    return pd.Timestamp(later[n - 1]) if n > 0 and later.size >= n else None


def _done_times(tickets: pd.DataFrame) -> np.ndarray:
    return np.sort(tickets.loc[tickets["finished"], "completed_at"].to_numpy(dtype="datetime64[ns]"))


def aware(dt: datetime) -> datetime:
    """Store UTC explicitly so Postgres timestamptz columns don't assume a local zone."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


# ---------- recording ----------
def record_project(db: Session, analysis: "Analysis") -> Forecast | None:
    """Store today's completion forecast unless one exists for this project today."""
    result = analysis.forecast()["forecast"]
    if not result["available"]:
        return None
    day_start = aware(datetime.combine(analysis.today, datetime.min.time()))
    existing = db.scalar(
        select(Forecast.id).where(
            Forecast.project_id == analysis.project_id, Forecast.kind == PROJECT, Forecast.made_at >= day_start
        )
    )
    if existing:
        return None
    entry = Forecast(
        project_id=analysis.project_id,
        kind=PROJECT,
        made_at=aware(analysis.now),
        inputs={"remaining": result["remaining"], "history_weeks": result["history_weeks"]},
        p50_date=pd.Timestamp(result["p50"]).date(),
        p85_date=pd.Timestamp(result["p85"]).date(),
    )
    db.add(entry)
    return entry


def _ticket_entry(project_id: str, subject_id: str, made_at: datetime, ref: dict) -> Forecast:
    return Forecast(
        project_id=project_id,
        kind=TICKET,
        subject_id=subject_id,
        made_at=aware(made_at),
        inputs={"n": ref["n"], "planned_days": (ref.get("plan") or {}).get("planned_days")},
        p10_days=ref["p10"],
        p50_days=ref["p50"],
        p85_days=ref["p85"],
        p90_days=ref["p90"],
    )


def record_ticket(db: Session, analysis: "Analysis", task) -> Forecast | None:
    """Store a reference-class forecast for a ticket that just started, once per ticket."""
    if analysis.reference_index is None:
        return None
    if db.scalar(select(Forecast.id).where(Forecast.kind == TICKET, Forecast.subject_id == task.id)):
        return None
    planned = None
    if task.due and task.created_at:
        planned = (task.due - naive_utc(task.created_at).date()).days
    ref = analysis.reference_index.query(task.title, task.description or "", planned, exclude_id=task.id)
    if not ref["available"]:
        return None
    entry = _ticket_entry(analysis.project_id, task.id, naive_utc(task.started_at) or analysis.now, ref)
    db.add(entry)
    return entry


# ---------- resolving ----------
def _resolve_entry(entry: Forecast, tickets_by_id: pd.DataFrame, done_times: np.ndarray, now: datetime) -> bool:
    made_at = naive_utc(entry.made_at)
    if entry.kind == PROJECT:
        n = int((entry.inputs or {}).get("remaining", 0))
        when = _nth_completion_after(done_times, made_at, n)
        if when is None:
            return False
        entry.actual_date = when.date()
        entry.hit_p85 = bool(entry.actual_date <= entry.p85_date)
    else:
        if entry.subject_id not in tickets_by_id.index:
            entry.void = True
            entry.hit_p85 = None
        else:
            row = tickets_by_id.loc[entry.subject_id]
            if not row["finished"]:
                return False
            entry.actual_days = round(float(row["cycle_days"]), 2)
            entry.hit_p85 = bool(entry.actual_days <= entry.p85_days)
    entry.resolved_at = aware(now)
    return True


def resolve(db: Session, analysis: "Analysis") -> int:
    """Score every unresolved forecast whose outcome is now known. Returns how many."""
    pending = db.scalars(
        select(Forecast).where(Forecast.project_id == analysis.project_id, Forecast.resolved_at.is_(None))
    ).all()
    if not pending:
        return 0
    by_id = analysis.tickets.set_index("id")
    done = _done_times(analysis.tickets)
    return sum(_resolve_entry(e, by_id, done, analysis.now) for e in pending)


# ---------- demo back-fill ----------
def backfill(db: Session, analysis: "Analysis", step_days: int = 7) -> int:
    """Replay history as if SlipCast had been running: forecast with only the data known
    at each past moment, then score against what really happened."""
    t = analysis.tickets
    if t.empty:
        return 0
    entries: list[Forecast] = []
    done = _done_times(t)

    # weekly project forecasts
    first = t["created_at"].min()
    moment = (first + timedelta(weeks=5)).normalize() + timedelta(hours=9)
    while moment < analysis.now - timedelta(days=1):
        known = t[t["created_at"] <= moment].copy()
        known["finished"] = known["finished"] & (known["completed_at"] <= moment)
        remaining = int((~known["finished"]).sum())
        history = np.array(flow.history_weeks(known, moment.to_pydatetime()))
        result = forecast.forecast(history, remaining, moment.date())["forecast"]
        if result["available"]:
            entries.append(
                Forecast(
                    project_id=analysis.project_id,
                    kind=PROJECT,
                    made_at=aware(moment.to_pydatetime()),
                    inputs={"remaining": remaining, "history_weeks": result["history_weeks"], "replayed": True},
                    p50_date=pd.Timestamp(result["p50"]).date(),
                    p85_date=pd.Timestamp(result["p85"]).date(),
                )
            )
        moment += timedelta(days=step_days)

    # a reference-class forecast at each ticket's start, using only tickets finished before it
    finished = t[t["finished"]].reset_index(drop=True)
    started = t[t["started_at"].notna()].reset_index(drop=True)
    if len(finished) >= MIN_FINISHED_FOR_TICKET and not started.empty:
        vec = reference_class.make_vectorizer()
        x_fin = vec.fit_transform(reference_class.ticket_text(finished["title"], finished["description"]))
        x_start = vec.transform(reference_class.ticket_text(started["title"], started["description"]))
        sims = (x_start @ x_fin.T).toarray()
        fin_done = finished["completed_at"].to_numpy(dtype="datetime64[ns]")
        cycle = finished["cycle_days"].to_numpy(dtype=float)
        late = finished["late"].to_numpy(dtype=float)
        for i, row in started.iterrows():
            visible = fin_done < np.datetime64(row["started_at"])
            if visible.sum() < MIN_FINISHED_FOR_TICKET:
                continue
            ref = reference_class.summarise(np.where(visible, sims[i], -1.0), cycle, late)
            if ref["available"]:
                ref["plan"] = {"planned_days": None if pd.isna(row["planned_days"]) else float(row["planned_days"])}
                entries.append(_ticket_entry(analysis.project_id, row["id"], row["started_at"].to_pydatetime(), ref))

    by_id = t.set_index("id")
    for e in entries:
        _resolve_entry(e, by_id, done, analysis.now)
    db.add_all(entries)
    return len(entries)


# ---------- summary ----------
def _rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def summary(db: Session, analysis: "Analysis", limit: int = 50) -> dict:
    rows = db.scalars(
        select(Forecast).where(Forecast.project_id == analysis.project_id).order_by(Forecast.made_at.desc())
    ).all()
    titles = dict(zip(analysis.tickets["id"], analysis.tickets["title"], strict=False))
    scored = [r for r in rows if r.resolved_at is not None and not r.void]
    projects = [r for r in scored if r.kind == PROJECT]
    tickets = [r for r in scored if r.kind == TICKET]

    calibration = []
    for q, attr in ((0.5, "p50_date"), (0.85, "p85_date")):
        if projects:
            calibration.append(
                {
                    "kind": PROJECT,
                    "predicted": q,
                    "observed": _rate([r.actual_date <= getattr(r, attr) for r in projects]),
                    "n": len(projects),
                }
            )
    for q, attr in ((0.1, "p10_days"), (0.5, "p50_days"), (0.85, "p85_days"), (0.9, "p90_days")):
        if tickets:
            calibration.append(
                {
                    "kind": TICKET,
                    "predicted": q,
                    "observed": _rate([r.actual_days <= getattr(r, attr) for r in tickets]),
                    "n": len(tickets),
                }
            )

    def entry(r: Forecast) -> dict:
        base = {
            "id": r.id,
            "kind": r.kind,
            "made_at": naive_utc(r.made_at).isoformat(),
            "resolved": r.resolved_at is not None,
            "void": r.void,
            "hit_p85": r.hit_p85,
        }
        if r.kind == PROJECT:
            base.update(
                subject=f"{(r.inputs or {}).get('remaining', '?')} open tickets",
                p50=r.p50_date.isoformat() if r.p50_date else None,
                p85=r.p85_date.isoformat() if r.p85_date else None,
                actual=r.actual_date.isoformat() if r.actual_date else None,
            )
        else:
            base.update(
                subject=titles.get(r.subject_id, "Deleted ticket"),
                subject_id=r.subject_id,
                p50=r.p50_days,
                p85=r.p85_days,
                band=[r.p10_days, r.p90_days],
                actual=r.actual_days,
            )
        return base

    return {
        "available": bool(scored),
        "reason": ""
        if scored
        else "No forecast has been scored yet. Entries are scored automatically when the "
        "work they predicted is finished.",
        "total": len(rows),
        "resolved": len(scored),
        "unresolved": sum(r.resolved_at is None for r in rows),
        "void": sum(r.void for r in rows),
        "hit_rate": _rate([bool(r.hit_p85) for r in scored]),
        "project": {"resolved": len(projects), "hit_rate_p85": _rate([bool(r.hit_p85) for r in projects])},
        "ticket": {
            "resolved": len(tickets),
            "hit_rate_p85": _rate([bool(r.hit_p85) for r in tickets]),
            "coverage_p10_p90": _rate([r.p10_days <= r.actual_days <= r.p90_days for r in tickets]),
        },
        "calibration": calibration,
        "entries": [entry(r) for r in rows[:limit]],
    }
