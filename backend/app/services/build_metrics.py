"""Build module metrics from pull requests, releases and deployments.

- Review wait: how long a pull request waits for its first review.
- Size classes: how long pull requests of each size took to merge, so an open one gets a
  reference-class range ("PRs this size took 6-30 hours").
- DORA: deployment frequency, lead time for changes, change failure rate and failed-deployment
  recovery time, over the last 4 weeks against the 4 before.

Stage times come from the event log, because a PR's stages (opened, in review, approved) all
count as "in progress" for the forecast and so never appear in the status history.
"""

from bisect import bisect_left
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BUILD_TYPES, IngestedEvent, Task
from app.services.github import SIZES
from app.timeutil import naive_utc

MIN_PRS = 5
MIN_CLASS = 5
WINDOW = timedelta(days=28)
SIZE_ORDER = [label for _, label in SIZES] + ["XL"]
SIZE_RANGE = {
    "XS": "under 10 lines",
    "S": "10-99 lines",
    "M": "100-399 lines",
    "L": "400-999 lines",
    "XL": "1,000+ lines",
}


def _h(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600


def _pct(values: list[float], q: float) -> float | None:
    return round(float(np.percentile(values, q)), 1) if values else None


def _metric(value, previous, unit: str, note: str = "") -> dict:
    return {"value": value, "previous": previous, "unit": unit, "note": note}


def compute(db: Session, project_id: str, now: datetime) -> dict:
    now = naive_utc(now)
    items = db.execute(
        select(Task.external_id, Task.item_type, Task.title, Task.owner, Task.attributes, Task.created_at).where(
            Task.project_id == project_id, Task.item_type.in_(BUILD_TYPES)
        )
    ).all()
    if not items:
        return {
            "available": False,
            "reason": "No pull requests, releases or deployments yet. Connect GitHub on the Live feed tab "
            "and they'll appear here as they happen.",
        }
    timeline: dict[str, dict[str, datetime]] = {}
    for ext, stage, at in db.execute(
        select(IngestedEvent.external_id, IngestedEvent.stage, IngestedEvent.occurred_at).where(
            IngestedEvent.project_id == project_id
        )
    ):
        at = naive_utc(at)
        stages = timeline.setdefault(ext, {})
        if stage not in stages or at < stages[stage]:
            stages[stage] = at  # first time each stage was reached

    prs, deploys, releases = [], [], []
    for ext, kind, title, owner, attrs, created in items:
        tl, attrs = timeline.get(ext, {}), attrs or {}
        if kind == "pr":
            reviews = [tl[s] for s in ("pr_in_review", "pr_approved") if s in tl]
            prs.append({
                "title": title, "author": owner or attrs.get("author") or "", "number": attrs.get("number"),
                "url": attrs.get("url"), "size": attrs.get("size"),
                "lines": int(attrs.get("additions", 0) or 0) + int(attrs.get("deletions", 0) or 0),
                "opened": tl.get("pr_opened") or naive_utc(created), "review": min(reviews) if reviews else None,
                "merged": tl.get("pr_merged"), "closed": tl.get("pr_closed"),
            })  # fmt: skip
        elif kind == "deploy":
            ok, failed = tl.get("deployed"), tl.get("deploy_failed")
            if ok or failed:
                deploys.append({"at": ok or failed, "ok": ok is not None, "production": attrs.get("production", True)})
        elif kind == "release" and tl.get("release_tagged"):
            releases.append(tl["release_tagged"])

    if len(prs) < MIN_PRS and not deploys and not releases:
        return {
            "available": False,
            "reason": f"Only {len(prs)} pull request{'s' if len(prs) != 1 else ''} so far; "
            f"review and delivery numbers need at least {MIN_PRS}.",
        }
    return {
        "available": True,
        "reason": "",
        "counts": {"prs": len(prs), "deploys": len(deploys), "releases": len(releases)},
        "review": _review(prs, now),
        "sizes": _sizes(prs, now),
        "dora": _dora(prs, deploys, releases, now),
    }


def _review(prs: list[dict], now: datetime) -> dict:
    waits = [(p["review"], _h(p["opened"], p["review"])) for p in prs if p["review"] and p["review"] >= p["opened"]]
    hours = [w for _, w in waits]
    weeks = []
    for i in range(11, -1, -1):
        end = now - timedelta(weeks=i)
        chunk = [w for at, w in waits if end - timedelta(weeks=1) <= at < end]
        start = (end - timedelta(weeks=1)).date().isoformat()
        weeks.append({"week": start, "median": _pct(chunk, 50), "n": len(chunk)})
    waiting = sorted(
        (p for p in prs if not p["merged"] and not p["closed"] and not p["review"]), key=lambda p: p["opened"]
    )
    return {
        "median_hours": _pct(hours, 50),
        "p85_hours": _pct(hours, 85),
        "reviewed": len(hours),
        "weekly": weeks,
        "waiting": [
            {
                "title": p["title"],
                "author": p["author"],
                "number": p["number"],
                "url": p["url"],
                "size": p["size"],
                "age_hours": round(_h(p["opened"], now), 1),
            }
            for p in waiting[:8]
        ],  # fmt: skip
        "waiting_count": len(waiting),
    }


def _sizes(prs: list[dict], now: datetime) -> dict:
    classes, by_label = [], {}
    for label in SIZE_ORDER:
        hours = [_h(p["opened"], p["merged"]) for p in prs if p["size"] == label and p["merged"]]
        enough = len(hours) >= MIN_CLASS
        row = {
            "size": label, "lines": SIZE_RANGE[label], "n": len(hours),
            "p50_hours": _pct(hours, 50) if enough else None, "p85_hours": _pct(hours, 85) if enough else None,
        }  # fmt: skip
        classes.append(row)
        by_label[label] = row
    open_prs = []
    for p in sorted((p for p in prs if not p["merged"] and not p["closed"]), key=lambda p: p["opened"]):
        ref = by_label.get(p["size"] or "")
        open_prs.append({
            "title": p["title"], "number": p["number"], "url": p["url"], "size": p["size"], "author": p["author"],
            "age_hours": round(_h(p["opened"], now), 1),
            "expected": [ref["p50_hours"], ref["p85_hours"]] if ref and ref["p50_hours"] is not None else None,
        })  # fmt: skip
    return {"classes": classes, "open": open_prs[:10], "open_count": len(open_prs)}


def _dora(prs: list[dict], deploys: list[dict], releases: list[datetime], now: datetime) -> dict:
    prod = [d for d in deploys if d["production"]] or deploys
    using_releases = not prod
    successes = sorted(d["at"] for d in prod if d["ok"]) if prod else sorted(releases)
    failures = sorted(d["at"] for d in prod if not d["ok"])
    cur, prev = (now - WINDOW, now), (now - 2 * WINDOW, now - WINDOW)

    def inside(times, span):
        return [t for t in times if span[0] <= t < span[1]]

    def lead(span):
        out = []
        for p in prs:
            if not p["merged"] or not span[0] <= p["merged"] < span[1]:
                continue
            if successes:  # time until the change was actually running (or released)
                i = bisect_left(successes, p["merged"])
                if i < len(successes):
                    out.append(_h(p["opened"], successes[i]))
            else:  # nothing ships through SlipCast yet: merged is the best we know
                out.append(_h(p["opened"], p["merged"]))
        return _pct(out, 50)

    def failure_rate(span):
        ok, bad = len(inside(successes, span)), len(inside(failures, span))
        return round(100 * bad / (ok + bad), 1) if ok + bad else None

    def recovery(span):
        out = []
        for f in inside(failures, span):
            i = bisect_left(successes, f)
            if i < len(successes):
                out.append(_h(f, successes[i]))
        return _pct(out, 50)

    weekly = []
    for i in range(11, -1, -1):
        end = now - timedelta(weeks=i)
        weekly.append({
            "week": (end - timedelta(weeks=1)).date().isoformat(),
            "ok": len(inside(successes, (end - timedelta(weeks=1), end))),
            "failed": len(inside(failures, (end - timedelta(weeks=1), end))),
        })  # fmt: skip
    source = "releases" if using_releases else "deployments"
    has_deploys = bool(prod)
    no_deploy_note = "Needs deployment statuses from GitHub (Actions environments or another deploy tool)."
    if has_deploys:
        lead_note = "From PR opened to the next successful deployment."
    elif successes:
        lead_note = "From PR opened to the next release."
    else:
        lead_note = "From PR opened to merged (no deployments yet)."
    return {
        "source": source,
        "deployment_frequency": _metric(
            round(len(inside(successes, cur)) / 4, 1),
            round(len(inside(successes, prev)) / 4, 1),
            "per_week",
            "Counting releases, because no deployments have been reported yet." if using_releases else "",
        ),
        "lead_time": _metric(lead(cur), lead(prev), "hours", lead_note),
        "change_failure_rate": _metric(
            failure_rate(cur), failure_rate(prev), "percent", "" if has_deploys else no_deploy_note
        ),
        "recovery_time": _metric(
            recovery(cur),
            recovery(prev),
            "hours",
            "From a failed deployment to the next successful one." if has_deploys else no_deploy_note,
        ),
        "weekly": weekly,
    }
