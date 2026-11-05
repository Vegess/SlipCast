from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_project_for_user
from app.models import User
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
    return get_analysis(db, project.id).forecast(target)
