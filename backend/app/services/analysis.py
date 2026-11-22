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

from app.models import BUILD_TYPES, Task, TaskEvent
from app.services import flow, forecast, ledger, nlp, reference_class, risk_model
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
    @cached_property
    def classifier(self) -> dict:
        return nlp.train_classifier(self.tickets)

    @cached_property
    def effective_kind(self) -> pd.Series:
        """Labelled type where a person set one, else the classifier's prediction, else 'unknown'."""
        kind = self.tickets["kind"].where(self.tickets["kind_source"] == "label")
        predicted = self.classifier["predictions"]
        if len(predicted):
            kind = kind.fillna(predicted)
        return kind.fillna("unknown")

    @cached_property
    def theme_result(self) -> dict:
        return nlp.find_themes(self.tickets)

    @property
    def themes(self) -> pd.Series | None:
        return self.theme_result["labels"] if self.theme_result["available"] else None

    @cached_property
    def quality(self) -> pd.Series:
        return nlp.quality_column(self.tickets)

    @cached_property
    def risk(self) -> risk_model.RiskModel:
        return risk_model.RiskModel(self.tickets, self.effective_kind, self.quality)

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

    # ---------- text ----------
    @cached_property
    def reference_index(self) -> reference_class.ReferenceIndex | None:
        return reference_class.ReferenceIndex.build(self.tickets)

    @cached_property
    def text_index(self) -> nlp.TextIndex | None:
        return nlp.TextIndex.build(self.tickets)

    def reference(
        self, title: str, description: str, planned_days: float | None = None, exclude_id: str | None = None
    ) -> dict:
        if self.reference_index is None:
            return reference_class.unavailable(
                "No finished tickets with text yet, so there is nothing to compare with."
            )
        return self.reference_index.query(title, description, planned_days, exclude_id)

    def reference_for_task(self, task_id: str) -> dict:
        row = self.tickets.loc[self.tickets["id"] == task_id].iloc[0]
        planned = None if pd.isna(row["planned_days"]) else float(row["planned_days"])
        out = self.reference(row["title"], row["description"], planned, exclude_id=task_id)
        if row["finished"]:
            out["actual_days"] = round(float(row["cycle_days"]), 1)
        return out

    def ticket_check(
        self,
        title: str,
        description: str,
        owner: str = "",
        due: date | None = None,
        priority: str = "medium",
        kind: str | None = None,
        exclude_id: str | None = None,
    ) -> dict:
        """Write-time check for a draft ticket: quality, reference class, slip risk, duplicates."""
        score, reasons = nlp.quality(title, description, owner, due)
        planned = (due - self.today).days if due else None
        slip_risk = None
        if due is not None and (title.strip() or description.strip()):
            draft_kind = kind
            if draft_kind is None and self.classifier["available"]:
                draft_kind = str(self.classifier["model"].predict([reference_class.ticket_text(title, description)])[0])
            slip_risk = self.risk.score_draft(title, description, owner, planned, priority, draft_kind or "unknown")
        duplicates = (
            self.text_index.similar_to(title, description, exclude_id=exclude_id)
            if self.text_index is not None and (title.strip() or description.strip())
            else []
        )
        return {
            "quality": {"score": score, "reasons": reasons},
            "reference": self.reference(title, description, planned, exclude_id),
            "slip_risk": slip_risk,
            "duplicates": duplicates,
        }

    # ---------- models ----------
    def text_insights(self) -> dict:
        t = self.tickets
        th = self.theme_result
        topics = {"available": th["available"], "reason": th.get("reason", ""), "silhouette": th["silhouette"]}
        topics["items"] = []
        if th["available"]:
            for name, g in t.groupby(th["labels"].values, sort=False):
                if name == "Other":
                    continue
                cycles = g.loc[g["finished"], "cycle_days"]
                topics["items"].append(
                    {
                        "name": name,
                        "size": int(len(g)),
                        "keywords": th["keywords"][name],
                        "open": int((g["status"] != "done").sum()),
                        "median_cycle_days": round(float(cycles.median()), 1) if len(cycles) else None,
                        "late_rate": round(float(g["late"].mean()), 3) if g["late"].notna().any() else None,
                        "kinds": self.effective_kind.loc[g.index].value_counts().to_dict(),
                    }
                )
            topics["items"].sort(key=lambda d: -d["size"])
        open_t = t[t["status"] != "done"]
        lowest = []
        for r in open_t.assign(q=self.quality.loc[open_t.index]).sort_values("q").head(10).itertuples():
            score, reasons = nlp.quality(r.title, r.description, r.owner, r.due)
            lowest.append({"id": r.id, "title": r.title, "score": score, "reasons": reasons})
        return {
            "topics": topics,
            "duplicates": nlp.duplicate_pairs(self.text_index),
            "quality": {
                "average_open": round(float(self.quality.loc[open_t.index].mean()), 1) if len(open_t) else None,
                "lowest": lowest,
            },
            "types": {
                "counts": self.effective_kind.value_counts().to_dict(),
                "predicted": self.classifier["predicted_unlabeled"],
                "classifier_available": self.classifier["available"],
                "reason": self.classifier.get("reason", ""),
            },
        }

    @cached_property
    def evaluation(self) -> dict:
        clf = {k: v for k, v in self.classifier.items() if k not in ("predictions", "model")}
        th = self.theme_result
        return {
            "classifier": clf,
            "topics": {"available": th["available"], "silhouette": th["silhouette"], "count": th["count"]},
            "risk": self.risk.evaluation(),
            "forecast_backtest": forecast.backtest(self.tickets, self.now),
            "reference_class": reference_class.evaluate(self.tickets),
        }

    def task_analysis(self, task_id: str) -> dict:
        """Everything SlipCast knows about one ticket."""
        idx = self.tickets.index[self.tickets["id"] == task_id][0]
        r = self.tickets.loc[idx]
        score, reasons = nlp.quality(r["title"], r["description"], r["owner"], r["due"])
        risk = None
        if self.risk.available and r["status"] != "done" and pd.notna(r["due"]):
            prob = float(self.risk.model.predict_proba(self.risk.x.loc[[idx]])[0, 1])
            risk = {
                "risk": round(prob, 3),
                "factors": risk_model.explain(self.risk.model, self.risk.x.loc[idx], r["owner"]),
            }
        themes = self.themes
        return {
            "id": task_id,
            "kind": self.effective_kind.loc[idx],
            "kind_source": "label" if r["kind_source"] == "label" else "predicted",
            "theme": themes.loc[idx] if themes is not None else None,
            "quality": {"score": score, "reasons": reasons},
            "slip_risk": risk,
            "reference": self.reference_for_task(task_id),
            "duplicates": self.text_index.similar_to(r["title"], r["description"], exclude_id=task_id)
            if self.text_index is not None
            else [],
        }

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
            "high_risk": sum(i["risk"] >= risk_model.HIGH_RISK for i in self.risk.open_risks()["items"])
            if self.risk.available
            else None,
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
    tickets_only = (Task.project_id == project_id) & Task.item_type.notin_(BUILD_TYPES)
    task_rows = [tuple(r) for r in db.execute(select(*cols).where(tickets_only)).all()]
    event_rows = [
        tuple(r)
        for r in db.execute(
            select(TaskEvent.task_id, TaskEvent.from_status, TaskEvent.to_status, TaskEvent.at)
            .join(Task, Task.id == TaskEvent.task_id)
            .where(tickets_only)
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
    if ledger.resolve(db, analysis):
        db.commit()
    with _lock:
        _cache[project_id] = (key, analysis)
        _cache.move_to_end(project_id)
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return analysis


def clear_cache() -> None:
    with _lock:
        _cache.clear()
