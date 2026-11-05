"""Loads a project's tickets and status events into pandas once and caches the results.

Every analytics endpoint goes through `get_analysis`. The cache key changes whenever a
ticket is added, edited or moved (ticket count, latest `updated_at`, event count) and at
midnight UTC (today's date), so results are never stale but repeated page loads and the
write-time ticket check reuse the same fitted models.
"""

import threading
from collections import OrderedDict
from datetime import date, datetime
from functools import cached_property

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Task, TaskEvent
from app.services import flow, forecast
from app.timeutil import naive_utc, now_utc

TICKET_COLUMNS = (
    "id",
    "title",
    "description",
    "owner",
    "status",
    "priority",
    "due",
    "kind",
    "kind_source",
    "created_at",
    "started_at",
    "completed_at",
    "updated_at",
)
_CACHE_SIZE = 32
_cache: OrderedDict[str, tuple[tuple, "Analysis"]] = OrderedDict()
_lock = threading.Lock()


def _to_datetime(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values.map(naive_utc), errors="coerce")


def build_frames(task_rows: list[tuple], event_rows: list[tuple]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Turn raw rows into the ticket and event frames every analysis works from."""
    t = pd.DataFrame(task_rows, columns=list(TICKET_COLUMNS))
    for col in ("created_at", "started_at", "completed_at", "updated_at"):
        t[col] = _to_datetime(t[col]) if len(t) else pd.Series(dtype="datetime64[ns]")
    t["due"] = pd.to_datetime(t["due"], errors="coerce")
    for col in ("title", "description", "owner", "kind_source"):
        t[col] = t[col].fillna("").astype(str)
    t["owner"] = t["owner"].str.strip()

    t["start"] = t["started_at"].fillna(t["created_at"])
    t["finished"] = (t["status"] == "done") & t["completed_at"].notna()
    cycle = (t["completed_at"] - t["start"]).dt.total_seconds() / 86400
    t["cycle_days"] = cycle.where(t["finished"]).clip(lower=0)
    has_due = t["finished"] & t["due"].notna()
    late = (t["completed_at"].dt.normalize() > t["due"]).astype(float)
    t["late"] = late.where(has_due)
    t["planned_days"] = (t["due"] - t["created_at"].dt.normalize()).dt.days

    e = pd.DataFrame(event_rows, columns=["task_id", "from_status", "to_status", "at"])
    e["at"] = _to_datetime(e["at"]) if len(e) else pd.Series(dtype="datetime64[ns]")
    # Tickets without recorded history (e.g. created before history existed) get a
    # synthetic one from their timestamps so flow charts still include them.
    missing = t[~t["id"].isin(set(e["task_id"]))]
    synthetic = []
    for row in missing.itertuples():
        if pd.notna(row.created_at):
            synthetic.append((row.id, None, "planned", row.created_at))
        if pd.notna(row.started_at):
            synthetic.append((row.id, "planned", "in_progress", row.started_at))
        if row.status == "done" and pd.notna(row.completed_at):
            synthetic.append((row.id, "in_progress", "done", row.completed_at))
        elif row.status == "blocked" and pd.notna(row.started_at):
            synthetic.append((row.id, "in_progress", "blocked", row.started_at))
    if synthetic:
        e = pd.concat([e, pd.DataFrame(synthetic, columns=e.columns)], ignore_index=True)
    e = e.dropna(subset=["at"]).sort_values("at", kind="stable").reset_index(drop=True)
    return t.reset_index(drop=True), e


class Analysis:
    """Everything computed for one project on one day. Expensive parts are lazy."""

    def __init__(self, project_id: str, tickets: pd.DataFrame, events: pd.DataFrame, now: datetime):
        self.project_id = project_id
        self.tickets = tickets
        self.events = events
        self.now = now
        self.today: date = now.date()
        self._forecasts: dict[date | None, dict] = {}

    # ---------- shared columns ----------
    @property
    def effective_kind(self) -> pd.Series:
        """Labelled type where known; otherwise 'unknown'. Phase 2C fills in predictions."""
        return self.tickets["kind"].where(self.tickets["kind"].notna(), "unknown")

    @property
    def themes(self) -> pd.Series | None:
        return None

    # ---------- flow and forecast ----------
    @cached_property
    def flow(self) -> dict:
        return flow.compute(self.tickets, self.events, self.now, self.effective_kind, self.themes)

    @cached_property
    def throughput_history(self) -> list[int]:
        return flow.history_weeks(self.tickets, self.now)

    def forecast(self, target: date | None = None) -> dict:
        if target not in self._forecasts:
            remaining = int((self.tickets["status"] != "done").sum())
            result = forecast.forecast(np.array(self.throughput_history), remaining, self.today, target)
            result["burnup"] = forecast.burnup(self.tickets, self.now, result)
            self._forecasts[target] = result
        return self._forecasts[target]

    def overview(self) -> dict:
        t = self.tickets
        f = self.flow
        fc = self.forecast()
        hist = self.throughput_history
        return {
            "tickets": len(t),
            "open": int((t["status"] != "done").sum()),
            "done": int(t["finished"].sum()),
            "cycle": {k: f["cycle_time"]["percentiles"].get(k) for k in ("p50", "p85")},
            "throughput_avg": round(float(np.mean(hist)), 1) if hist else None,
            "forecast_p85": fc["forecast"].get("p85") if fc["forecast"]["available"] else None,
            "high_risk": None,
        }


def _cache_key(db: Session, project_id: str, today: date) -> tuple:
    count, max_updated = db.execute(
        select(func.count(Task.id), func.max(Task.updated_at)).where(Task.project_id == project_id)
    ).one()
    events = db.scalar(
        select(func.count(TaskEvent.id)).join(Task, Task.id == TaskEvent.task_id).where(Task.project_id == project_id)
    )
    return (count, str(naive_utc(max_updated)), events, today)


def load(db: Session, project_id: str, now: datetime) -> Analysis:
    cols = [getattr(Task, c) for c in TICKET_COLUMNS]
    task_rows = [tuple(r) for r in db.execute(select(*cols).where(Task.project_id == project_id)).all()]
    event_rows = [
        tuple(r)
        for r in db.execute(
            select(TaskEvent.task_id, TaskEvent.from_status, TaskEvent.to_status, TaskEvent.at)
            .join(Task, Task.id == TaskEvent.task_id)
            .where(Task.project_id == project_id)
        ).all()
    ]
    tickets, events = build_frames(task_rows, event_rows)
    return Analysis(project_id, tickets, events, now)


def get_analysis(db: Session, project_id: str) -> Analysis:
    now = naive_utc(now_utc())
    key = _cache_key(db, project_id, now.date())
    with _lock:
        hit = _cache.get(project_id)
        if hit and hit[0] == key:
            _cache.move_to_end(project_id)
            return hit[1]
    analysis = load(db, project_id, now)
    with _lock:
        _cache[project_id] = (key, analysis)
        _cache.move_to_end(project_id)
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return analysis


def clear_cache() -> None:
    with _lock:
        _cache.clear()
