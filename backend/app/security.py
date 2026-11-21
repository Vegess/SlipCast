from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:  # accounts that only use Google or GitHub have no password
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, version: int = 0) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "ver": version,  # must match users.token_version; bumping it signs out every session
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> tuple[str, int] | None:
    """Returns (user_id, token version), or None for an invalid or expired token.
    Tokens issued before versioning carry no "ver" and count as version 0."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose"):  # short-lived OAuth state tokens are never access tokens
        return None
    sub, ver = payload.get("sub"), payload.get("ver", 0)
    if not isinstance(sub, str) or not isinstance(ver, int):
        return None
    return sub, ver


def create_signed(payload: dict, minutes: int) -> str:
    """A short-lived signed blob for one purpose (e.g. OAuth state), never usable as a login."""
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {**payload, "iat": now, "exp": now + timedelta(minutes=minutes)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def read_signed(token: str, purpose: str) -> dict | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    return payload if payload.get("purpose") == purpose else None
