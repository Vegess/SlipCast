"""Each project has its own stages; the engine only ever sees four categories.

Build (software) uses the four statuses directly. Ship and Serve have their own stages
(4.3 lets people pick a module); every stage maps to todo, doing, blocked or done, so flow,
forecasting, risk and the ledger work unchanged for any kind of promise.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project, WorkflowStage

CATEGORY_STATUS = {"todo": "planned", "doing": "in_progress", "blocked": "blocked", "done": "done"}

# (key, label, category)
DEFAULTS: dict[str, list[tuple[str, str, str]]] = {
    "software": [
        ("planned", "Planned", "todo"),
        ("in_progress", "In progress", "doing"),
        ("blocked", "Blocked", "blocked"),
        ("done", "Done", "done"),
        # Pull requests and releases, usually from the GitHub webhook (Build module).
        ("pr_opened", "PR opened", "doing"),
        ("pr_in_review", "PR in review", "doing"),
        ("pr_approved", "PR approved", "doing"),
        ("pr_merged", "PR merged", "done"),
        ("pr_closed", "PR closed without merging", "done"),
        ("release_tagged", "Release tagged", "doing"),
        ("deploy_failed", "Deploy failed", "blocked"),
        ("deployed", "Deployed", "done"),
    ],
    "shipments": [
        ("ordered", "Ordered", "todo"),
        ("packed", "Packed", "doing"),
        ("dispatched", "Dispatched", "doing"),
        ("in_transit", "In transit", "doing"),
        ("out_for_delivery", "Out for delivery", "doing"),
        ("exception", "Exception", "blocked"),
        ("delivered", "Delivered", "done"),
    ],
    "services": [
        ("booked", "Booked", "todo"),
        ("scheduled", "Scheduled", "todo"),
        ("assigned", "Assigned", "doing"),
        ("en_route", "En route", "doing"),
        ("on_site", "On site", "doing"),
        ("rescheduled", "Rescheduled", "blocked"),
        ("done", "Done", "done"),
        ("cancelled", "Cancelled", "done"),
    ],
}


def stages_for(db: Session, project: Project) -> list[dict]:
    """The project's stages in order: its own if it has any, otherwise its module's defaults."""
    rows = db.scalars(
        select(WorkflowStage).where(WorkflowStage.project_id == project.id).order_by(WorkflowStage.order)
    ).all()
    if rows:
        return [{"key": r.key, "label": r.label, "category": r.category} for r in rows]
    defaults = DEFAULTS.get(project.template, DEFAULTS["software"])
    return [{"key": k, "label": label, "category": c} for k, label, c in defaults]


def status_for(stages: list[dict], stage_key: str) -> str | None:
    """The engine status for a stage key, or None if the project has no such stage."""
    for s in stages:
        if s["key"] == stage_key:
            return CATEGORY_STATUS[s["category"]]
    return None
