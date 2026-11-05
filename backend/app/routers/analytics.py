from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_project_for_user, get_task_for_user
from app.models import User
from app.schemas import DraftIn
from app.services import ledger
from app.services.analysis import get_analysis

router = APIRouter(tags=["analytics"])


@router.get("/projects/{project_id}/analytics/overview")
def overview(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Headline numbers for the Delivery tab."""
    project = get_project_for_user(db, user, project_id)
    return get_analysis(db, project.id).overview()


@router.get("/projects/{project_id}/analytics/flow")
def flow(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Cycle time, throughput, cumulative flow, breakdowns and aging work in progress."""
    project = get_project_for_user(db, user, project_id)
    return get_analysis(db, project.id).flow


@router.get("/projects/{project_id}/analytics/forecast")
def forecast(
    project_id: str,
    target: date | None = Query(default=None, description="Optional target date to score"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Monte Carlo completion forecast for all open tickets, with burn-up data."""
    project = get_project_for_user(db, user, project_id)
    analysis = get_analysis(db, project.id)
    if ledger.record_project(db, analysis):  # at most once per project per day
        db.commit()
    return analysis.forecast(target)


@router.get("/projects/{project_id}/forecast-ledger")
def forecast_ledger(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Track record: every forecast made for this project and how it turned out."""
    project = get_project_for_user(db, user, project_id)
    return ledger.summary(db, get_analysis(db, project.id))


@router.get("/tasks/{task_id}/reference-class")
def task_reference_class(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """How long the most similar finished tickets really took, compared with this ticket's plan."""
    task = get_task_for_user(db, user, task_id)
    return get_analysis(db, task.project_id).reference_for_task(task.id)


@router.post("/projects/{project_id}/reference-class")
def draft_reference_class(
    project_id: str, body: DraftIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Reference class for an unsaved draft (title and description)."""
    project = get_project_for_user(db, user, project_id)
    analysis = get_analysis(db, project.id)
    planned = (body.due - analysis.today).days if body.due else None
    return analysis.reference(body.title, body.description, planned)


@router.post("/projects/{project_id}/ticket-check")
def ticket_check(
    project_id: str, body: DraftIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Write-time risk check while a ticket is being typed. Reuses the cached analysis."""
    project = get_project_for_user(db, user, project_id)
    return get_analysis(db, project.id).ticket_check(
        body.title, body.description, body.owner, body.due, body.priority, body.kind, exclude_id=body.task_id
    )
