"""Sign in with Google and GitHub: OAuth 2.0 authorization-code flow with state and PKCE.

The API runs the whole flow on its own domain, so no provider secret or access token ever
reaches the browser. The provider's access token is used once, to read the person's name
and verified email address, and is then discarded.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import Settings

PROVIDERS: dict[str, dict[str, str]] = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scope": "openid email profile",
    },
    "github": {
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "scope": "read:user user:email",
    },
}


@dataclass
class Identity:
    provider_user_id: str
    email: str
    email_verified: bool
    name: str


class OAuthError(Exception):
    """Something went wrong talking to the provider; `code` is shown to the person as a reason."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def credentials(settings: Settings, provider: str) -> tuple[str, str] | None:
    pair = (getattr(settings, f"{provider}_client_id", ""), getattr(settings, f"{provider}_client_secret", ""))
    return pair if all(pair) else None


def configured(settings: Settings) -> dict[str, bool]:
    return {p: credentials(settings, p) is not None for p in PROVIDERS}


def new_pkce() -> tuple[str, str, str]:
    """Returns (state, code_verifier, code_challenge)."""
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return secrets.token_urlsafe(24), verifier, challenge


def authorize_url(provider: str, client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    p = PROVIDERS[provider]
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": p["scope"],
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if provider == "google":
        params["prompt"] = "select_account"
    else:
        params["allow_signup"] = "true"
    return f"{p['authorize']}?{urlencode(params)}"


def fetch_identity(provider: str, settings: Settings, code: str, verifier: str, redirect_uri: str) -> Identity:
    """Exchanges the code for a token and reads who signed in. Tests replace this function."""
    client_id, client_secret = credentials(settings, provider) or ("", "")
    try:
        with httpx.Client(timeout=10, headers={"Accept": "application/json"}) as http:
            token = http.post(
                PROVIDERS[provider]["token"],
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "code_verifier": verifier,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            access = token.json().get("access_token") if token.status_code == 200 else None
            if not access:
                raise OAuthError("exchange_failed")
            auth = {"Authorization": f"Bearer {access}"}
            if provider == "google":
                info = http.get("https://openidconnect.googleapis.com/v1/userinfo", headers=auth).json()
                return Identity(
                    provider_user_id=str(info.get("sub", "")),
                    email=str(info.get("email", "")).lower(),
                    email_verified=bool(info.get("email_verified")),
                    name=str(info.get("name") or info.get("email", "")).strip(),
                )
            gh = {**auth, "Accept": "application/vnd.github+json"}
            user = http.get("https://api.github.com/user", headers=gh).json()
            emails = http.get("https://api.github.com/user/emails", headers=gh).json()
            primary = next((e for e in emails if e.get("primary")), None) if isinstance(emails, list) else None
            return Identity(
                provider_user_id=str(user.get("id", "")),
                email=str((primary or {}).get("email", "")).lower(),
                email_verified=bool((primary or {}).get("verified")),
                name=str(user.get("name") or user.get("login") or "").strip(),
            )
    except httpx.HTTPError as exc:
        raise OAuthError("provider_unreachable") from exc
