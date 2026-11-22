"""CSV import for Jira, GitHub Issues and Trello exports, with a data-quality report."""

import io
import re
from collections import Counter

import pandas as pd

ALIASES = {
    "title": ["summary", "title", "name", "card name", "issue", "task"],
    "description": ["description", "body", "details", "card description"],
    "kind": ["issue type", "issuetype", "type", "labels", "label", "work type"],
    "status": ["status", "state", "list", "list name"],
    "owner": ["assignee", "owner", "assigned to", "assignees", "members"],
    "priority": ["priority"],
    "created_at": ["created", "created at", "created_at", "creation date", "date created"],
    "started_at": ["started", "start date", "started at", "in progress date"],
    "completed_at": [
        "resolved",
        "resolution date",
        "closed at",
        "closed_at",
        "completed",
        "done date",
        "date completed",
        "closed",
    ],
    "due": ["due date", "due", "due_date", "due at"],
    "external_id": ["issue key", "key", "issue id", "number", "id", "card id"],
}
MAX_ROWS = 5000
MAX_BYTES = 5 * 1024 * 1024


class ImportError_(ValueError):
    pass


def _norm(name: str) -> str:
    return re.sub(r"[\s_]+", " ", str(name).strip().lower())


def map_columns(columns: list[str]) -> dict[str, str]:
    normed = {_norm(c): c for c in columns}
    mapping = {}
    for field, names in ALIASES.items():
        for n in names:
            if n in normed:
                mapping[field] = normed[n]
                break
    return mapping


def norm_status(v: str) -> str:
    v = _norm(v)
    if v in ("done", "closed", "resolved", "complete", "completed", "released", "shipped"):
        return "done"
    if v in ("blocked", "on hold", "impeded", "waiting"):
        return "blocked"
    if v in (
        "in progress",
        "doing",
        "in review",
        "review",
        "started",
        "in development",
        "qa",
        "testing",
    ):
        return "in_progress"
    return "planned"


def norm_kind(v: str) -> str | None:
    v = _norm(v)
    tokens = set(re.split(r"[,;/| ]+", v))
    if tokens & {"bug", "defect", "incident", "regression"}:
        return "bug"
    if tokens & {"support", "question", "request", "service"} or "service request" in v:
        return "support"
    if tokens & {"debt", "chore", "refactor", "maintenance", "improvement", "task"} or "tech debt" in v:
        return "tech_debt"
    if tokens & {"story", "feature", "enhancement", "epic", "new"}:
        return "feature"
    return None


def norm_priority(v: str) -> str:
    v = _norm(v)
    if any(k in v for k in ("highest", "critical", "blocker", "urgent", "p0", "p1", "high")):
        return "high"
    if any(k in v for k in ("lowest", "low", "minor", "trivial", "p3", "p4")):
        return "low"
    return "medium"


def _dates(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True, format="mixed", dayfirst=False)
    return parsed.dt.tz_convert(None)


def parse_csv(raw: bytes, now: pd.Timestamp) -> tuple[list[dict], dict]:
    if len(raw) > MAX_BYTES:
        raise ImportError_("File is larger than 5 MB. Export fewer columns or rows.")
    try:
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
    except UnicodeDecodeError:
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, encoding="latin-1")
    except Exception as exc:  # pandas raises several parser errors
        raise ImportError_("Couldn't read this file as CSV.") from exc

    mapping = map_columns(list(df.columns))
    if "title" not in mapping:
        raise ImportError_("No title column found. Expected one of: Summary, Title, Name.")
    if len(df) > MAX_ROWS:
        raise ImportError_(f"File has {len(df)} rows; the limit is {MAX_ROWS}.")

    get = lambda f: df[mapping[f]] if f in mapping else pd.Series([""] * len(df))  # noqa: E731
    created = _dates(get("created_at"))
    started = _dates(get("started_at"))
    completed = _dates(get("completed_at"))
    due = _dates(get("due"))

    skipped: Counter[str] = Counter()
    warnings: list[str] = []
    rows: list[dict] = []
    seen: set[str] = set()
    inferred_created = inferred_started = 0

    for i in range(len(df)):
        title = str(get("title").iloc[i]).strip()
        if not title:
            skipped["missing title"] += 1
            continue
        ext = str(get("external_id").iloc[i]).strip()[:64] or None
        if ext and ext in seen:
            skipped["duplicate key"] += 1
            continue
        if ext:
            seen.add(ext)
        status = norm_status(get("status").iloc[i])
        c = created.iloc[i]
        if pd.isna(c):
            c, inferred_created = now, inferred_created + 1
        s = started.iloc[i]
        d = completed.iloc[i]
        if status == "done" and pd.isna(d):
            d = c
        if status != "done":
            d = pd.NaT
        if status in ("in_progress", "blocked", "done") and pd.isna(s):
            s, inferred_started = c, inferred_started + 1
        if not pd.isna(d) and d < c:
            skipped["completed before created"] += 1
            continue
        raw_kind = str(get("kind").iloc[i])
        kind = norm_kind(raw_kind) if raw_kind else None
        rows.append(
            {
                "title": title[:140],
                "description": str(get("description").iloc[i]).strip()[:5000],
                "owner": str(get("owner").iloc[i]).split(",")[0].strip()[:40],
                "priority": norm_priority(get("priority").iloc[i]),
                "status": status,
                "created_at": c.to_pydatetime(),
                "started_at": None if pd.isna(s) else s.to_pydatetime(),
                "completed_at": None if pd.isna(d) else d.to_pydatetime(),
                "due": None if pd.isna(due.iloc[i]) else due.iloc[i].date(),
                "kind": kind,
                "kind_source": "label" if kind else "",
                "external_id": ext,
            }
        )

    if "kind" not in mapping:
        warnings.append("No issue type column: ticket types will be predicted from the text.")
    if "completed_at" not in mapping:
        warnings.append("No resolved/closed date column: cycle times use the created date.")
    if "started_at" not in mapping:
        warnings.append("No start date column: cycle time is measured from creation, so it includes waiting time.")
    if inferred_created:
        warnings.append(f"{inferred_created} rows had no created date; today was used.")
    if "description" not in mapping:
        warnings.append("No description column: text analysis will use titles only.")

    dates = [r["created_at"] for r in rows]
    report = {
        "rows_read": int(len(df)),
        "imported": len(rows),
        "skipped": sum(skipped.values()),
        "skipped_reasons": dict(skipped),
        "columns_mapped": {k: v for k, v in mapping.items()},
        "columns_ignored": [c for c in df.columns if c not in mapping.values()],
        "warnings": warnings,
        "date_range": [min(dates).date().isoformat(), max(dates).date().isoformat()] if dates else None,
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "labelled_types": sum(1 for r in rows if r["kind"]),
    }
    return rows, report


def events_for(row: dict) -> list[tuple[str | None, str, object]]:
    ev = [(None, "planned", row["created_at"])]
    if row["started_at"]:
        ev.append(("planned", "in_progress", row["started_at"]))
    if row["status"] == "blocked":
        ev.append(("in_progress", "blocked", row["started_at"] or row["created_at"]))
    if row["completed_at"]:
        ev.append(("in_progress", "done", row["completed_at"]))
    return ev
