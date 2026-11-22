from datetime import date

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_project_for_user, require_membership
from app.models import BUILD_TYPES, ImportRecord, Project, Task, User
from app.schemas import InsightsOut, ProjectIn, ProjectOut, ProjectUpdate
from app.services import insights

router = APIRouter(tags=["projects"])

PALETTE = ["#7D96F2", "#52B5AA", "#F2B632", "#B58CF0", "#E66C63", "#5DB0E8"]


def _counts(db: Session, project_ids: list[str]) -> dict[str, tuple[int, int]]:
    if not project_ids:
        return {}
    rows = db.execute(
        select(
            Task.project_id,
            func.count(Task.id),
            func.sum(case((Task.status == "done", 1), else_=0)),
        )
        .where(Task.project_id.in_(project_ids), Task.item_type.notin_(BUILD_TYPES))
        .group_by(Task.project_id)
    ).all()
    return {pid: (total, int(done or 0)) for pid, total, done in rows}


def _out(project: Project, counts: dict[str, tuple[int, int]]) -> ProjectOut:
    total, done = counts.get(project.id, (0, 0))
    out = ProjectOut.model_validate(project)
    out.task_count, out.done_count = total, done
    return out


def next_color(db: Session, workspace_id: str) -> str:
    n = db.scalar(select(func.count(Project.id)).where(Project.workspace_id == workspace_id)) or 0
    return PALETTE[n % len(PALETTE)]


@router.get("/workspaces/{workspace_id}/projects", response_model=list[ProjectOut])
def list_projects(
    workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ProjectOut]:
    require_membership(db, user, workspace_id)
    projects = db.scalars(
        select(Project).where(Project.workspace_id == workspace_id).order_by(Project.created_at)
    ).all()
    counts = _counts(db, [p.id for p in projects])
    return [_out(p, counts) for p in projects]


@router.post(
    "/workspaces/{workspace_id}/projects",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    workspace_id: str,
    body: ProjectIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    require_membership(db, user, workspace_id, minimum="member")
    project = Project(
        workspace_id=workspace_id,
        name=body.name.strip(),
        goal=body.goal.strip(),
        color=body.color or next_color(db, workspace_id),
    )
    db.add(project)
    db.commit()
    return _out(project, {})


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProjectOut:
    project = get_project_for_user(db, user, project_id)
    return _out(project, _counts(db, [project.id]))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = get_project_for_user(db, user, project_id, minimum="member")
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(project, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    return _out(project, _counts(db, [project.id]))


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    project = get_project_for_user(db, user, project_id, minimum="admin")
    # Keep the import report but drop the link (explicit, so SQLite behaves like Postgres).
    db.execute(update(ImportRecord).where(ImportRecord.project_id == project.id).values(project_id=None))
    db.delete(project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/insights", response_model=InsightsOut)
def project_insights(
    project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> InsightsOut:
    """Rule-based health checks: overdue, blocked, unowned and overloaded work."""
    project = get_project_for_user(db, user, project_id)
    tasks = db.scalars(select(Task).where(Task.project_id == project.id, Task.item_type.notin_(BUILD_TYPES))).all()
    views = [insights.TaskView(t.id, t.title, t.owner, t.status, t.priority, t.due) for t in tasks]
    result = insights.analyse(views, date.today())
    return InsightsOut(
        project_id=project.id,
        health=result.health,
        completion=result.completion,
        open_count=result.open_count,
        insights=result.insights,
    )
