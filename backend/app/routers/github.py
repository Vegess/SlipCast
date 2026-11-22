"""Connect a project to a GitHub repository's webhook, and receive its deliveries."""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import ROLE_RANK, get_current_user, get_project_for_user, require_membership
from app.models import Project, Task, User
from app.services import github
from app.services.ingest import apply_events
from app.services.live import limiter
from app.timeutil import now_utc

router = APIRouter(tags=["github"])


def _api_base(request: Request) -> str:
    base = get_settings().public_api_url.rstrip("/")
    if base:
        return base
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def _status(project: Project, request: Request, show_secret: bool) -> dict:
    return {
        "connected": project.github_hook_version is not None,
        "repo": project.github_repo,
        "last_event_at": project.github_last_event_at.isoformat() if project.github_last_event_at else None,
        "webhook_url": f"{_api_base(request)}/api/projects/{project.id}/github/webhook",
        "secret": github.secret_for(project) if show_secret else None,
        "events": list(github.EVENTS),
    }


@router.get("/projects/{project_id}/github")
def github_status(
    project_id: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Whether GitHub is connected. Only admins see the secret."""
    project = get_project_for_user(db, user, project_id)
    role = require_membership(db, user, project.workspace_id).role
    return _status(project, request, show_secret=ROLE_RANK.get(role, 0) >= ROLE_RANK["admin"])


@router.post("/projects/{project_id}/github")
def connect_github(
    project_id: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Turns the webhook on, or rotates its secret (the old secret stops working at once)."""
    project = get_project_for_user(db, user, project_id, minimum="admin")
    project.github_hook_version = (project.github_hook_version or 0) + 1
    db.commit()
    return _status(project, request, show_secret=True)


@router.delete("/projects/{project_id}/github", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_github(
    project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    project = get_project_for_user(db, user, project_id, minimum="admin")
    project.github_hook_version = None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{project_id}/github/webhook")
async def github_webhook(
    project_id: str,
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Where GitHub sends deliveries. Every one must carry a valid signature for this project."""
    body = await request.body()
    project = db.get(Project, project_id)
    secret = github.secret_for(project) if project else None
    if secret is None or not github.verify(secret, body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Signature doesn't match this project's webhook secret")
    if not limiter.allow(f"github:{project_id}", 1, get_settings().events_per_minute):
        raise HTTPException(
            status_code=429, detail="Too many deliveries; GitHub will retry", headers={"Retry-After": "60"}
        )
    try:
        payload = json.loads(body or b"{}")
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Body isn't JSON; set the content type to application/json"
        ) from exc

    repo = (payload.get("repository") or {}).get("full_name")
    if repo:
        project.github_repo = str(repo)[:140]
    project.github_last_event_at = now_utc()
    if x_github_event == "ping":
        db.commit()
        return {
            "ok": True,
            "message": "Connected. SlipCast will track pull requests, reviews, releases and deployments.",
        }

    tags = None
    if x_github_event == "deployment_status":
        rows = db.scalars(select(Task.attributes).where(Task.project_id == project.id, Task.item_type == "release"))
        tags = {str(a.get("tag")) for a in rows if a and a.get("tag")}
    events = github.to_events(x_github_event, payload, tags)
    if not events:
        db.commit()
        return {
            "ok": True,
            "ignored": f"'{x_github_event}' {payload.get('action') or ''} isn't something SlipCast tracks".strip(),
        }
    result = apply_events(db, project, events, source="github")
    return {"ok": True, **result}
