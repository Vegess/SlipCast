from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_project_for_user, get_task_for_user
from app.models import User
from app.schemas import DraftIn
from app.services import build_metrics, export, ledger
from app.services.analysis import get_analysis
from app.timeutil import now_utc

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


@router.get("/projects/{project_id}/analytics/text")
def text(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Themes, likely duplicates, ticket quality and type counts from ticket text."""
    project = get_project_for_user(db, user, project_id)
    return get_analysis(db, project.id).text_insights()


@router.get("/projects/{project_id}/analytics/risk")
def risk(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Open tickets ranked by predicted chance of finishing after their due date."""
    project = get_project_for_user(db, user, project_id)
    return get_analysis(db, project.id).risk.open_risks()


@router.get("/projects/{project_id}/analytics/evaluation")
def evaluation(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """How well every model performs on data it never saw, against simple baselines."""
    project = get_project_for_user(db, user, project_id)
    analysis = get_analysis(db, project.id)
    ledger_summary = ledger.summary(db, analysis)
    ledger_summary.pop("entries")
    from app.routers.advice import advice_stats

    return {**analysis.evaluation, "ledger": ledger_summary, "advice": advice_stats(db, project.id)}


@router.get("/projects/{project_id}/analytics/build")
def build_analytics(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Pull requests, releases and deployments: review wait, size classes and DORA metrics."""
    project = get_project_for_user(db, user, project_id)
    return build_metrics.compute(db, project.id, now_utc())


@router.get("/tasks/{task_id}/analysis")
def task_analysis(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Type, theme, quality, slip risk, reference class and duplicates for one ticket."""
    task = get_task_for_user(db, user, task_id)
    return get_analysis(db, task.project_id).task_analysis(task.id)


@router.get("/projects/{project_id}/export.xlsx")
def export_excel(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Excel workbook: tickets, history, cycle times, throughput, forecast, ledger and model metrics."""
    project = get_project_for_user(db, user, project_id)
    analysis = get_analysis(db, project.id)
    data = export.workbook(db, analysis, project.name, ledger.summary(db, analysis))
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="slipcast-{export.slug(project.name)}.xlsx"'},
    )


@router.get("/projects/{project_id}/export/bi.zip")
def export_bi(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Tidy CSVs (one row per entity, ISO dates) for Tableau or Power BI."""
    project = get_project_for_user(db, user, project_id)
    data = export.bi_zip(db, get_analysis(db, project.id))
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="slipcast-{export.slug(project.name)}-bi.zip"'},
    )
