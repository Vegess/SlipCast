from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ImportRecord, Membership, Project, Task, User
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in to continue",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    decoded = decode_access_token(creds.credentials)
    user = db.get(User, decoded[0]) if decoded else None
    # A token from before "sign out everywhere" or a password change no longer works.
    if user is None or decoded[1] != user.token_version:
        raise unauthorized
    return user


# Tenant isolation: every lookup below joins through Membership, so a user can only
# ever reach rows in workspaces they belong to. Missing access returns 404, not 403,
# so the API never confirms that another tenant's resource exists.
#
# Roles: once membership is established, `minimum` says what the action needs.
#   viewer  reads everything, changes nothing (403 on any write)
#   member  creates and edits projects, tickets and imports
#   admin   also deletes projects and manages the team and invite links
# Routers pass `minimum`; they never compare role strings themselves.

ROLE_RANK = {"viewer": 0, "member": 1, "admin": 2}
FORBIDDEN = {
    "member": "You have view-only access to this workspace. Ask an admin to make you a member.",
    "admin": "Only workspace admins can do that.",
}


def _check_role(role: str, minimum: str) -> None:
    if ROLE_RANK.get(role, -1) < ROLE_RANK[minimum]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN[minimum])


def require_membership(db: Session, user: User, workspace_id: str, minimum: str = "viewer") -> Membership:
    membership = db.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == workspace_id)
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    _check_role(membership.role, minimum)
    return membership


def get_project_for_user(db: Session, user: User, project_id: str, minimum: str = "viewer") -> Project:
    row = db.execute(
        select(Project, Membership.role)
        .join(Membership, Membership.workspace_id == Project.workspace_id)
        .where(Project.id == project_id, Membership.user_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _check_role(row[1], minimum)
    return row[0]


def get_task_for_user(db: Session, user: User, task_id: str, minimum: str = "viewer") -> Task:
    row = db.execute(
        select(Task, Membership.role)
        .join(Project, Project.id == Task.project_id)
        .join(Membership, Membership.workspace_id == Project.workspace_id)
        .where(Task.id == task_id, Membership.user_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _check_role(row[1], minimum)
    return row[0]


def get_import_for_user(db: Session, user: User, import_id: str) -> ImportRecord:
    record = db.scalar(
        select(ImportRecord)
        .join(Membership, Membership.workspace_id == ImportRecord.workspace_id)
        .where(ImportRecord.id == import_id, Membership.user_id == user.id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return record
