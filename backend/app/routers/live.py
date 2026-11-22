"""Real-time engine: project stages, API keys, event ingestion, live stream and alerts."""

import asyncio
import hashlib
import json
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user, get_project_for_user, require_membership
from app.models import Alert, Project, ProjectApiKey, User
from app.security import create_signed, read_signed
from app.services import alerts as alert_rules
from app.services import control_room
from app.services.ingest import EventBatch, EventIn, apply_events
from app.services.live import broker, limiter
from app.services.stages import stages_for
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


def _project_for_key(db: Session, project_id: str, key: str | None) -> tuple[Project, ProjectApiKey]:
    if not key:
        raise HTTPException(status_code=401, detail="Send the project's API key in the X-SlipCast-Key header")
    row = db.scalar(select(ProjectApiKey).where(ProjectApiKey.key_hash == _hash(key.strip())))
    # A key only ever works for its own project; any mismatch looks like a bad key.
    if row is None or row.revoked_at is not None or row.project_id != project_id:
        raise HTTPException(status_code=401, detail="This API key isn't valid for this project")
    return db.get(Project, project_id), row


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

    key.last_used_at = now_utc()
    return apply_events(db, project, events, source="events")


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


@router.post("/workspaces/{workspace_id}/stream-token")
def workspace_stream_token(
    workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """A live link for the Control Room: hears every project in the workspace."""
    require_membership(db, user, workspace_id)
    claims = {"purpose": "workspace-stream", "workspace": workspace_id, "sub": user.id, "ver": user.token_version}
    return {"token": create_signed(claims, STREAM_TOKEN_MINUTES), "expires_in": STREAM_TOKEN_MINUTES * 60}


@router.get("/workspaces/{workspace_id}/stream")
async def workspace_stream(workspace_id: str, request: Request, token: str = "", db: Session = Depends(get_db)):
    """Server-Sent Events from every project in the workspace; each message names its project.
    Projects created after connecting are heard after the next reconnect (every few minutes)."""
    claims = read_signed(token, "workspace-stream")
    user = db.get(User, claims["sub"]) if claims and claims.get("workspace") == workspace_id else None
    if user is None or claims.get("ver") != user.token_version:
        raise HTTPException(status_code=401, detail="This live link has expired; the page will reconnect")
    require_membership(db, user, workspace_id)
    project_ids = list(db.scalars(select(Project.id).where(Project.workspace_id == workspace_id)))
    db.close()

    max_seconds = get_settings().stream_max_seconds
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    for pid in project_ids:
        broker.subscribe(pid, queue)

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
            for pid in project_ids:
                broker.unsubscribe(pid, queue)

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
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


# ---------- control room ----------


@router.get("/workspaces/{workspace_id}/control-room")
def control_room_view(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Every promise due in the next 7 days across the workspace, riskiest first, with each module's
    track record and the latest activity."""
    require_membership(db, user, workspace_id)
    return control_room.compute(db, workspace_id, now_utc())
