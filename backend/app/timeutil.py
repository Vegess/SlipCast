from datetime import UTC, datetime


def naive_utc(value: datetime | None) -> datetime | None:
    """SQLite drops tz info and Postgres keeps it; analytics works in naive UTC."""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value


def now_utc() -> datetime:
    return datetime.now(UTC)
