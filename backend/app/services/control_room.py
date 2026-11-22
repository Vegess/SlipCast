"""Control Room: every promise due in the next 7 days across a workspace, riskiest first.

Nothing new is predicted here. Each project's promises are scored by its own module's model
(the slip-risk model for tickets, late-delivery risk for orders, missed-visit risk for jobs),
so a risk on this page is exactly the risk shown on that project's own screens. The track
record per module comes from the forecast ledger, which every module shares.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BUILD_TYPES, IngestedEvent, Project, Task, TaskEvent
from app.services import ledger, serve_metrics, ship_metrics
from app.services.analysis import get_analysis
from app.services.risk_model import HIGH_RISK
from app.timeutil import naive_utc

HORIZON = timedelta(days=7)
LIMIT = 60
MODULES = {"software": "Build", "shipments": "Ship", "services": "Serve"}
NOUN = {"software": "ticket", "shipments": "order", "services": "job"}
LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2, None: 3}


def _level(risk: float | None, high: float, medium: float) -> str | None:
    if risk is None:
        return None
    return "high" if risk >= high else "medium" if risk >= medium else "low"


def _promise(p: Project, **fields) -> dict:
    return {"project_id": p.id, "project": p.name, "color": p.color, "template": p.template,
            "module": MODULES.get(p.template, "Build"), **fields}  # fmt: skip


def _tickets(db: Session, p: Project, analysis, now: datetime) -> list[dict]:
    last = (now + HORIZON).date()
    risk = analysis.risk.open_risks() if analysis.risk.available else {"items": []}
    scored = {i["id"]: i for i in risk["items"]}
    rows = db.execute(
        select(Task.id, Task.title, Task.owner, Task.due, Task.stage, Task.status).where(
            Task.project_id == p.id, Task.item_type.notin_(BUILD_TYPES), Task.status != "done",
            Task.due.is_not(None), Task.due <= last,
        )
    ).all()  # fmt: skip
    out = []
    for tid, title, owner, due, stage, status in rows:
        s = scored.get(tid)
        r = s["risk"] if s else None
        reasons = list(s["factors"]) if s else []
        if due < now.date():
            r = 1.0
            reasons.insert(0, f"Overdue since {due.isoformat()}")
        out.append(_promise(p, id=tid, title=title, owner=owner, due=due.isoformat(), when=None,
                            stage=stage or status, risk=r, level=_level(r, HIGH_RISK, 0.35),
                            reasons=reasons[:2]))  # fmt: skip
    return out


def _orders(db: Session, p: Project, now: datetime) -> list[dict]:
    m = ship_metrics.compute(db, p.id, now)
    last = (now + HORIZON).date().isoformat()
    return [
        _promise(
            p,
            id=o["id"],
            title=o["title"],
            owner=o["carrier"],
            due=o["due"],
            when=None,
            stage=o["stage"],
            risk=o["risk"],
            level=o["level"],
            reasons=o["reasons"][:2],
        )  # fmt: skip
        for o in m.get("at_risk", [])
        if o["due"] and o["due"] <= last
    ]


def _jobs(db: Session, p: Project, now: datetime) -> list[dict]:
    m = serve_metrics.compute(db, p.id, now)
    out = []
    for j in m.get("upcoming", []):
        start = j["window_start"]
        day = (
            (naive_utc(datetime.fromisoformat(start.replace("Z", "+00:00"))) + serve_metrics.IST).date()
            if start
            else None
        )
        out.append(_promise(p, id=j["id"], title=j["title"], owner=j["tech"], due=day.isoformat() if day else None,
                            when=start, stage=j["stage"], risk=j["risk"], level=j["level"],
                            reasons=j["reasons"][:2]))  # fmt: skip
    return out


def activity(db: Session, project_ids: list[str], names: dict[str, str], limit: int = 30) -> list[dict]:
    """Latest stage changes: events from other systems, and status changes made in SlipCast."""
    if not project_ids:
        return []
    titles = {
        (pid, ext): (tid, title)
        for tid, pid, ext, title in db.execute(
            select(Task.id, Task.project_id, Task.external_id, Task.title).where(
                Task.project_id.in_(project_ids), Task.external_id.is_not(None)
            )
        )
    }
    items = []
    for pid, ext, stage, at in db.execute(
        select(IngestedEvent.project_id, IngestedEvent.external_id, IngestedEvent.stage, IngestedEvent.occurred_at)
        .where(IngestedEvent.project_id.in_(project_ids))
        .order_by(IngestedEvent.occurred_at.desc())
        .limit(limit)
    ):
        tid, title = titles.get((pid, ext), (None, ext))
        items.append({"at": naive_utc(at), "project_id": pid, "project": names[pid], "task_id": tid,
                      "title": title, "stage": stage})  # fmt: skip
    for pid, tid, title, to, at in db.execute(
        select(Task.project_id, Task.id, Task.title, TaskEvent.to_status, TaskEvent.at)
        .join(Task, Task.id == TaskEvent.task_id)
        .where(Task.project_id.in_(project_ids), Task.external_id.is_(None))
        .order_by(TaskEvent.at.desc())
        .limit(limit)
    ):
        items.append({"at": naive_utc(at), "project_id": pid, "project": names[pid], "task_id": tid,
                      "title": title, "stage": to})  # fmt: skip
    items.sort(key=lambda i: i["at"], reverse=True)
    return [{**i, "at": i["at"].isoformat() + "Z"} for i in items[:limit]]


def compute(db: Session, workspace_id: str, now: datetime) -> dict:
    now = naive_utc(now)
    projects = db.scalars(
        select(Project).where(Project.workspace_id == workspace_id).order_by(Project.created_at)
    ).all()
    if not projects:
        return {"available": False, "reason": "No projects yet. Create one, or open a demo, and its promises "
                "due in the next 7 days will appear here.", "promises": [], "projects": [], "modules": [],
                "activity": []}  # fmt: skip

    promises, cards = [], []
    modules: dict[str, dict] = {}
    for p in projects:
        analysis = get_analysis(db, p.id)
        if p.template == "shipments":
            mine = _orders(db, p, now)
        elif p.template == "services":
            mine = _jobs(db, p, now)
        else:
            mine = _tickets(db, p, analysis, now)
        promises += mine
        fc = analysis.forecast()["forecast"]
        record = ledger.summary(db, analysis, limit=0)
        cards.append({
            "id": p.id, "name": p.name, "color": p.color, "template": p.template, "module": MODULES.get(p.template),
            "noun": NOUN.get(p.template, "ticket"), "open": int((analysis.tickets["status"] != "done").sum()),
            "due_soon": len(mine), "high_risk": sum(m["level"] == "high" for m in mine),
            "forecast_p85": fc.get("p85") if fc.get("available") else None,
            "hit_rate": record["hit_rate"], "scored": record["resolved"],
        })  # fmt: skip
        empty = {"template": p.template, "module": MODULES.get(p.template), "projects": 0, "due_soon": 0,
                 "high_risk": 0, "scored": 0, "hits": 0}  # fmt: skip
        mod = modules.setdefault(p.template, empty)
        mod["projects"] += 1
        mod["due_soon"] += len(mine)
        mod["high_risk"] += sum(m["level"] == "high" for m in mine)
        mod["scored"] += record["resolved"]
        mod["hits"] += round((record["hit_rate"] or 0) * record["resolved"])
    for mod in modules.values():
        mod["hit_rate"] = round(mod["hits"] / mod["scored"], 3) if mod["scored"] else None

    promises.sort(key=lambda m: (LEVEL_ORDER[m["level"]], -(m["risk"] or 0), m["due"] or "9999"))
    days = [(now.date() + timedelta(days=i)).isoformat() for i in range(8)]
    names = {p.id: p.name for p in projects}
    return {
        "available": True,
        "reason": "",
        "now": now.isoformat() + "Z",
        "days": days,
        "counts": {
            "due_soon": len(promises),
            "high_risk": sum(m["level"] == "high" for m in promises),
            "overdue": sum(bool(m["due"]) and m["due"] < days[0] for m in promises),
        },  # fmt: skip
        "modules": [modules[t] for t in MODULES if t in modules],
        "projects": cards,
        "promises": promises[:LIMIT],
        "activity": activity(db, [p.id for p in projects], names),
    }
