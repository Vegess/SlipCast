"""Tenant isolation: one user must never read or change another user's data."""


def test_cross_tenant_access_is_denied(client, make_user):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")

    p = client.post(
        f"/api/workspaces/{alice['workspace_id']}/projects",
        json={"name": "Secret roadmap"},
        headers=alice["headers"],
    ).json()
    t = client.post(
        f"/api/projects/{p['id']}/tasks",
        json={"title": "Private task"},
        headers=alice["headers"],
    ).json()

    bh = bob["headers"]
    assert client.get(f"/api/workspaces/{alice['workspace_id']}/projects", headers=bh).status_code == 404
    assert (
        client.post(
            f"/api/workspaces/{alice['workspace_id']}/projects",
            json={"name": "Injected"},
            headers=bh,
        ).status_code
        == 404
    )
    assert client.get(f"/api/projects/{p['id']}", headers=bh).status_code == 404
    assert client.get(f"/api/projects/{p['id']}/tasks", headers=bh).status_code == 404
    assert client.post(f"/api/projects/{p['id']}/tasks", json={"title": "x"}, headers=bh).status_code == 404
    assert client.patch(f"/api/tasks/{t['id']}", json={"title": "pwned"}, headers=bh).status_code == 404
    assert client.delete(f"/api/tasks/{t['id']}", headers=bh).status_code == 404
    assert client.get(f"/api/projects/{p['id']}/insights", headers=bh).status_code == 404
    for path in ("overview", "flow", "forecast", "text", "risk", "evaluation"):
        assert client.get(f"/api/projects/{p['id']}/analytics/{path}", headers=bh).status_code == 404
    assert client.get(f"/api/projects/{p['id']}/forecast-ledger", headers=bh).status_code == 404
    assert client.get(f"/api/tasks/{t['id']}/reference-class", headers=bh).status_code == 404
    assert client.get(f"/api/tasks/{t['id']}/analysis", headers=bh).status_code == 404
    for path in ("advice", "status-report", "rewrite"):
        assert client.post(f"/api/projects/{p['id']}/{path}", json={}, headers=bh).status_code == 404
    assert client.get(f"/api/projects/{p['id']}/export.xlsx", headers=bh).status_code == 404
    assert client.get(f"/api/projects/{p['id']}/export/bi.zip", headers=bh).status_code == 404
    vote = {"suggestion_key": "k", "source": "rules", "helpful": True}
    assert client.post(f"/api/projects/{p['id']}/feedback", json=vote, headers=bh).status_code == 404
    assert client.post(f"/api/projects/{p['id']}/reference-class", json={"title": "x"}, headers=bh).status_code == 404
    assert client.post(f"/api/projects/{p['id']}/ticket-check", json={"title": "x"}, headers=bh).status_code == 404
    assert client.post(f"/api/workspaces/{alice['workspace_id']}/demo-project", headers=bh).status_code == 404
    # Control Room
    assert client.get(f"/api/workspaces/{alice['workspace_id']}/control-room", headers=bh).status_code == 404
    assert client.post(f"/api/workspaces/{alice['workspace_id']}/stream-token", headers=bh).status_code == 404
    assert (
        client.post(
            f"/api/workspaces/{alice['workspace_id']}/import",
            files={"file": ("x.csv", b"Summary\nA\n", "text/csv")},
            headers=bh,
        ).status_code
        == 404
    )
    assert client.get(f"/api/workspaces/{alice['workspace_id']}/imports", headers=bh).status_code == 404
    assert client.delete(f"/api/projects/{p['id']}", headers=bh).status_code == 404
    ws, alice_id = alice["workspace_id"], alice["user"]["id"]
    assert client.get(f"/api/workspaces/{ws}/members", headers=bh).status_code == 404
    assert (
        client.patch(f"/api/workspaces/{ws}/members/{alice_id}", json={"role": "viewer"}, headers=bh).status_code == 404
    )
    assert client.delete(f"/api/workspaces/{ws}/members/{alice_id}", headers=bh).status_code == 404
    assert client.post(f"/api/workspaces/{ws}/invites", json={"role": "admin"}, headers=bh).status_code == 404
    assert client.get(f"/api/workspaces/{ws}/invites", headers=bh).status_code == 404
    invite = client.post(f"/api/workspaces/{ws}/invites", json={"role": "viewer"}, headers=alice["headers"]).json()
    assert client.delete(f"/api/workspaces/{ws}/invites/{invite['id']}", headers=bh).status_code == 404
    bob_invite = client.post(
        f"/api/workspaces/{bob['workspace_id']}/invites", json={"role": "viewer"}, headers=bh
    ).json()
    # real-time endpoints
    pid = p["id"]
    assert client.get(f"/api/projects/{pid}/stages", headers=bh).status_code == 404
    assert client.post(f"/api/projects/{pid}/api-keys", json={"name": "x"}, headers=bh).status_code == 404
    assert client.get(f"/api/projects/{pid}/api-keys", headers=bh).status_code == 404
    alice_key = client.post(f"/api/projects/{pid}/api-keys", json={"name": "x"}, headers=alice["headers"]).json()
    assert client.delete(f"/api/projects/{pid}/api-keys/{alice_key['id']}", headers=bh).status_code == 404
    assert client.post(f"/api/projects/{pid}/stream-token", headers=bh).status_code == 404
    assert client.get(f"/api/projects/{pid}/alerts", headers=bh).status_code == 404
    assert client.get(f"/api/workspaces/{ws}/alerts", headers=bh).status_code == 404
    # Build module
    assert client.get(f"/api/projects/{pid}/github", headers=bh).status_code == 404
    assert client.post(f"/api/projects/{pid}/github", headers=bh).status_code == 404
    assert client.delete(f"/api/projects/{pid}/github", headers=bh).status_code == 404
    assert client.get(f"/api/projects/{pid}/analytics/build", headers=bh).status_code == 404
    # Ship module
    assert client.get(f"/api/projects/{pid}/analytics/ship", headers=bh).status_code == 404
    est = {"origin": "Chennai", "destination": "Delhi", "carrier": "A"}
    assert client.post(f"/api/projects/{pid}/ship/estimate", json=est, headers=bh).status_code == 404
    # Serve module
    assert client.get(f"/api/projects/{pid}/analytics/serve", headers=bh).status_code == 404
    job = {"service_type": "AC repair", "technician": "Deepa"}
    assert client.post(f"/api/projects/{pid}/serve/estimate", json=job, headers=bh).status_code == 404
    assert client.get(f"/api/projects/{pid}/tasks", params={"types": "all"}, headers=bh).status_code == 404
    bob_project = client.post(f"/api/workspaces/{bob['workspace_id']}/projects", json={"name": "B"}, headers=bh).json()
    bob_secret = client.post(f"/api/projects/{bob_project['id']}/github", headers=bh).json()["secret"]
    import hashlib
    import hmac

    body = b'{"zen": "x"}'
    sig = "sha256=" + hmac.new(bob_secret.encode(), body, hashlib.sha256).hexdigest()
    hook = f"/api/projects/{pid}/github/webhook"  # Bob's valid signature, Alice's project
    assert (
        client.post(hook, content=body, headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": sig}).status_code
        == 401
    )
    # an invite id from Bob's workspace can't be used to delete through Alice's, or vice versa
    assert (
        client.delete(f"/api/workspaces/{ws}/invites/{bob_invite['id']}", headers=alice["headers"]).status_code == 404
    )

    # Alice's data is untouched
    tasks = client.get(f"/api/projects/{p['id']}/tasks", headers=alice["headers"]).json()
    assert tasks[0]["title"] == "Private task"
