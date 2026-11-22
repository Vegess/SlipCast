"""Applies stage-change events to a project's items. Shared by the event API and the GitHub webhook."""

from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BUILD_TYPES, IngestedEvent, Project, Task, TaskEvent
from app.schemas import Kind, Priority
from app.services import alerts as alert_rules
from app.services import ledger
from app.services.analysis import get_analysis
from app.services.live import broker
from app.services.stages import stages_for, status_for
from app.timeutil import now_utc

MAX_BATCH = 500


class EventIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=64, description="Your id for the item, e.g. an order number")
    stage: str = Field(min_length=1, max_length=40, description="One of the project's stage keys")
    occurred_at: datetime | None = Field(default=None, description="When it happened; defaults to now")
    title: str | None = Field(default=None, max_length=140)
    description: str | None = Field(default=None, max_length=10_000)
    owner: str | None = Field(default=None, max_length=40)
    due: date | None = None
    priority: Priority | None = None
    kind: Kind | None = None
    item_type: str | None = Field(default=None, max_length=20)
    attributes: dict | None = None


class EventBatch(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=MAX_BATCH)


def when(value: datetime | None) -> datetime:
    """An event time as aware UTC, to the second. No offset given means UTC; none at all means now."""
    now = now_utc()
    if value is None:
        return now.replace(microsecond=0)
    if value.tzinfo is None:
        value = value.replace(tzinfo=now.tzinfo)
    return value.astimezone(now.tzinfo).replace(microsecond=0)


def _snapshot(task: Task) -> tuple:
    return (
        task.status, task.stage, task.title, task.description, task.owner, task.due,
        task.priority, task.kind, task.item_type, repr(task.attributes),
    )  # fmt: skip


def apply_events(db: Session, project: Project, events: list[EventIn], source: str = "events") -> dict:
    """Creates or moves items, records each event once, then notifies screens and checks alerts.

    The same event twice (external_id, stage, occurred_at) changes nothing; an event that
    changes nothing about its item counts as unchanged; an event older than the item's latest
    change is kept in the history but doesn't move the item backwards.
    """
    from app.routers.tasks import apply_status, notify  # the router owns the status rules

    stages = stages_for(db, project)
    alert_rules.baseline(db, project)  # first time only: the forecast before this change
    now = now_utc()
    created, updated, duplicates, stale, unchanged = [], [], 0, 0, 0
    errors: list[dict] = []
    seen: set[tuple] = set()
    started: list[Task] = []
    last = db.scalar(select(func.max(Task.position)).where(Task.project_id == project.id))
    next_position = (last + 1) if last is not None else 0

    for i, ev in enumerate(events):
        new_status = status_for(stages, ev.stage)
        if new_status is None:
            keys = ", ".join(s["key"] for s in stages)
            errors.append(
                {"index": i, "external_id": ev.external_id, "error": f"Unknown stage '{ev.stage}'. Use one of: {keys}"}
            )
            continue
        at = when(ev.occurred_at)
        if at > now + timedelta(minutes=5):
            errors.append({"index": i, "external_id": ev.external_id, "error": "occurred_at is in the future"})
            continue
        ident = (ev.external_id, ev.stage, at)
        exists = ident in seen or db.scalar(
            select(IngestedEvent.id).where(
                IngestedEvent.project_id == project.id,
                IngestedEvent.external_id == ev.external_id,
                IngestedEvent.stage == ev.stage,
                IngestedEvent.occurred_at == at,
            )
        )
        if exists:
            duplicates += 1
            continue
        seen.add(ident)
        db.add(IngestedEvent(project_id=project.id, external_id=ev.external_id, stage=ev.stage, occurred_at=at))

        task = db.scalar(select(Task).where(Task.project_id == project.id, Task.external_id == ev.external_id))
        is_new = task is None
        before = None if is_new else _snapshot(task)
        if is_new:
            task = Task(
                project_id=project.id,
                external_id=ev.external_id,
                title=(ev.title or ev.external_id).strip()[:140],
                position=next_position,
                status=None,
                created_at=at,
            )
            next_position += 1
            db.add(task)
        for field in ("title", "description", "owner", "due", "priority", "item_type"):
            value = getattr(ev, field)
            if value is not None:
                setattr(task, field, value.strip() if isinstance(value, str) else value)
        if ev.kind is not None:
            task.kind, task.kind_source = ev.kind, "label"
        if ev.attributes:
            task.attributes = {**(task.attributes or {}), **ev.attributes}

        latest = None if is_new else db.scalar(select(func.max(TaskEvent.at)).where(TaskEvent.task_id == task.id))
        if latest is not None and at < when(latest):
            stale += 1
        else:
            old = task.status
            apply_status(task, new_status, db, at=at, stage=None if ev.stage == new_status else ev.stage)
            if new_status == "in_progress" and old in (None, "planned") and task.item_type not in BUILD_TYPES:
                started.append(task)
        db.flush()
        if is_new:
            created.append(task.id)
        elif _snapshot(task) == before:
            unchanged += 1
        else:
            updated.append(task.id)
    db.commit()

    changed = list(dict.fromkeys(created + updated))
    if changed:
        notify(project.id, changed, source=source)  # screens refresh now; alerts follow
        analysis = get_analysis(db, project.id)
        if any(ledger.record_ticket(db, analysis, t) for t in started):
            db.commit()
        raised = alert_rules.check(db, project, created)
        db.commit()
        for a in raised:
            broker.publish(project.id, {"type": "alert", "alert": alert_rules.to_dict(a, project.name)})

    return {
        "accepted": len(events) - duplicates - len(errors),
        "created": len(set(created)),
        "updated": len(set(updated) - set(created)),
        "unchanged": unchanged,
        "duplicates": duplicates,
        "out_of_order": stale,
        "errors": errors,
    }
