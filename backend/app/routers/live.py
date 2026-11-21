"""Real-time engine: project stages, API keys, event ingestion, live stream and alerts."""

import asyncio
import hashlib
import json
import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user, get_project_for_user, require_membership
from app.models import Alert, IngestedEvent, Project, ProjectApiKey, Task, TaskEvent, User
from app.routers.tasks import apply_status, notify
from app.schemas import Kind, Priority
from app.security import create_signed, read_signed
from app.services import alerts as alert_rules
from app.services import ledger
from app.services.analysis import get_analysis
from app.services.live import broker, limiter
from app.services.stages import stages_for, status_for
from app.timeutil import now_utc

router = APIRouter(tags=["live"])

KEY_PREFIX = "sck_"
STREAM_TOKEN_MINUTES = 2
MAX_BATCH = 500


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# ---------- stages ----------


@router.get("/projects/{project_id}/stages")
def list_stages(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """The project's stages and the engine category each one counts as."""
    project = get_project_for_user(db, user, project_id)
    return {"template": project.template, "stages": stages_for(db, project)}


# ---------- API keys ----------


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=60, pattern=r".*\S.*")


def _key_out(k: ProjectApiKey, key: str | None = None) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix,
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "key": key,  # only when the key is created; it can't be shown again
    }


@router.post("/projects/{project_id}/api-keys", status_code=status.HTTP_201_CREATED)
def create_key(
    project_id: str, body: KeyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    project = get_project_for_user(db, user, project_id, minimum="admin")
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    row = ProjectApiKey(
        project_id=project.id, name=body.name.strip(), prefix=key[:10], key_hash=_hash(key), created_by=user.id
    )
    db.add(row)
    db.commit()
    return _key_out(row, key)


@router.get("/projects/{project_id}/api-keys")
def list_keys(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    project = get_project_for_user(db, user, project_id, minimum="admin")
    rows = db.scalars(
        select(ProjectApiKey)
        .where(ProjectApiKey.project_id == project.id, ProjectApiKey.revoked_at.is_(None))
        .order_by(ProjectApiKey.created_at.desc())
    )
    return [_key_out(k) for k in rows]


@router.delete("/projects/{project_id}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(
    project_id: str, key_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    project = get_project_for_user(db, user, project_id, minimum="admin")
    row = db.scalar(select(ProjectApiKey).where(ProjectApiKey.id == key_id, ProjectApiKey.project_id == project.id))
    if row is None or row.revoked_at is not None:
        raise HTTPException(status_code=404, detail="Key not found")
    row.revoked_at = now_utc()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- event ingestion ----------


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


def _project_for_key(db: Session, project_id: str, key: str | None) -> tuple[Project, ProjectApiKey]:
    if not key:
        raise HTTPException(status_code=401, detail="Send the project's API key in the X-SlipCast-Key header")
    row = db.scalar(select(ProjectApiKey).where(ProjectApiKey.key_hash == _hash(key.strip())))
    # A key only ever works for its own project; any mismatch looks like a bad key.
    if row is None or row.revoked_at is not None or row.project_id != project_id:
        raise HTTPException(status_code=401, detail="This API key isn't valid for this project")
    return db.get(Project, project_id), row


def _when(value: datetime | None) -> datetime:
    now = now_utc()
    if value is None:
        return now.replace(microsecond=0)
    if value.tzinfo is None:  # no offset given: treat it as UTC
        value = value.replace(tzinfo=now.tzinfo)
    return value.astimezone(now.tzinfo).replace(microsecond=0)


def _snapshot(task: Task) -> tuple:
    return (
        task.status,
        task.stage,
        task.title,
        task.description,
        task.owner,
        task.due,
        task.priority,
        task.kind,
        task.item_type,
        repr(task.attributes),
    )


@router.post("/projects/{project_id}/events")
def ingest_events(
    project_id: str,
    body: EventBatch | EventIn,
    x_slipcast_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Stage changes from another system (an order system, a courier feed, a script).

    Send one event, or {"events": [...]} with up to 500. Sending the same event twice
    (same external_id, stage and occurred_at) changes nothing; an event that changes nothing
    about its item is counted as "unchanged" and doesn't refresh anyone's screen. An item that doesn't exist yet
    is created. An event older than the item's latest change is kept but doesn't move it back.
    """
    project, key = _project_for_key(db, project_id, x_slipcast_key)
    events = body.events if isinstance(body, EventBatch) else [body]
    settings = get_settings()
    if not limiter.allow(key.id, len(events), settings.events_per_minute):
        raise HTTPException(
            status_code=429,
            detail=f"Too many events: this key can send {settings.events_per_minute} a minute. Try again shortly.",
            headers={"Retry-After": "60"},
        )

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
        at = _when(ev.occurred_at)
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
        if latest is not None and at < _when(latest):
            stale += 1  # out of order: remembered, but doesn't move the item backwards
        else:
            old = task.status
            apply_status(task, new_status, db, at=at, stage=None if ev.stage == new_status else ev.stage)
            if new_status == "in_progress" and old in (None, "planned"):
                started.append(task)
        db.flush()
        if is_new:
            created.append(task.id)
        elif _snapshot(task) == before:
            unchanged += 1  # e.g. the same stage sent again without occurred_at: nothing to tell anyone
        else:
            updated.append(task.id)

    key.last_used_at = now
    db.commit()

    changed = list(dict.fromkeys(created + updated))
    if changed:
        notify(project.id, changed, source="events")  # screens refresh now; alerts follow
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


# ---------- live stream ----------


@router.post("/projects/{project_id}/stream-token")
def stream_token(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Browsers can't send headers on a live stream, so they get a short-lived, single-purpose token."""
    project = get_project_for_user(db, user, project_id)
    token = create_signed(
        {"purpose": "stream", "project": project.id, "sub": user.id, "ver": user.token_version}, STREAM_TOKEN_MINUTES
    )
    return {"token": token, "expires_in": STREAM_TOKEN_MINUTES * 60}


@router.get("/projects/{project_id}/stream")
async def stream(project_id: str, request: Request, token: str = "", db: Session = Depends(get_db)):
    """Server-Sent Events: `change` when items change, `alert` for new alerts, comments as keep-alives."""
    claims = read_signed(token, "stream")
    user = db.get(User, claims["sub"]) if claims and claims.get("project") == project_id else None
    if user is None or claims.get("ver") != user.token_version:
        raise HTTPException(status_code=401, detail="This live link has expired; the page will reconnect")
    get_project_for_user(db, user, project_id)  # still a member?
    db.close()  # a stream can stay open for minutes; don't hold a database connection

    max_seconds = get_settings().stream_max_seconds
    queue = broker.subscribe(project_id)

    async def events():
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_seconds
        try:
            yield "retry: 3000\nevent: ready\ndata: {}\n\n"
            while (remaining := deadline - loop.time()) > 0:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=min(15.0, remaining))
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {msg['type']}\ndata: {json.dumps(msg)}\n\n"
        finally:
            broker.unsubscribe(project_id, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- alerts ----------


@router.get("/projects/{project_id}/alerts")
def project_alerts(
    project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    project = get_project_for_user(db, user, project_id)
    rows = db.scalars(select(Alert).where(Alert.project_id == project.id).order_by(Alert.created_at.desc()).limit(30))
    return [alert_rules.to_dict(a, project.name) for a in rows]


@router.get("/workspaces/{workspace_id}/alerts")
def workspace_alerts(
    workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    """The latest alerts across every project in the workspace, for the bell menu."""
    require_membership(db, user, workspace_id)
    rows = db.execute(
        select(Alert, Project.name)
        .join(Project, Project.id == Alert.project_id)
        .where(Project.workspace_id == workspace_id)
        .order_by(Alert.created_at.desc())
        .limit(30)
    ).all()
    return [alert_rules.to_dict(a, name) for a, name in rows]
