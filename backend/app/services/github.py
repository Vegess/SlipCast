"""GitHub webhook: verify deliveries and turn them into SlipCast events.

Pull requests move through opened, in review, approved and merged (or closed); releases are
tagged; deployments succeed or fail. Each becomes an ordinary event, so the same engine,
live screens and alerts handle them. Nothing calls GitHub's API: GitHub pushes, we listen.
"""

import hashlib
import hmac
from datetime import datetime

from app.config import get_settings
from app.models import Project
from app.services.ingest import EventIn

EVENTS = ("pull_request", "pull_request_review", "release", "deployment_status")
SIZES = [(10, "XS"), (100, "S"), (400, "M"), (1000, "L")]  # lines changed, upper bounds; above is XL
PRODUCTION = {"production", "prod", "live", "main"}


def secret_for(project: Project) -> str | None:
    """The webhook secret, derived from the server secret, so it is never stored anywhere."""
    if project.github_hook_version is None:
        return None
    msg = f"github-webhook:{project.id}:{project.github_hook_version}".encode()
    return hmac.new(get_settings().jwt_secret.encode(), msg, hashlib.sha256).hexdigest()[:40]


def verify(secret: str, body: bytes, signature: str | None) -> bool:
    """GitHub signs every delivery with HMAC-SHA256 of the raw body: X-Hub-Signature-256."""
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def size_label(lines: int) -> str:
    for limit, label in SIZES:
        if lines < limit:
            return label
    return "XL"


def _ts(value) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _ext(prefix: str, repo: str, key: str) -> str:
    """A stable item id within 64 characters, readable when it fits."""
    ext = f"{prefix}:{repo}#{key}"
    if len(ext) <= 64:
        return ext
    return f"{prefix}:{hashlib.sha1(repo.encode()).hexdigest()[:10]}#{key}"[:64]


def _pr_event(pr: dict, repo: str, stage: str, at) -> EventIn:
    additions, deletions = int(pr.get("additions") or 0), int(pr.get("deletions") or 0)
    attrs = {
        "number": pr.get("number"),
        "url": pr.get("html_url"),
        "author": (pr.get("user") or {}).get("login"),
        "repo": repo,
        "base": (pr.get("base") or {}).get("ref"),
        "draft": bool(pr.get("draft")),
    }
    if "additions" in pr:  # list payloads leave sizes out; never overwrite a known size with zero
        attrs |= {
            "additions": additions,
            "deletions": deletions,
            "changed_files": pr.get("changed_files"),
            "size": size_label(additions + deletions),
        }
    return EventIn(
        external_id=_ext("pr", repo, str(pr.get("number"))),
        stage=stage,
        occurred_at=_ts(at),
        title=str(pr.get("title") or f"PR #{pr.get('number')}")[:140],
        description=str(pr.get("body") or "")[:2000],
        owner=str(attrs["author"] or "")[:40],
        item_type="pr",
        attributes={k: v for k, v in attrs.items() if v is not None},
    )


def to_events(kind: str, payload: dict, release_tags: set[str] | None = None) -> list[EventIn]:
    """Events for one delivery; an empty list means "nothing SlipCast tracks"."""
    repo = str((payload.get("repository") or {}).get("full_name") or "repo")
    action = payload.get("action")

    if kind == "pull_request":
        pr = payload.get("pull_request") or {}
        if action == "opened":
            return [_pr_event(pr, repo, "pr_opened", pr.get("created_at"))]
        if action in ("reopened", "ready_for_review"):
            return [_pr_event(pr, repo, "pr_opened", pr.get("updated_at"))]
        if action == "closed":
            if pr.get("merged"):
                return [_pr_event(pr, repo, "pr_merged", pr.get("merged_at"))]
            return [_pr_event(pr, repo, "pr_closed", pr.get("closed_at"))]
        return []

    if kind == "pull_request_review" and action == "submitted":
        pr, review = payload.get("pull_request") or {}, payload.get("review") or {}
        if (review.get("user") or {}).get("login") == (pr.get("user") or {}).get("login"):
            return []  # authors commenting on their own PR aren't a review
        state = str(review.get("state") or "").lower()
        stage = "pr_approved" if state == "approved" else "pr_in_review"
        return [_pr_event(pr, repo, stage, review.get("submitted_at"))]

    if kind == "release" and action in ("published", "released"):
        rel = payload.get("release") or {}
        tag = str(rel.get("tag_name") or "")
        return [
            EventIn(
                external_id=_ext("release", repo, tag),
                stage="release_tagged",
                occurred_at=_ts(rel.get("published_at") or rel.get("created_at")),
                title=f"Release {tag}"[:140],
                description=str(rel.get("name") or "")[:2000],
                item_type="release",
                attributes={
                    "tag": tag,
                    "url": rel.get("html_url"),
                    "repo": repo,
                    "prerelease": bool(rel.get("prerelease")),
                },
            )
        ]

    if kind == "deployment_status":
        status, dep = payload.get("deployment_status") or {}, payload.get("deployment") or {}
        state = str(status.get("state") or "")
        if state not in ("success", "failure", "error"):
            return []  # queued, pending, in progress: wait for the outcome
        env = str(status.get("environment") or dep.get("environment") or "production")
        ref = str(dep.get("ref") or "")
        at = _ts(status.get("created_at") or status.get("updated_at"))
        stage = "deployed" if state == "success" else "deploy_failed"
        events = [
            EventIn(
                external_id=_ext("deploy", repo, str(dep.get("id"))),
                stage=stage,
                occurred_at=at,
                title=f"Deploy {ref or dep.get('sha', '')[:7]} to {env}"[:140],
                item_type="deploy",
                attributes={
                    "environment": env,
                    "ref": ref,
                    "sha": dep.get("sha"),
                    "repo": repo,
                    "production": env.lower() in PRODUCTION,
                },
            )
        ]
        if state == "success" and release_tags and ref in release_tags:
            events.append(
                EventIn(external_id=_ext("release", repo, ref), stage="deployed", occurred_at=at, item_type="release")
            )
        return events

    return []
