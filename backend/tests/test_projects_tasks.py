def _project(client, u, name="Billing v2"):
    r = client.post(
        f"/api/workspaces/{u['workspace_id']}/projects",
        json={"name": name, "goal": "Ship usage-based billing"},
        headers=u["headers"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_project_crud(client, make_user):
    u = make_user()
    p = _project(client, u)
    listed = client.get(f"/api/workspaces/{u['workspace_id']}/projects", headers=u["headers"])
    assert [x["name"] for x in listed.json()] == ["Billing v2"]

    r = client.patch(f"/api/projects/{p['id']}", json={"name": "Billing v3"}, headers=u["headers"])
    assert r.json()["name"] == "Billing v3"

    assert client.delete(f"/api/projects/{p['id']}", headers=u["headers"]).status_code == 204
    assert client.get(f"/api/projects/{p['id']}", headers=u["headers"]).status_code == 404


def test_task_lifecycle_and_counts(client, make_user):
    u = make_user()
    p = _project(client, u)
    h = u["headers"]
    t1 = client.post(f"/api/projects/{p['id']}/tasks", json={"title": "Design pricing page"}, headers=h).json()
    t2 = client.post(
        f"/api/projects/{p['id']}/tasks",
        json={"title": "Meter API calls", "due": "2030-01-01", "priority": "high"},
        headers=h,
    ).json()
    assert (t1["position"], t2["position"]) == (0, 1)

    r = client.patch(f"/api/tasks/{t1['id']}", json={"status": "done"}, headers=h)
    assert r.json()["status"] == "done"

    r = client.patch(f"/api/tasks/{t2['id']}", json={"due": None}, headers=h)
    assert r.json()["due"] is None

    proj = client.get(f"/api/projects/{p['id']}", headers=h).json()
    assert (proj["task_count"], proj["done_count"]) == (2, 1)

    bad = client.patch(f"/api/tasks/{t1['id']}", json={"status": "shipped"}, headers=h)
    assert bad.status_code == 422

    assert client.delete(f"/api/tasks/{t1['id']}", headers=h).status_code == 204
    assert len(client.get(f"/api/projects/{p['id']}/tasks", headers=h).json()) == 1


def test_deleting_project_removes_tasks(client, make_user):
    u = make_user()
    p = _project(client, u)
    t = client.post(f"/api/projects/{p['id']}/tasks", json={"title": "x"}, headers=u["headers"]).json()
    client.delete(f"/api/projects/{p['id']}", headers=u["headers"])
    assert client.patch(f"/api/tasks/{t['id']}", json={"title": "y"}, headers=u["headers"]).status_code == 404
