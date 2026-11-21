"""Teams: invite links, roles enforced on every write, and account security."""

from datetime import timedelta

import pytest

from app.models import Invite
from app.timeutil import now_utc


def _invite(client, admin, role):
    r = client.post(f"/api/workspaces/{admin['workspace_id']}/invites", json={"role": role}, headers=admin["headers"])
    assert r.status_code == 201, r.text
    return r.json()["url"].rsplit("/", 1)[1]


def _join(client, admin, person, role):
    token = _invite(client, admin, role)
    r = client.post(f"/api/invites/{token}/accept", headers=person["headers"])
    assert r.status_code == 200, r.text
    assert r.json() == {"id": admin["workspace_id"], "name": "Alice's workspace", "role": role}


@pytest.fixture()
def team(client, make_user):
    """Alice (admin) with a project and a ticket; Mia joins as member, Vic as viewer."""
    alice = make_user("alice@example.com", "Alice")
    mia = make_user("mia@example.com", "Mia")
    vic = make_user("vic@example.com", "Vic")
    _join(client, alice, mia, "member")
    _join(client, alice, vic, "viewer")
    ws = alice["workspace_id"]
    p = client.post(f"/api/workspaces/{ws}/projects", json={"name": "Roadmap"}, headers=alice["headers"]).json()
    t = client.post(f"/api/projects/{p['id']}/tasks", json={"title": "Ship it"}, headers=alice["headers"]).json()
    return {"alice": alice, "mia": mia, "vic": vic, "ws": ws, "pid": p["id"], "tid": t["id"]}


def _writes(client, team, h):
    """Every write a project member can attempt, as (label, status code)."""
    ws, pid, tid = team["ws"], team["pid"], team["tid"]
    vote = {"suggestion_key": "k", "source": "rules", "helpful": True}
    return {
        "create project": client.post(f"/api/workspaces/{ws}/projects", json={"name": "X"}, headers=h).status_code,
        "rename project": client.patch(f"/api/projects/{pid}", json={"name": "Y"}, headers=h).status_code,
        "add ticket": client.post(f"/api/projects/{pid}/tasks", json={"title": "x"}, headers=h).status_code,
        "edit ticket": client.patch(f"/api/tasks/{tid}", json={"title": "z"}, headers=h).status_code,
        "demo data": client.post(f"/api/workspaces/{ws}/demo-project", headers=h).status_code,
        "import": client.post(
            f"/api/workspaces/{ws}/import", files={"file": ("x.csv", b"Summary\nA\n", "text/csv")}, headers=h
        ).status_code,
        "advice vote": client.post(f"/api/projects/{pid}/feedback", json=vote, headers=h).status_code,
    }


def test_viewer_can_read_everything_but_change_nothing(client, team):
    h, pid, ws = team["vic"]["headers"], team["pid"], team["ws"]
    assert client.get(f"/api/workspaces/{ws}/projects", headers=h).status_code == 200
    assert client.get(f"/api/projects/{pid}/tasks", headers=h).json()[0]["title"] == "Ship it"
    assert client.get(f"/api/projects/{pid}/analytics/overview", headers=h).status_code == 200
    assert client.get(f"/api/workspaces/{ws}/members", headers=h).status_code == 200

    codes = _writes(client, team, h)
    assert codes == {k: 403 for k in codes}, codes
    assert client.delete(f"/api/tasks/{team['tid']}", headers=h).status_code == 403
    assert client.delete(f"/api/projects/{pid}", headers=h).status_code == 403
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "x"}, headers=h)
    assert "view-only" in r.json()["detail"]
    # nothing changed
    assert [t["title"] for t in client.get(f"/api/projects/{pid}/tasks", headers=h).json()] == ["Ship it"]


def test_member_edits_work_but_not_admin_actions(client, team):
    h, ws, pid = team["mia"]["headers"], team["ws"], team["pid"]
    codes = _writes(client, team, h)
    assert codes["add ticket"] == 201 and codes["edit ticket"] == 200 and codes["create project"] == 201
    assert codes["advice vote"] == 204
    assert client.delete(f"/api/tasks/{team['tid']}", headers=h).status_code == 204
    # admin-only
    assert client.delete(f"/api/projects/{pid}", headers=h).status_code == 403
    assert client.post(f"/api/workspaces/{ws}/invites", json={"role": "viewer"}, headers=h).status_code == 403
    assert client.get(f"/api/workspaces/{ws}/invites", headers=h).status_code == 403
    vic_id = team["vic"]["user"]["id"]
    assert client.patch(f"/api/workspaces/{ws}/members/{vic_id}", json={"role": "admin"}, headers=h).status_code == 403
    assert client.delete(f"/api/workspaces/{ws}/members/{vic_id}", headers=h).status_code == 403


def test_admin_manages_roles_and_keeps_at_least_one_admin(client, team):
    a, ws = team["alice"], team["ws"]
    vic_id, alice_id = team["vic"]["user"]["id"], a["user"]["id"]
    members = client.get(f"/api/workspaces/{ws}/members", headers=a["headers"]).json()
    assert [(m["name"], m["role"]) for m in members] == [("Alice", "admin"), ("Mia", "member"), ("Vic", "viewer")]
    assert members[0]["is_you"] and not members[1]["is_you"]

    # the only admin can't demote or remove themselves
    r = client.patch(f"/api/workspaces/{ws}/members/{alice_id}", json={"role": "member"}, headers=a["headers"])
    assert r.status_code == 400 and "at least one admin" in r.json()["detail"]
    assert client.delete(f"/api/workspaces/{ws}/members/{alice_id}", headers=a["headers"]).status_code == 400

    # promote Vic: his writes start working
    r = client.patch(f"/api/workspaces/{ws}/members/{vic_id}", json={"role": "member"}, headers=a["headers"])
    assert r.status_code == 200 and r.json()["role"] == "member"
    assert (
        client.post(
            f"/api/projects/{team['pid']}/tasks", json={"title": "y"}, headers=team["vic"]["headers"]
        ).status_code
        == 201
    )
    assert (
        client.patch(f"/api/workspaces/{ws}/members/{vic_id}", json={"role": "boss"}, headers=a["headers"]).status_code
        == 422
    )

    # remove Vic: the workspace disappears for him (404, not 403)
    assert client.delete(f"/api/workspaces/{ws}/members/{vic_id}", headers=a["headers"]).status_code == 204
    assert client.get(f"/api/projects/{team['pid']}", headers=team["vic"]["headers"]).status_code == 404


def test_anyone_can_leave_a_workspace(client, team):
    mia = team["mia"]
    assert (
        client.delete(f"/api/workspaces/{team['ws']}/members/{mia['user']['id']}", headers=mia["headers"]).status_code
        == 204
    )
    me = client.get("/api/auth/me", headers=mia["headers"]).json()
    assert [w["name"] for w in me["workspaces"]] == ["Mia's workspace"]


def test_invite_links_are_single_use_and_expire(client, make_user):
    from app.db import get_db
    from app.main import app

    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    carol = make_user("carol@example.com", "Carol")
    token = _invite(client, alice, "member")

    preview = client.get(f"/api/invites/{token}").json()  # public, before sign-in
    assert preview == {
        "workspace_name": "Alice's workspace",
        "role": "member",
        "invited_by": "Alice",
        "valid": True,
        "reason": "",
    }
    assert client.post(f"/api/invites/{token}/accept").status_code == 401
    assert client.post(f"/api/invites/{token}/accept", headers=bob["headers"]).status_code == 200
    # the link is now used up, even for the person who used it
    assert client.post(f"/api/invites/{token}/accept", headers=bob["headers"]).status_code == 410

    used = client.post(f"/api/invites/{token}/accept", headers=carol["headers"])
    assert used.status_code == 410 and "already been used" in used.json()["detail"]
    assert client.get(f"/api/invites/{token}").json()["valid"] is False
    assert client.get("/api/invites/not-a-real-token").status_code == 404

    # an expired link can't be used
    old = _invite(client, alice, "viewer")
    db = next(app.dependency_overrides[get_db]())
    for inv in db.query(Invite).filter(Invite.used_at.is_(None)).all():
        inv.expires_at = now_utc() - timedelta(minutes=1)
    db.commit()
    r = client.post(f"/api/invites/{old}/accept", headers=carol["headers"])
    assert r.status_code == 410 and "expired" in r.json()["detail"]
    # expired and used links drop out of the admin's list; only the hash is stored
    assert client.get(f"/api/workspaces/{alice['workspace_id']}/invites", headers=alice["headers"]).json() == []
    assert all(len(i.token_hash) == 64 and i.token_hash != old for i in db.query(Invite).all())


def test_already_a_member_keeps_role_and_link_stays_unused(client, make_user):
    alice = make_user("alice@example.com", "Alice")
    token = _invite(client, alice, "viewer")
    r = client.post(f"/api/invites/{token}/accept", headers=alice["headers"])
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert client.get(f"/api/invites/{token}").json()["valid"] is True


def test_admin_can_list_and_revoke_invites(client, make_user):
    alice = make_user("alice@example.com", "Alice")
    ws, h = alice["workspace_id"], alice["headers"]
    token = _invite(client, alice, "member")
    listed = client.get(f"/api/workspaces/{ws}/invites", headers=h).json()
    assert len(listed) == 1 and listed[0]["role"] == "member" and listed[0]["url"] is None
    assert client.delete(f"/api/workspaces/{ws}/invites/{listed[0]['id']}", headers=h).status_code == 204
    assert client.get(f"/api/invites/{token}").status_code == 404


def test_sign_out_everywhere_and_password_change_revoke_old_tokens(client, make_user):
    u = make_user()
    old = u["headers"]
    r = client.post(
        "/api/auth/password", json={"current_password": "wrong", "new_password": "n3w-password"}, headers=old
    )
    assert r.status_code == 400
    r = client.post(
        "/api/auth/password", json={"current_password": "s3cure-pass", "new_password": "n3w-password"}, headers=old
    )
    assert r.status_code == 200
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=old).status_code == 401  # other sessions are signed out
    assert client.get("/api/auth/me", headers=fresh).status_code == 200
    login = client.post("/api/auth/login", json={"email": "anirudh@example.com", "password": "n3w-password"})
    assert login.status_code == 200

    assert client.post("/api/auth/logout-all", headers=fresh).status_code == 204
    assert client.get("/api/auth/me", headers=fresh).status_code == 401


def test_tokens_from_before_versioning_still_work(client, make_user):
    """Accounts created before v1.2 hold tokens without "ver"; they must keep working."""
    import jwt

    from app.config import get_settings

    u = make_user()
    s = get_settings()
    legacy = jwt.encode(
        {"sub": u["user"]["id"], "exp": now_utc() + timedelta(hours=1)}, s.jwt_secret, algorithm=s.jwt_algorithm
    )
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 200
