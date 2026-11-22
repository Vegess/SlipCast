from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_project_for_user, get_task_for_user
from app.models import BUILD_TYPES, Task, TaskEvent, User
from app.schemas import TaskIn, TaskOut, TaskUpdate
from app.services import ledger
from app.services.analysis import get_analysis
from app.services.live import broker
from app.services.stages import stages_for, status_for
from app.timeutil import now_utc

router = APIRouter(tags=["tasks"])


def record_start(task: Task, old_status: str | None, db: Session) -> None:
    """When a ticket starts, store its reference-class forecast in the ledger (once)."""
    if task.status == "in_progress" and old_status in (None, "planned"):
        if ledger.record_ticket(db, get_analysis(db, task.project_id), task):
            db.commit()


def apply_status(task: Task, new_status: str, db: Session, at=None, stage: str | None = None) -> None:
    """Record the transition and keep started/completed timestamps consistent.
    `at` is when it really happened (events from other systems); `stage` is the project's own stage."""
    old = task.status if task.id and task.status else None
    task.stage = stage
    if old == new_status:
        return
    now = at or now_utc()
    task.status = new_status
    if new_status in ("in_progress", "blocked", "done") and task.started_at is None:
        task.started_at = now
    if new_status == "done":
        task.completed_at = now
    elif old == "done":
        task.completed_at = None  # reopened
    db.add(TaskEvent(task=task, from_status=old, to_status=new_status, at=now))


def _stage_status(db: Session, project, stage: str) -> str:
    status_ = status_for(stages_for(db, project), stage)
    if status_ is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"This project has no stage called '{stage}'.")
    return status_


def notify(project_id: str, task_ids: list[str], deleted: bool = False, source: str = "app") -> None:
    """Tell open screens for this project to refresh (a no-op when nobody is watching)."""
    broker.publish(project_id, {"type": "change", "source": source, "task_ids": task_ids, "deleted": deleted})


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
def list_tasks(
    project_id: str,
    types: Literal["tickets", "all"] = "tickets",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Task]:
    """Tickets by default; `types=all` adds the pull requests, releases and deployments from GitHub."""
    project = get_project_for_user(db, user, project_id)
    query = select(Task).where(Task.project_id == project.id)
    if types == "tickets":
        query = query.where(Task.item_type.notin_(BUILD_TYPES))
    return list(db.scalars(query.order_by(Task.position, Task.created_at)))


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    project_id: str,
    body: TaskIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Task:
    project = get_project_for_user(db, user, project_id, minimum="member")
    last = db.scalar(select(func.max(Task.position)).where(Task.project_id == project.id))
    data = body.model_dump()
    new_status = _stage_status(db, project, data["stage"]) if data["stage"] else data["status"]
    task = Task(
        project_id=project.id,
        position=(last + 1) if last is not None else 0,
        title=data["title"].strip(),
        owner=data["owner"].strip(),
        priority=data["priority"],
        due=data["due"],
        notes=data["notes"].strip(),
        description=data["description"].strip(),
        kind=data["kind"],
        kind_source="label" if data["kind"] else "",
        item_type=data["item_type"].strip(),
        attributes=data["attributes"],
        status=None,
    )
    db.add(task)
    apply_status(task, new_status, db, stage=data["stage"])
    db.commit()
    record_start(task, None, db)
    notify(project.id, [task.id])
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    body: TaskUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Task:
    task = get_task_for_user(db, user, task_id, minimum="member")
    changes = body.model_dump(exclude_unset=True)
    new_status = changes.pop("status", None)
    stage = changes.pop("stage", None)
    if stage:
        new_status = _stage_status(db, task.project, stage)
    for field, value in changes.items():
        if value is None and field != "due":
            continue  # only `due` may be cleared explicitly
        setattr(task, field, value.strip() if isinstance(value, str) else value)
        if field == "kind":
            task.kind_source = "label"
    old_status = task.status
    if new_status:
        apply_status(task, new_status, db, stage=stage)
    db.commit()
    if new_status:
        record_start(task, old_status, db)
    notify(task.project_id, [task.id])
    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    task = get_task_for_user(db, user, task_id, minimum="member")
    project_id = task.project_id
    db.delete(task)
    db.commit()
    notify(project_id, [task_id], deleted=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
