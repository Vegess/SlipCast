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
    user_id = decode_access_token(creds.credentials)
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise unauthorized
    return user


# Tenant isolation: every lookup below joins through Membership, so a user can only
# ever reach rows in workspaces they belong to. Missing access returns 404, not 403,
# so the API never confirms that another tenant's resource exists.


def require_membership(db: Session, user: User, workspace_id: str) -> Membership:
    membership = db.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == workspace_id)
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return membership


def get_project_for_user(db: Session, user: User, project_id: str) -> Project:
    project = db.scalar(
        select(Project)
        .join(Membership, Membership.workspace_id == Project.workspace_id)
        .where(Project.id == project_id, Membership.user_id == user.id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def get_task_for_user(db: Session, user: User, task_id: str) -> Task:
    task = db.scalar(
        select(Task)
        .join(Project, Project.id == Task.project_id)
        .join(Membership, Membership.workspace_id == Project.workspace_id)
        .where(Task.id == task_id, Membership.user_id == user.id)
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def get_import_for_user(db: Session, user: User, import_id: str) -> ImportRecord:
    record = db.scalar(
        select(ImportRecord)
        .join(Membership, Membership.workspace_id == ImportRecord.workspace_id)
        .where(ImportRecord.id == import_id, Membership.user_id == user.id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return record
