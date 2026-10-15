def test_demo_project_has_realistic_history(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    tasks = client.get(f"/api/projects/{pid}/tasks", headers=h).json()
    assert len(tasks) > 400
    statuses = {t["status"] for t in tasks}
    assert statuses >= {"planned", "in_progress", "done"}

    done = [t for t in tasks if t["status"] == "done"]
    assert all(t["completed_at"] and t["started_at"] for t in done)
    assert all(t["completed_at"] >= t["started_at"] >= t["created_at"][:10] for t in done)

    labelled = [t for t in tasks if t["kind_source"] == "label"]
    unlabelled = [t for t in tasks if t["kind_source"] == ""]
    assert labelled and unlabelled, "some tickets are left unlabelled for the classifier"
    assert {t["kind"] for t in labelled} == {"bug", "feature", "tech_debt", "support"}

    project = client.get(f"/api/projects/{pid}", headers=h).json()
    assert project["task_count"] == len(tasks) and project["done_count"] == len(done)


def test_demo_is_deterministic():
    from datetime import datetime

    from app.services.demo_data import generate

    now = datetime(2026, 10, 1, 12)
    a, b = generate(now), generate(now)
    assert [t["title"] for t in a] == [t["title"] for t in b]
    assert all(e[2] <= now for t in a for e in t["events"])
