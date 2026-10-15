from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_project_for_user, get_task_for_user
from app.models import Task, TaskEvent, User
from app.schemas import TaskIn, TaskOut, TaskUpdate
from app.timeutil import now_utc

router = APIRouter(tags=["tasks"])


def apply_status(task: Task, new_status: str, db: Session) -> None:
    """Record the transition and keep started/completed timestamps consistent."""
    old = task.status if task.id and task.status else None
    if old == new_status:
        return
    now = now_utc()
    task.status = new_status
    if new_status in ("in_progress", "blocked", "done") and task.started_at is None:
        task.started_at = now
    if new_status == "done":
        task.completed_at = now
    elif old == "done":
        task.completed_at = None  # reopened
    db.add(TaskEvent(task=task, from_status=old, to_status=new_status, at=now))


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
def list_tasks(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Task]:
    project = get_project_for_user(db, user, project_id)
    return list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.position, Task.created_at)))


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    project_id: str,
    body: TaskIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Task:
    project = get_project_for_user(db, user, project_id)
    last = db.scalar(select(func.max(Task.position)).where(Task.project_id == project.id))
    data = body.model_dump()
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
        status=None,
    )
    db.add(task)
    apply_status(task, data["status"], db)
    db.commit()
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    body: TaskUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Task:
    task = get_task_for_user(db, user, task_id)
    changes = body.model_dump(exclude_unset=True)
    new_status = changes.pop("status", None)
    for field, value in changes.items():
        if value is None and field != "due":
            continue  # only `due` may be cleared explicitly
        setattr(task, field, value.strip() if isinstance(value, str) else value)
        if field == "kind":
            task.kind_source = "label"
    if new_status:
        apply_status(task, new_status, db)
    db.commit()
    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    task = get_task_for_user(db, user, task_id)
    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
