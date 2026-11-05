from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Membership, User, Workspace
from app.schemas import LoginIn, MeOut, ProfileUpdate, RegisterIn, TokenOut, UserOut, WorkspaceOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _workspaces(user: User) -> list[WorkspaceOut]:
    return [WorkspaceOut(id=m.workspace.id, name=m.workspace.name, role=m.role) for m in user.memberships]


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    first_name = user.name.split()[0]
    workspace = Workspace(name=f"{first_name}'s workspace")
    db.add_all([user, workspace])
    db.flush()
    db.add(Membership(user_id=user.id, workspace_id=workspace.id, role="owner"))
    db.commit()
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> MeOut:
    return MeOut(user=UserOut.model_validate(user), workspaces=_workspaces(user))


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    """Change the signed-in user's display name."""
    user.name = body.name.strip()
    db.commit()
    return UserOut.model_validate(user)


@router.get("/ai-status")
def ai_status(user: User = Depends(get_current_user)) -> dict:
    """Which advice provider is active. Never returns the key itself."""
    s = get_settings()
    configured = bool(s.groq_api_key)
    return {
        "provider": "groq" if configured else "rules",
        "configured": configured,
        "model": s.groq_model if configured else None,
        "limits": {"per_minute": s.advice_per_minute, "per_day": s.advice_per_day},
    }
