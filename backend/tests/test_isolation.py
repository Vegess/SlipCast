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
    assert client.post(f"/api/workspaces/{alice['workspace_id']}/demo-project", headers=bh).status_code == 404
    assert (
        client.post(
            f"/api/workspaces/{alice['workspace_id']}/import",
            files={"file": ("x.csv", b"Summary\nA\n", "text/csv")},
            headers=bh,
        ).status_code
        == 404
    )
    assert client.delete(f"/api/projects/{p['id']}", headers=bh).status_code == 404

    # Alice's data is untouched
    tasks = client.get(f"/api/projects/{p['id']}/tasks", headers=alice["headers"]).json()
    assert tasks[0]["title"] == "Private task"
