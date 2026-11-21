"""Alerts: the 85% forecast moved by 2+ days, or a newly arrived item looks likely to be late."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, Project, Task
from app.services import risk_model
from app.services.analysis import get_analysis

SLIP_DAYS = 2
GROUP_ABOVE = 2  # more risky new items than this in one change become one grouped alert


def _day(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}"


def baseline(db: Session, project: Project) -> None:
    """Remember the current 85% date before a change, so the change itself can be measured."""
    if project.last_p85 is not None:
        return
    fc = get_analysis(db, project.id).forecast()["forecast"]
    if fc.get("available") and fc.get("p85"):
        project.last_p85 = date.fromisoformat(str(fc["p85"])[:10])


def check(db: Session, project: Project, new_task_ids: list[str]) -> list[Alert]:
    """Creates and returns the alerts this change caused. The caller commits."""
    analysis = get_analysis(db, project.id)
    alerts: list[Alert] = []

    fc = analysis.forecast()["forecast"]
    if fc.get("available") and fc.get("p85"):
        new = date.fromisoformat(str(fc["p85"])[:10])
        old = project.last_p85
        if old is None:
            project.last_p85 = new  # first sighting is the baseline, not news
        elif abs((new - old).days) >= SLIP_DAYS:
            delta = (new - old).days
            later = delta > 0
            alerts.append(
                Alert(
                    project_id=project.id,
                    kind="forecast_slip" if later else "forecast_gain",
                    severity="warning" if later else "info",
                    message=(
                        f"{project.name}: the 85% finish date moved {'later' if later else 'earlier'} "
                        f"by {abs(delta)} days, from {_day(old)} to {_day(new)}."
                    ),
                    data={"from": old.isoformat(), "to": new.isoformat(), "days": delta},
                )
            )
            project.last_p85 = new  # small drifts below 2 days accumulate until they matter

    if new_task_ids and analysis.risk.available:
        risky = []
        for task in db.scalars(select(Task).where(Task.id.in_(new_task_ids), Task.due.is_not(None))):
            if task.status == "done":
                continue
            planned = (task.due - analysis.today).days
            scored = analysis.risk.score_draft(
                task.title, task.description or "", task.owner or "", planned, task.priority, task.kind or "unknown"
            )
            if scored and scored["risk"] >= risk_model.HIGH_RISK:
                risky.append((scored["risk"], task, scored["factors"]))
        risky.sort(key=lambda r: -r[0])
        if len(risky) <= GROUP_ABOVE:
            for risk, task, factors in risky:
                alerts.append(
                    Alert(
                        project_id=project.id,
                        kind="high_risk",
                        severity="critical" if risk >= 0.8 else "warning",
                        message=f'New: "{task.title[:80]}" has a {round(risk * 100)}% chance of missing its date.',
                        data={"task_id": task.id, "risk": risk, "factors": factors[:3]},
                    )
                )
        elif risky:
            # A batch of similar new work is one piece of news, not a pile of toasts.
            top = risky[0]
            names = ", ".join(f'"{t.title[:40]}"' for _, t, _ in risky[:2])
            alerts.append(
                Alert(
                    project_id=project.id,
                    kind="high_risk",
                    severity="critical" if top[0] >= 0.8 else "warning",
                    message=f"{len(risky)} new items look likely to miss their dates, including {names}.",
                    data={
                        "count": len(risky),
                        "task_ids": [t.id for _, t, _ in risky[:20]],
                        "risk": top[0],
                        "factors": top[2][:3],
                    },
                )
            )

    db.add_all(alerts)
    return alerts


def to_dict(a: Alert, project_name: str = "") -> dict:
    return {
        "id": a.id,
        "project_id": a.project_id,
        "project_name": project_name,
        "kind": a.kind,
        "severity": a.severity,
        "message": a.message,
        "data": a.data or {},
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
