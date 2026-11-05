from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user, get_project_for_user
from app.models import AdviceFeedback, AdviceLog, User
from app.schemas import Kind, StatusReportOut
from app.services import advisor, findings
from app.services.analysis import get_analysis
from app.timeutil import now_utc

router = APIRouter(tags=["advice"])


class AdviceIn(BaseModel):
    privacy_mode: bool = False


class RewriteIn(AdviceIn):
    title: str = Field(default="", max_length=140)
    description: str = Field(default="", max_length=5000)
    kind: Kind | None = None


class FeedbackIn(BaseModel):
    suggestion_key: str = Field(min_length=1, max_length=40)
    source: str = Field(pattern="^(llm|rules)$")
    helpful: bool


def llm_for(db: Session, user: User) -> tuple[advisor.LLM | None, str | None]:
    """The LLM if configured and this user is within the per-minute and per-day limits."""
    llm = advisor.get_llm()
    if llm is None:
        return None, None
    s, now = get_settings(), now_utc()

    def used(since) -> int:
        q = select(func.count(AdviceLog.id)).where(
            AdviceLog.user_id == user.id, AdviceLog.llm_called.is_(True), AdviceLog.created_at >= since
        )
        return db.scalar(q) or 0

    if used(now - timedelta(minutes=1)) >= s.advice_per_minute:
        return None, f"AI limit reached ({s.advice_per_minute} requests a minute)."
    if used(now - timedelta(days=1)) >= s.advice_per_day:
        return None, f"AI limit reached ({s.advice_per_day} requests a day)."
    return llm, None


def _log(db: Session, project_id: str, user: User, kind: str, provider: str, privacy: bool, **kw) -> None:
    db.add(AdviceLog(project_id=project_id, user_id=user.id, kind=kind, provider=provider, privacy_mode=privacy, **kw))
    db.commit()


@router.post("/projects/{project_id}/advice")
def advice(
    project_id: str, body: AdviceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """3 to 5 suggestions grounded in computed findings, validated before they are shown."""
    project = get_project_for_user(db, user, project_id)
    found = findings.build(get_analysis(db, project.id), privacy=body.privacy_mode)
    llm, limited = llm_for(db, user)
    result = advisor.suggest(found, llm)
    _log(
        db,
        project.id,
        user,
        "suggestions",
        result.provider,
        body.privacy_mode,
        llm_called=result.llm_called,
        generated=result.generated,
        accepted=result.accepted,
        rejected=result.rejected,
        error=(result.error or limited or "")[:300],
    )
    votes = db.execute(
        select(AdviceFeedback.suggestion_key, AdviceFeedback.helpful).where(
            AdviceFeedback.project_id == project.id, AdviceFeedback.user_id == user.id
        )
    ).all()
    return {
        "provider": result.provider,
        "suggestions": result.suggestions,
        "findings": [f.out() for f in found],
        "privacy_mode": body.privacy_mode,
        "error": result.error or limited,
        "validation": result.validation(),
        "feedback": dict(votes),
    }


@router.post("/projects/{project_id}/feedback", status_code=204)
def feedback(
    project_id: str, body: FeedbackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    """Record whether a suggestion was helpful (one vote per user per suggestion; later votes replace it)."""
    project = get_project_for_user(db, user, project_id)
    row = db.scalar(
        select(AdviceFeedback).where(
            AdviceFeedback.project_id == project.id,
            AdviceFeedback.user_id == user.id,
            AdviceFeedback.suggestion_key == body.suggestion_key,
        )
    )
    if row is None:
        row = AdviceFeedback(project_id=project.id, user_id=user.id, suggestion_key=body.suggestion_key)
        db.add(row)
    row.source, row.helpful = body.source, body.helpful
    db.commit()


@router.post("/projects/{project_id}/status-report", response_model=StatusReportOut)
def status_report(
    project_id: str, body: AdviceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> StatusReportOut:
    """Weekly status report in Markdown, written only from computed findings."""
    project = get_project_for_user(db, user, project_id)
    found = findings.build(get_analysis(db, project.id), privacy=body.privacy_mode)
    llm, limited = llm_for(db, user)
    report, provider = advisor.status_report(project.name, found, llm)
    _log(db, project.id, user, "report", provider, body.privacy_mode, llm_called=llm is not None, error=limited or "")
    return StatusReportOut(project_id=project.id, report=report, provider=provider, generated_at=now_utc())


@router.post("/projects/{project_id}/rewrite")
def rewrite(
    project_id: str, body: RewriteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """A clearer version of a ticket. Privacy mode always uses the template, never the LLM."""
    project = get_project_for_user(db, user, project_id)
    llm, limited = (None, None) if body.privacy_mode else llm_for(db, user)
    out = advisor.rewrite(body.title, body.description, body.kind, llm, body.privacy_mode)
    _log(
        db,
        project.id,
        user,
        "rewrite",
        out["provider"],
        body.privacy_mode,
        llm_called=llm is not None,
        error=limited or "",
    )
    return out


def advice_stats(db: Session, project_id: str) -> dict:
    """Grounding pass rate of LLM suggestions and helpfulness votes, for the evaluation page."""
    gen, acc, rej = db.execute(
        select(
            func.coalesce(func.sum(AdviceLog.generated), 0),
            func.coalesce(func.sum(AdviceLog.accepted), 0),
            func.coalesce(func.sum(AdviceLog.rejected), 0),
        ).where(AdviceLog.project_id == project_id, AdviceLog.kind == "suggestions")
    ).one()
    votes = db.execute(
        select(AdviceFeedback.source, AdviceFeedback.helpful, func.count(AdviceFeedback.id))
        .where(AdviceFeedback.project_id == project_id)
        .group_by(AdviceFeedback.source, AdviceFeedback.helpful)
    ).all()
    fb = {s: {"helpful": 0, "not_helpful": 0, "helpful_rate": None} for s in ("llm", "rules")}
    for source, helpful, n in votes:
        fb[source]["helpful" if helpful else "not_helpful"] += n
    for v in fb.values():
        total = v["helpful"] + v["not_helpful"]
        v["helpful_rate"] = round(v["helpful"] / total, 3) if total else None
    return {
        "generated": int(gen),
        "accepted": int(acc),
        "rejected": int(rej),
        "grounding_pass_rate": round(acc / gen, 3) if gen else None,
        "feedback": fb,
    }
