from datetime import date, timedelta

from app.services.insights import TaskView, analyse

TODAY = date(2026, 10, 14)


def tv(i, status="planned", owner="Priya", priority="medium", due_offset=5):
    due = TODAY + timedelta(days=due_offset) if due_offset is not None else None
    return TaskView(str(i), f"Task {i}", owner, status, priority, due)


def kinds(result):
    return {i.kind for i in result.insights}


def test_empty_project_is_on_track():
    r = analyse([], TODAY)
    assert r.health == "on_track" and r.completion == 0.0


def test_overdue_high_priority_is_critical():
    r = analyse([tv(1, priority="high", due_offset=-2), tv(2, status="done")], TODAY)
    assert r.health == "off_track"
    assert "overdue" in kinds(r)
    assert r.completion == 0.5


def test_done_tasks_are_never_overdue():
    r = analyse([tv(1, status="done", due_offset=-10)], TODAY)
    assert "overdue" not in kinds(r) and r.health == "on_track"


def test_blocked_and_unassigned_are_warnings():
    r = analyse([tv(1, status="blocked"), tv(2, owner="", priority="high")], TODAY)
    assert {"blocked", "unassigned"} <= kinds(r)
    assert r.health == "at_risk"


def test_overload_detected():
    tasks = [tv(i, owner="Arun") for i in range(4)] + [tv(9, owner="Meera")]
    assert "overload" in kinds(analyse(tasks, TODAY))


def test_due_soon_and_undated_are_info():
    r = analyse([tv(1, due_offset=1), tv(2, due_offset=None), tv(3, due_offset=None)], TODAY)
    assert {"due_soon", "undated"} <= kinds(r)
    assert r.health == "on_track"
