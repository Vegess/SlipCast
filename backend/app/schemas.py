from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Status = Literal["planned", "in_progress", "blocked", "done"]
Priority = Literal["low", "medium", "high"]
Kind = Literal["bug", "feature", "tech_debt", "support"]
HexColor = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


# ---------- auth ----------
class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=64)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=64)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str


class WorkspaceOut(BaseModel):
    id: str
    name: str
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")


class MeOut(BaseModel):
    user: UserOut
    workspaces: list[WorkspaceOut]
    has_password: bool = True
    sign_in_methods: list[str] = []  # "password", "google", "github"


class PasswordChange(BaseModel):
    # Not needed when the account has no password yet (it signed up with Google or GitHub).
    current_password: str = Field(default="", max_length=64)
    new_password: str = Field(min_length=8, max_length=64)


# ---------- teams ----------
class MemberOut(BaseModel):
    user_id: str
    name: str
    email: str
    role: str
    is_you: bool


class RoleIn(BaseModel):
    role: str = Field(pattern="^(admin|member|viewer)$")


class InviteOut(BaseModel):
    id: str
    role: str
    created_at: datetime
    expires_at: datetime
    url: str | None = None  # only in the response that creates the invite


class InvitePreview(BaseModel):
    workspace_name: str
    role: str
    invited_by: str
    valid: bool
    reason: str = ""


# ---------- projects ----------
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    goal: str = Field(default="", max_length=300)
    color: str | None = HexColor


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    goal: str | None = Field(default=None, max_length=300)
    color: str | None = HexColor


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str
    name: str
    goal: str
    color: str
    created_at: datetime
    task_count: int = 0
    done_count: int = 0


# ---------- tasks ----------
class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    owner: str = Field(default="", max_length=40)
    status: Status = "planned"
    priority: Priority = "medium"
    due: date | None = None
    notes: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=5000)
    kind: Kind | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=140)
    owner: str | None = Field(default=None, max_length=40)
    status: Status | None = None
    priority: Priority | None = None
    due: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=5000)
    kind: Kind | None = None
    position: int | None = Field(default=None, ge=0)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    title: str
    owner: str
    status: Status
    priority: Priority
    due: date | None
    notes: str
    description: str
    kind: str | None
    kind_source: str
    stage: str | None = None
    item_type: str = ""
    attributes: dict | None = None
    started_at: datetime | None
    completed_at: datetime | None
    position: int
    created_at: datetime
    updated_at: datetime


# ---------- insights ----------
class Insight(BaseModel):
    kind: str
    severity: Literal["info", "warning", "critical"]
    message: str
    task_ids: list[str] = Field(default_factory=list)


class InsightsOut(BaseModel):
    project_id: str
    health: Literal["on_track", "at_risk", "off_track"]
    completion: float
    open_count: int
    insights: list[Insight]


class StatusReportOut(BaseModel):
    project_id: str
    report: str
    provider: str
    generated_at: datetime


# ---------- analytics ----------
class DraftIn(BaseModel):
    """A ticket as it is being written; nothing is saved."""

    title: str = Field(default="", max_length=140)
    description: str = Field(default="", max_length=5000)
    owner: str = Field(default="", max_length=40)
    due: date | None = None
    priority: Priority = "medium"
    kind: Kind | None = None
    task_id: str | None = Field(default=None, max_length=32, description="Set when editing a saved ticket")
