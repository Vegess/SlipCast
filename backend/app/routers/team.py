"""Workspace members, roles and invite links."""

import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user, require_membership
from app.models import Invite, Membership, User, Workspace
from app.schemas import InviteOut, InvitePreview, MemberOut, RoleIn, WorkspaceOut
from app.timeutil import now_utc

router = APIRouter(tags=["team"])


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt):
    """SQLite hands back naive datetimes; treat them as the UTC they were stored as."""
    return dt if dt.tzinfo else dt.replace(tzinfo=now_utc().tzinfo)


def _admin_count(db: Session, workspace_id: str) -> int:
    return (
        db.scalar(
            select(func.count(Membership.id)).where(Membership.workspace_id == workspace_id, Membership.role == "admin")
        )
        or 0
    )


def _member(db: Session, workspace_id: str, user_id: str) -> Membership:
    m = db.scalar(select(Membership).where(Membership.workspace_id == workspace_id, Membership.user_id == user_id))
    if m is None:
        raise HTTPException(status_code=404, detail="That person isn't in this workspace")
    return m


@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberOut])
def list_members(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_membership(db, user, workspace_id)
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == workspace_id)
    ).all()
    order = {"admin": 0, "member": 1, "viewer": 2}
    rows = sorted(rows, key=lambda r: (order.get(r[0].role, 3), r[1].name.lower()))
    return [MemberOut(user_id=u.id, name=u.name, email=u.email, role=m.role, is_you=u.id == user.id) for m, u in rows]


@router.patch("/workspaces/{workspace_id}/members/{user_id}", response_model=MemberOut)
def change_role(
    workspace_id: str, user_id: str, body: RoleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    require_membership(db, user, workspace_id, minimum="admin")
    m = _member(db, workspace_id, user_id)
    if m.role == "admin" and body.role != "admin" and _admin_count(db, workspace_id) == 1:
        raise HTTPException(
            status_code=400, detail="A workspace needs at least one admin. Make someone else admin first."
        )
    m.role = body.role
    db.commit()
    target = db.get(User, user_id)
    return MemberOut(user_id=target.id, name=target.name, email=target.email, role=m.role, is_you=target.id == user.id)


@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    workspace_id: str, user_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Admins can remove anyone; anyone can remove themselves (leave)."""
    require_membership(db, user, workspace_id, minimum="viewer" if user_id == user.id else "admin")
    m = _member(db, workspace_id, user_id)
    if m.role == "admin" and _admin_count(db, workspace_id) == 1:
        raise HTTPException(
            status_code=400, detail="A workspace needs at least one admin. Make someone else admin first."
        )
    db.delete(m)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/workspaces/{workspace_id}/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_invite(
    workspace_id: str, body: RoleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    require_membership(db, user, workspace_id, minimum="admin")
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    invite = Invite(
        workspace_id=workspace_id,
        token_hash=_hash(token),
        role=body.role,
        created_by=user.id,
        expires_at=now_utc() + timedelta(days=settings.invite_days),
    )
    db.add(invite)
    db.commit()
    out = InviteOut.model_validate(invite, from_attributes=True)
    out.url = f"{settings.public_web_url.rstrip('/')}/invite/{token}"  # shown once; only the hash is kept
    return out


@router.get("/workspaces/{workspace_id}/invites", response_model=list[InviteOut])
def list_invites(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Invite links that are still usable. Their URLs can't be shown again; make a new one if lost."""
    require_membership(db, user, workspace_id, minimum="admin")
    now = now_utc()
    rows = db.scalars(
        select(Invite)
        .where(Invite.workspace_id == workspace_id, Invite.used_at.is_(None))
        .order_by(Invite.created_at.desc())
    ).all()
    return [InviteOut.model_validate(i, from_attributes=True) for i in rows if _aware(i.expires_at) > now]


@router.delete("/workspaces/{workspace_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(
    workspace_id: str, invite_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    require_membership(db, user, workspace_id, minimum="admin")
    invite = db.scalar(select(Invite).where(Invite.id == invite_id, Invite.workspace_id == workspace_id))
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    db.delete(invite)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _find_invite(db: Session, token: str) -> tuple[Invite, str]:
    """Returns the invite and, if it can't be used, the reason."""
    invite = db.scalar(select(Invite).where(Invite.token_hash == _hash(token)))
    if invite is None:
        raise HTTPException(status_code=404, detail="This invite link isn't valid. Ask for a new one.")
    if invite.used_at is not None:
        return invite, "This invite link has already been used. Ask for a new one."
    if _aware(invite.expires_at) <= now_utc():
        return invite, "This invite link has expired. Ask for a new one."
    return invite, ""


@router.get("/invites/{token}", response_model=InvitePreview)
def preview_invite(token: str, db: Session = Depends(get_db)):
    """Public: what the invite is for, so the page can say so before sign-in."""
    invite, reason = _find_invite(db, token)
    inviter = db.get(User, invite.created_by) if invite.created_by else None
    return InvitePreview(
        workspace_name=invite.workspace.name,
        role=invite.role,
        invited_by=inviter.name if inviter else "A workspace admin",
        valid=not reason,
        reason=reason,
    )


@router.post("/invites/{token}/accept", response_model=WorkspaceOut)
def accept_invite(token: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invite, reason = _find_invite(db, token)
    if reason:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=reason)
    workspace: Workspace = invite.workspace
    existing = db.scalar(
        select(Membership).where(Membership.workspace_id == workspace.id, Membership.user_id == user.id)
    )
    if existing is not None:  # already in: don't use up the link, don't change their role
        return WorkspaceOut(id=workspace.id, name=workspace.name, role=existing.role)
    db.add(Membership(user_id=user.id, workspace_id=workspace.id, role=invite.role))
    invite.used_at = now_utc()
    invite.used_by = user.id
    db.commit()
    return WorkspaceOut(id=workspace.id, name=workspace.name, role=invite.role)
