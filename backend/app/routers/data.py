from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_membership
from app.models import Project, Task, TaskEvent, User
from app.routers.projects import _out, next_color
from app.services import analysis, demo_data, importer, ledger
from app.timeutil import naive_utc, now_utc

router = APIRouter(tags=["data"])


def _save(db: Session, project: Project, rows: list[dict], events_of) -> None:
    for i, row in enumerate(rows):
        task = Task(
            project_id=project.id,
            position=i,
            title=row["title"],
            description=row["description"],
            owner=row["owner"],
            priority=row["priority"],
            status=row["status"],
            due=row["due"],
            kind=row["kind"],
            kind_source=row["kind_source"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            external_id=row.get("external_id"),
        )
        db.add(task)
        for frm, to, at in events_of(row):
            db.add(TaskEvent(task=task, from_status=frm, to_status=to, at=at))


@router.post("/workspaces/{workspace_id}/demo-project", status_code=status.HTTP_201_CREATED)
def create_demo_project(
    workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    require_membership(db, user, workspace_id)
    project = Project(
        workspace_id=workspace_id,
        name="Atlas Billing (demo)",
        goal="Six months of sample tickets from a SaaS billing team",
        color=next_color(db, workspace_id),
    )
    db.add(project)
    db.flush()
    now = naive_utc(now_utc())
    rows = demo_data.generate(now)
    _save(db, project, rows, lambda r: r["events"])
    db.flush()
    # Replay history so the demo's forecast ledger shows a real track record.
    ledger.backfill(db, analysis.load(db, project.id, now))
    db.commit()
    return _out(project, {project.id: (len(rows), sum(r["status"] == "done" for r in rows))}).model_dump()


@router.post("/workspaces/{workspace_id}/import", status_code=status.HTTP_201_CREATED)
async def import_csv(
    workspace_id: str,
    file: UploadFile = File(...),
    project_name: str = Form(default="", max_length=80),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    require_membership(db, user, workspace_id)
    raw = await file.read(importer.MAX_BYTES + 1)
    import pandas as pd

    try:
        rows, report = importer.parse_csv(raw, pd.Timestamp(naive_utc(now_utc())))
    except importer.ImportError_ as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not rows:
        raise HTTPException(status_code=400, detail="No usable rows found in this file.")
    name = project_name.strip() or (file.filename or "Imported project").rsplit(".", 1)[0][:80]
    project = Project(
        workspace_id=workspace_id,
        name=name,
        goal="Imported from CSV",
        color=next_color(db, workspace_id),
    )
    db.add(project)
    db.flush()
    _save(db, project, rows, importer.events_for)
    db.commit()
    done = sum(r["status"] == "done" for r in rows)
    return {
        "project": _out(project, {project.id: (len(rows), done)}).model_dump(),
        "report": report,
    }
