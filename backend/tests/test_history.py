def test_status_changes_are_recorded(client, make_user):
    u = make_user()
    h = u["headers"]
    p = client.post(f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "Flow"}, headers=h).json()
    t = client.post(
        f"/api/projects/{p['id']}/tasks",
        json={"title": "Build export", "kind": "feature"},
        headers=h,
    ).json()
    assert t["started_at"] is None and t["kind_source"] == "label"

    t = client.patch(f"/api/tasks/{t['id']}", json={"status": "in_progress"}, headers=h).json()
    assert t["started_at"] and t["completed_at"] is None
    t = client.patch(f"/api/tasks/{t['id']}", json={"status": "done"}, headers=h).json()
    assert t["completed_at"]
    t = client.patch(f"/api/tasks/{t['id']}", json={"status": "in_progress"}, headers=h).json()
    assert t["completed_at"] is None, "reopening clears the completion time"

    from app.db import get_db
    from app.main import app
    from app.models import TaskEvent

    db = next(app.dependency_overrides[get_db]())
    moves = [
        (e.from_status, e.to_status) for e in db.query(TaskEvent).filter_by(task_id=t["id"]).order_by(TaskEvent.at)
    ]
    assert moves == [
        (None, "planned"),
        ("planned", "in_progress"),
        ("in_progress", "done"),
        ("done", "in_progress"),
    ]


def test_same_status_is_not_an_event(client, make_user):
    u = make_user()
    p = client.post(f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "X"}, headers=u["headers"]).json()
    t = client.post(f"/api/projects/{p['id']}/tasks", json={"title": "A"}, headers=u["headers"]).json()
    r = client.patch(f"/api/tasks/{t['id']}", json={"status": "planned", "title": "B"}, headers=u["headers"])
    assert r.json()["title"] == "B" and r.json()["started_at"] is None
