"""Rule-based project health checks.

Deliberately deterministic: these signals feed the dashboard directly and also give
the LLM status report grounded facts, so the model summarises rather than invents.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from app.schemas import Insight


@dataclass(frozen=True)
class TaskView:
    id: str
    title: str
    owner: str
    status: str
    priority: str
    due: date | None


@dataclass(frozen=True)
class HealthResult:
    health: str
    completion: float
    open_count: int
    insights: list[Insight]


def _names(tasks: list[TaskView], limit: int = 3) -> str:
    titles = [f"“{t.title}”" for t in tasks[:limit]]
    extra = len(tasks) - limit
    return ", ".join(titles) + (f" and {extra} more" if extra > 0 else "")


# The same checks in each module's words (Build keeps the original wording).
WORDS = {
    "software": {
        "one": "task", "many": "tasks", "blocked": "blocked", "unblock": "Unblock these first.",
        "unowned": "High-priority work has no owner", "not_started": "Due within 3 days and not started",
        "due": "due date",
    },
    "shipments": {
        "one": "order", "many": "orders", "blocked": "with an exception", "unblock": "Contact the carrier first.",
        "unowned": "Express orders have no carrier", "not_started": "Due within 3 days and not packed yet",
        "due": "promised date",
    },
    "services": {
        "one": "job", "many": "jobs", "blocked": "rescheduled", "unblock": "Confirm a new time with the customer.",
        "unowned": "Urgent jobs have no technician", "not_started": "Due within 3 days and not assigned yet",
        "due": "appointment date",
    },
}  # fmt: skip


def analyse(tasks: list[TaskView], today: date, template: str = "software") -> HealthResult:
    w = WORDS.get(template, WORDS["software"])
    total = len(tasks)
    open_tasks = [t for t in tasks if t.status != "done"]
    completion = round((total - len(open_tasks)) / total, 3) if total else 0.0
    insights: list[Insight] = []

    overdue = sorted((t for t in open_tasks if t.due and t.due < today), key=lambda t: t.due or today)
    if overdue:
        high = any(t.priority == "high" for t in overdue)
        insights.append(
            Insight(
                kind="overdue",
                severity="critical" if high or len(overdue) >= 3 else "warning",
                message=f"{len(overdue)} {w['many'] + ' are' if len(overdue) > 1 else w['one'] + ' is'} overdue: "
                f"{_names(overdue)}.",
                task_ids=[t.id for t in overdue],
            )
        )

    blocked = [t for t in open_tasks if t.status == "blocked"]
    if blocked:
        insights.append(
            Insight(
                kind="blocked",
                severity="warning",
                message=f"{len(blocked)} {w['blocked']}: {_names(blocked)}. {w['unblock']}",
                task_ids=[t.id for t in blocked],
            )
        )

    unassigned = [t for t in open_tasks if t.priority == "high" and not t.owner.strip()]
    if unassigned:
        insights.append(
            Insight(
                kind="unassigned",
                severity="warning",
                message=f"{w['unowned']}: {_names(unassigned)}.",
                task_ids=[t.id for t in unassigned],
            )
        )

    owners = Counter(t.owner.strip() for t in open_tasks if t.owner.strip())
    if len(open_tasks) >= 5 and len(owners) >= 2:
        owner, count = owners.most_common(1)[0]
        if count / len(open_tasks) > 0.4:
            insights.append(
                Insight(
                    kind="overload",
                    severity="warning",
                    message=f"{owner} holds {count} of {len(open_tasks)} open {w['many']}. Consider rebalancing.",
                    task_ids=[t.id for t in open_tasks if t.owner.strip() == owner],
                )
            )

    soon = today + timedelta(days=3)
    not_started = [t for t in open_tasks if t.status == "planned" and t.due and today <= t.due <= soon]
    if not_started:
        insights.append(
            Insight(
                kind="due_soon",
                severity="info",
                message=f"{w['not_started']}: {_names(not_started)}.",
                task_ids=[t.id for t in not_started],
            )
        )

    undated = [t for t in open_tasks if t.due is None]
    if open_tasks and len(undated) / len(open_tasks) > 0.3:
        insights.append(
            Insight(
                kind="undated",
                severity="info",
                message=f"{len(undated)} open {w['many']} have no {w['due']}, so the timeline can't show them.",
                task_ids=[t.id for t in undated],
            )
        )

    severities = {i.severity for i in insights}
    if "critical" in severities:
        health = "off_track"
    elif "warning" in severities:
        health = "at_risk"
    else:
        health = "on_track"

    return HealthResult(health=health, completion=completion, open_count=len(open_tasks), insights=insights)
