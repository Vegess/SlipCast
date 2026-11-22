"""Build module: the GitHub webhook and pull request, release and deployment metrics."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.services.live import limiter


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


def _iso(hours_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours_ago)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _project(client, u):
    return client.post(
        f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "Repo"}, headers=u["headers"]
    ).json()


def _connect(client, u, pid):
    r = client.post(f"/api/projects/{pid}/github", headers=u["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def _send(client, pid, secret, event, payload, signature=None):
    body = json.dumps(payload).encode()
    sig = signature or "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        f"/api/projects/{pid}/github/webhook",
        content=body,
        headers={"X-GitHub-Event": event, "X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )


REPO = {"full_name": "acme/shop"}


def _pr(n=7, author="mia", **extra):
    return {
        "number": n, "title": f"Add checkout step {n}", "body": "Adds the step", "html_url": f"https://github.com/acme/shop/pull/{n}",
        "user": {"login": author}, "base": {"ref": "main"}, "draft": False,
        "additions": 120, "deletions": 30, "changed_files": 4, "created_at": _iso(30), "updated_at": _iso(30), **extra,
    }  # fmt: skip


def test_connect_is_admin_only_and_secret_is_hidden_from_others(client, make_user):
    alice, vic = make_user("alice@example.com", "Alice"), make_user("vic@example.com", "Vic")
    token = (
        client.post(
            f"/api/workspaces/{alice['workspace_id']}/invites", json={"role": "member"}, headers=alice["headers"]
        )
        .json()["url"]
        .rsplit("/", 1)[1]
    )
    client.post(f"/api/invites/{token}/accept", headers=vic["headers"])
    pid = _project(client, alice)["id"]

    assert client.get(f"/api/projects/{pid}/github", headers=alice["headers"]).json()["connected"] is False
    assert client.post(f"/api/projects/{pid}/github", headers=vic["headers"]).status_code == 403
    on = _connect(client, alice, pid)
    assert (
        on["connected"]
        and len(on["secret"]) == 40
        and on["webhook_url"].endswith(f"/api/projects/{pid}/github/webhook")
    )
    seen_by_member = client.get(f"/api/projects/{pid}/github", headers=vic["headers"]).json()
    assert seen_by_member["connected"] and seen_by_member["secret"] is None

    # rotating changes the secret; disconnecting turns the webhook off
    assert _connect(client, alice, pid)["secret"] != on["secret"]
    assert client.delete(f"/api/projects/{pid}/github", headers=alice["headers"]).status_code == 204
    assert _send(client, pid, on["secret"], "ping", {"zen": "hi"}).status_code == 401


def test_deliveries_need_a_valid_signature(client, make_user):
    u = make_user()
    pid = _project(client, u)["id"]
    secret = _connect(client, u, pid)["secret"]
    assert _send(client, pid, secret, "ping", {"repository": REPO}, signature="sha256=deadbeef").status_code == 401
    assert _send(client, pid, "wrong-secret", "ping", {"repository": REPO}).status_code == 401
    r = _send(client, pid, secret, "ping", {"repository": REPO})
    assert r.status_code == 200 and r.json()["ok"]
    status = client.get(f"/api/projects/{pid}/github", headers=u["headers"]).json()
    assert status["repo"] == "acme/shop" and status["last_event_at"]
    # an unrelated event is acknowledged, not an error, so GitHub doesn't mark deliveries failed
    assert "ignored" in _send(client, pid, secret, "star", {"action": "created", "repository": REPO}).json()


def test_pull_request_lifecycle_from_webhooks(client, make_user):
    u = make_user()
    pid = _project(client, u)["id"]
    secret = _connect(client, u, pid)["secret"]
    pr = _pr()
    assert (
        _send(client, pid, secret, "pull_request", {"action": "opened", "pull_request": pr, "repository": REPO}).json()[
            "created"
        ]
        == 1
    )
    # the author commenting on their own PR is not a review
    own = {"action": "submitted", "pull_request": pr, "repository": REPO,
           "review": {"user": {"login": "mia"}, "state": "commented", "submitted_at": _iso(29)}}  # fmt: skip
    assert _send(client, pid, secret, "pull_request_review", own).json()["ignored"]
    review = {"action": "submitted", "pull_request": pr, "repository": REPO,
              "review": {"user": {"login": "arun"}, "state": "approved", "submitted_at": _iso(20)}}  # fmt: skip
    assert _send(client, pid, secret, "pull_request_review", review).json()["updated"] == 1
    merged = {**pr, "merged": True, "merged_at": _iso(18)}
    assert (
        _send(
            client, pid, secret, "pull_request", {"action": "closed", "pull_request": merged, "repository": REPO}
        ).json()["updated"]
        == 1
    )
    # GitHub retries a delivery: nothing changes
    assert (
        _send(
            client, pid, secret, "pull_request", {"action": "closed", "pull_request": merged, "repository": REPO}
        ).json()["duplicates"]
        == 1
    )

    items = client.get(f"/api/projects/{pid}/tasks", params={"types": "all"}, headers=u["headers"]).json()
    assert client.get(f"/api/projects/{pid}/tasks", headers=u["headers"]).json() == []  # not a ticket
    (item,) = items
    assert item["item_type"] == "pr" and item["status"] == "done" and item["stage"] == "pr_merged"
    assert item["attributes"]["size"] == "M" and item["attributes"]["number"] == 7 and item["owner"] == "mia"


def test_releases_and_deployments(client, make_user):
    u = make_user()
    pid = _project(client, u)["id"]
    secret = _connect(client, u, pid)["secret"]
    release_body = {"tag_name": "v1.4.0", "name": "Spring", "published_at": _iso(10), "html_url": "https://x/r"}
    rel = {"action": "published", "repository": REPO, "release": release_body}
    assert _send(client, pid, secret, "release", rel).json()["created"] == 1

    def deploy(i, state, hours_ago, ref="v1.4.0"):
        status = {"state": state, "environment": "production", "created_at": _iso(hours_ago)}
        dep = {"id": i, "ref": ref, "sha": "abc1234", "environment": "production"}
        return {"deployment_status": status, "deployment": dep, "repository": REPO}

    assert "ignored" in _send(client, pid, secret, "deployment_status", deploy(1, "in_progress", 9)).json()
    assert _send(client, pid, secret, "deployment_status", deploy(1, "failure", 9)).json()["created"] == 1
    r = _send(client, pid, secret, "deployment_status", deploy(2, "success", 6)).json()
    assert r["created"] == 1 and r["updated"] == 1  # the deploy, and the release it shipped
    items = client.get(f"/api/projects/{pid}/tasks", params={"types": "all"}, headers=u["headers"]).json()
    release = next(i for i in items if i["item_type"] == "release")
    assert release["stage"] == "deployed" and release["status"] == "done"

    dora = client.get(f"/api/projects/{pid}/analytics/build", headers=u["headers"]).json()["dora"]
    assert dora["source"] == "deployments"
    assert dora["change_failure_rate"]["value"] == 50.0
    assert dora["recovery_time"]["value"] == 3.0  # failed 9 h ago, fixed 6 h ago


def test_build_metrics_on_the_demo(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    b = client.get(f"/api/projects/{pid}/analytics/build", headers=h).json()
    assert b["available"] and b["counts"]["prs"] > 250 and b["counts"]["deploys"] > 50
    assert 0 < b["review"]["median_hours"] < b["review"]["p85_hours"]
    sizes = {c["size"]: c for c in b["sizes"]["classes"]}
    # the demo bakes in "bigger PRs take longer": the model must find it
    assert sizes["S"]["p50_hours"] < sizes["L"]["p50_hours"] < sizes["XL"]["p50_hours"]
    d = b["dora"]
    assert d["source"] == "deployments" and d["deployment_frequency"]["value"] > 1
    assert d["lead_time"]["value"] > 0 and d["change_failure_rate"]["value"] > 0 and d["recovery_time"]["value"] > 0
    assert len(d["weekly"]) == 12 and len(b["review"]["weekly"]) == 12
    # PRs never leak into the ticket forecast or counts
    project = client.get(f"/api/projects/{pid}", headers=h).json()
    assert project["task_count"] == len(client.get(f"/api/projects/{pid}/tasks", headers=h).json())


def test_small_project_says_why_not(client, make_user):
    u = make_user()
    pid = _project(client, u)["id"]
    empty = client.get(f"/api/projects/{pid}/analytics/build", headers=u["headers"]).json()
    assert empty["available"] is False and "Connect GitHub" in empty["reason"]
    secret = _connect(client, u, pid)["secret"]
    for n in (1, 2):
        _send(client, pid, secret, "pull_request", {"action": "opened", "pull_request": _pr(n), "repository": REPO})
    few = client.get(f"/api/projects/{pid}/analytics/build", headers=u["headers"]).json()
    assert few["available"] is False and "Only 2 pull requests" in few["reason"]


def test_without_deployments_lead_time_falls_back_to_merge(client, make_user):
    u = make_user()
    pid = _project(client, u)["id"]
    secret = _connect(client, u, pid)["secret"]
    for n in range(1, 7):
        pr = _pr(n, created_at=_iso(40))
        _send(client, pid, secret, "pull_request", {"action": "opened", "pull_request": pr, "repository": REPO})
        merged = {**pr, "merged": True, "merged_at": _iso(30)}
        _send(client, pid, secret, "pull_request", {"action": "closed", "pull_request": merged, "repository": REPO})
    d = client.get(f"/api/projects/{pid}/analytics/build", headers=u["headers"]).json()["dora"]
    assert d["lead_time"]["value"] == 10.0 and "merged" in d["lead_time"]["note"]
    assert d["change_failure_rate"]["value"] is None and "deployment statuses" in d["change_failure_rate"]["note"]
