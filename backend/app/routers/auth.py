import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Membership, OAuthAccount, User, Workspace
from app.schemas import (
    LoginIn,
    MeOut,
    PasswordChange,
    ProfileUpdate,
    RegisterIn,
    TokenOut,
    UserOut,
    WorkspaceOut,
)
from app.security import create_access_token, create_signed, hash_password, read_signed, verify_password
from app.services import oauth

router = APIRouter(prefix="/auth", tags=["auth"])

STATE_COOKIE = "slipcast_oauth"
STATE_MINUTES = 10


def _workspaces(user: User) -> list[WorkspaceOut]:
    return [WorkspaceOut(id=m.workspace.id, name=m.workspace.name, role=m.role) for m in user.memberships]


def _token(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(user.id, user.token_version), user=UserOut.model_validate(user))


def _create_user(db: Session, email: str, name: str, password_hash: str | None) -> User:
    """A new account always gets its own personal workspace, where it is the admin."""
    user = User(email=email, name=name, password_hash=password_hash)
    workspace = Workspace(name=f"{name.split()[0]}'s workspace")
    db.add_all([user, workspace])
    db.flush()
    db.add(Membership(user_id=user.id, workspace_id=workspace.id, role="admin"))
    return user


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = _create_user(db, email, body.name.strip(), hash_password(body.password))
    db.commit()
    return _token(user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return _token(user)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> MeOut:
    methods = (["password"] if user.password_hash else []) + sorted({a.provider for a in user.oauth_accounts})
    return MeOut(
        user=UserOut.model_validate(user),
        workspaces=_workspaces(user),
        has_password=bool(user.password_hash),
        sign_in_methods=methods,
    )


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    """Change the signed-in user's display name."""
    user.name = body.name.strip()
    db.commit()
    return UserOut.model_validate(user)


@router.post("/password", response_model=TokenOut)
def change_password(
    body: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> TokenOut:
    """Set or change the password. Other sessions are signed out; this one gets a fresh token."""
    if user.password_hash and not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Your current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    db.commit()
    return _token(user)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Sign out on every device, including this one."""
    user.token_version += 1
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


# ---------- Sign in with Google / GitHub ----------


@router.get("/providers")
def providers() -> dict[str, bool]:
    """Which sign-in buttons the web app should show. Public; says nothing about any account."""
    return oauth.configured(get_settings())


def _callback_url(request: Request, settings: Settings, provider: str) -> str:
    base = settings.public_api_url.rstrip("/")
    if not base:
        # Behind Render's proxy the app sees plain http; the proxy says what the browser used.
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        base = f"{scheme}://{host}"
    return f"{base}/api/auth/{provider}/callback"


def _safe_next(path: str) -> str:
    """Only same-site paths, so the sign-in flow can't be used to bounce people elsewhere."""
    return path if path.startswith("/") and not path.startswith("//") and "\\" not in path else "/dashboard"


def _to_web(settings: Settings, path: str, fragment: dict[str, str] | None = None, query: dict | None = None):
    url = settings.public_web_url.rstrip("/") + path
    if query:
        url += "?" + urlencode(query)
    if fragment:  # the token travels in the fragment, which browsers never send to any server
        url += "#" + urlencode(fragment)
    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    response.delete_cookie(STATE_COOKIE, path="/api/auth")
    return response


@router.get("/{provider}/start")
def oauth_start(provider: str, request: Request, next: str = "/dashboard") -> RedirectResponse:
    settings = get_settings()
    creds = oauth.credentials(settings, provider) if provider in oauth.PROVIDERS else None
    if creds is None:
        raise HTTPException(status_code=404, detail="This sign-in method isn't set up")
    state, verifier, challenge = oauth.new_pkce()
    redirect_uri = _callback_url(request, settings, provider)
    response = RedirectResponse(
        oauth.authorize_url(provider, creds[0], redirect_uri, state, challenge), status_code=status.HTTP_302_FOUND
    )
    signed = create_signed(
        {"purpose": "oauth", "provider": provider, "state": state, "verifier": verifier, "next": _safe_next(next)},
        STATE_MINUTES,
    )
    response.set_cookie(
        STATE_COOKIE,
        signed,
        max_age=STATE_MINUTES * 60,
        path="/api/auth",
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",  # sent on the provider's top-level redirect back to us, not on cross-site posts
    )
    return response


@router.get("/{provider}/callback")
def oauth_callback(
    provider: str,
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    saved = read_signed(request.cookies.get(STATE_COOKIE, ""), "oauth")
    if error:  # e.g. the person pressed Cancel on the provider's screen
        return _to_web(settings, "/login", query={"error": "cancelled"})
    if (
        not saved
        or saved.get("provider") != provider
        or not state
        or not secrets.compare_digest(str(saved.get("state", "")), state)
        or not code
    ):
        return _to_web(settings, "/login", query={"error": "expired"})

    try:
        who = oauth.fetch_identity(
            provider, settings, code, saved["verifier"], _callback_url(request, settings, provider)
        )
    except oauth.OAuthError as exc:
        return _to_web(settings, "/login", query={"error": exc.code})
    if not who.provider_user_id or not who.email:
        return _to_web(settings, "/login", query={"error": "no_email"})

    link = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider, OAuthAccount.provider_user_id == who.provider_user_id
        )
    )
    if link is not None:
        user = link.user
    else:
        user = db.scalar(select(User).where(User.email == who.email))
        if user is not None and not who.email_verified:
            # Never attach an unverified address to someone's existing account.
            return _to_web(settings, "/login", query={"error": "unverified_email"})
        if user is None:
            if not who.email_verified:
                return _to_web(settings, "/login", query={"error": "unverified_email"})
            user = _create_user(db, who.email, (who.name or who.email.split("@")[0])[:80], None)
        db.add(OAuthAccount(user_id=user.id, provider=provider, provider_user_id=who.provider_user_id, email=who.email))
    db.commit()
    token = create_access_token(user.id, user.token_version)
    return _to_web(settings, "/auth/callback", fragment={"token": token, "next": saved.get("next", "/dashboard")})
