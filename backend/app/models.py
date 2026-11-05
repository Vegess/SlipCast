import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

STATUSES = ("planned", "in_progress", "blocked", "done")
PRIORITIES = ("low", "medium", "high")
KINDS = ("bug", "feature", "tech_debt", "support")


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship(cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id", name="uq_membership"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")

    user: Mapped[User] = relationship(back_populates="memberships")
    workspace: Mapped[Workspace] = relationship(back_populates="memberships")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    goal: Mapped[str] = mapped_column(String(300), default="")
    color: Mapped[str] = mapped_column(String(9), default="#7D96F2")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    tasks: Mapped[list["Task"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Task.position"
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(140))
    owner: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(20), default="planned")
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    due: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    # kind_source: "label" (imported or set by a person), "" (unknown; the classifier predicts it)
    kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    kind_source: Mapped[str] = mapped_column(String(10), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="tasks")
    events: Mapped[list["TaskEvent"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskEvent.at"
    )


class TaskEvent(Base):
    """Every status change. This history powers cycle time, flow and forecasting."""

    __tablename__ = "task_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Task] = relationship(back_populates="events")


class Forecast(Base):
    """Every forecast SlipCast makes, scored automatically once the real outcome is known.

    kind "project_completion": when will the tickets open at `made_at` all be done?
      Uses p50_date / p85_date; `actual_date` is when the last of them finished.
    kind "ticket_reference_class": how many days will this ticket take once started?
      Uses p10/p50/p85/p90_days; `actual_days` is its real cycle time.
    `hit_p85` is whether the outcome landed within the 85th-percentile forecast; it stays
    null while unresolved, and for "void" entries whose subject was deleted.
    """

    __tablename__ = "forecasts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    made_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    p50_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    p85_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    p10_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    p50_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    p85_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    p90_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    hit_p85: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    void: Mapped[bool] = mapped_column(Boolean, default=False)


class AdviceLog(Base):
    """One advice request: what the LLM produced and how much survived validation."""

    __tablename__ = "advice_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(20))  # suggestions | report | rewrite
    provider: Mapped[str] = mapped_column(String(20))  # groq | rules | template
    llm_called: Mapped[bool] = mapped_column(Boolean, default=False)
    privacy_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    generated: Mapped[int] = mapped_column(Integer, default=0)
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(300), default="")


class AdviceFeedback(Base):
    """Helpful / not helpful votes on suggestions, one per user per suggestion."""

    __tablename__ = "advice_feedback"
    __table_args__ = (UniqueConstraint("project_id", "user_id", "suggestion_key", name="uq_advice_feedback"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    suggestion_key: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(10))  # llm | rules
    helpful: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportRecord(Base):
    """A CSV import and its data-quality report, kept so people can review it later."""

    __tablename__ = "imports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    # The project survives as a link only while it exists; the report outlives it.
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    project_name: Mapped[str] = mapped_column(String(80))
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
