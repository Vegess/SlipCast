"""LLM advice layer with a fake LLM (Phase 2D). No test talks to a real API."""

import json

import pytest

from app.services import advisor
from app.services.findings import Finding


class FakeLLM:
    """Returns canned replies and records every prompt it was sent."""

    def __init__(self, reply):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, json_mode: bool = True) -> str:
        self.calls.append((system, user))
        return self.reply(user) if callable(self.reply) else self.reply


@pytest.fixture()
def fake_llm(monkeypatch):
    def install(reply):
        llm = FakeLLM(reply)
        monkeypatch.setattr(advisor, "get_llm", lambda: llm)
        return llm

    return install


FINDINGS = [
    Finding("F1", "overdue", "critical", "11 open tickets are past the due date.", {"count": 11}),
    Finding("F2", "aging", "warning", "2 tickets are older than 11.6 days; the oldest is 20 days.", {"count": 2}),
]


def suggestions(*items) -> str:
    return json.dumps({"suggestions": list(items)})


def test_validator_rejects_invented_numbers():
    allowed = advisor.allowed_numbers(FINDINGS)
    ok = {"title": "Triage the 11 overdue tickets", "action": "Pick 3 to close by Friday.", "finding_ids": ["F1"]}
    assert advisor.validate(ok, FINDINGS, allowed) is None
    rounded = {
        "title": "Swarm on aging work",
        "action": "Anything older than 12 days gets a pair.",
        "finding_ids": ["F2"],
    }
    assert advisor.validate(rounded, FINDINGS, allowed) is None  # 11.6 rounds to 12
    invented = {"title": "Cut scope", "action": "Drop 40% of the backlog.", "finding_ids": ["F1"]}
    assert "40" in advisor.validate(invented, FINDINGS, allowed)
    uncited = {"title": "Do better", "action": "Work harder.", "finding_ids": []}
    assert advisor.validate(uncited, FINDINGS, allowed) == "cites no finding"
    unknown = {"title": "Do better", "action": "Work harder.", "finding_ids": ["F9"]}
    assert "F9" in advisor.validate(unknown, FINDINGS, allowed)


def test_endpoint_keeps_grounded_suggestions_and_rejects_invented_numbers(client, demo, fake_llm):
    h, pid = demo["headers"], demo["project_id"]
    first = client.post(f"/api/projects/{pid}/advice", json={}, headers=h).json()
    overdue = next(
        f for f in first["findings"] if f["text"].endswith("past the due date.") or "past the due" in f["text"]
    )
    count = overdue["text"].split()[0]
    fake_llm(
        suggestions(
            {
                "title": "Triage overdue work",
                "action": f"Re-plan the {count} overdue tickets.",
                "finding_ids": [overdue["id"]],
            },
            {"title": "Hire 37 contractors", "action": "Scale up fast.", "finding_ids": [overdue["id"]]},
            {"title": "Celebrate", "action": "Team lunch.", "finding_ids": []},
        )
    )
    a = client.post(f"/api/projects/{pid}/advice", json={}, headers=h).json()
    assert a["provider"] == "groq" and a["error"] is None
    assert [s["title"] for s in a["suggestions"]] == ["Triage overdue work"]
    assert a["suggestions"][0]["source"] == "llm"
    assert a["validation"] == {
        "generated": 3,
        "accepted": 1,
        "rejected": 2,
        "problems": a["validation"]["problems"],
    }
    assert any("37" in p for p in a["validation"]["problems"])
    ev = client.get(f"/api/projects/{pid}/analytics/evaluation", headers=h).json()["advice"]
    assert ev["generated"] == 3 and ev["accepted"] == 1 and ev["grounding_pass_rate"] == pytest.approx(1 / 3, abs=0.001)


@pytest.mark.parametrize("reply", ["not json at all", json.dumps({"suggestions": "nope"}), suggestions()])
def test_fallback_runs_on_bad_output(client, demo, fake_llm, reply):
    h, pid = demo["headers"], demo["project_id"]
    fake_llm(reply)
    a = client.post(f"/api/projects/{pid}/advice", json={}, headers=h).json()
    assert a["provider"] == "rules" and a["error"]
    assert 3 <= len(a["suggestions"]) <= 5
    ids = {f["id"] for f in a["findings"]}
    assert all(s["source"] == "rules" and set(s["finding_ids"]) <= ids for s in a["suggestions"])


def test_without_a_key_rules_are_used(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    a = client.post(f"/api/projects/{pid}/advice", json={}, headers=h).json()
    assert a["provider"] == "rules" and a["validation"] is None and a["error"] is None
    assert 3 <= len(a["suggestions"]) <= 5
    allowed = advisor.allowed_numbers([Finding(f["id"], f["kind"], f["severity"], f["text"]) for f in a["findings"]])
    for s in a["suggestions"]:  # rule-based advice passes the same grounding check
        assert advisor.validate(s, [Finding(f["id"], "", "", f["text"]) for f in a["findings"]], allowed) is None


def test_privacy_mode_never_sends_ticket_text_to_the_llm(client, demo, fake_llm):
    h, pid = demo["headers"], demo["project_id"]
    tasks = client.get(f"/api/projects/{pid}/tasks", headers=h).json()
    themes = [t["name"] for t in client.get(f"/api/projects/{pid}/analytics/text", headers=h).json()["topics"]["items"]]
    llm = fake_llm(suggestions())

    r = client.post(
        f"/api/projects/{pid}/rewrite",
        json={"title": "Fix stuff", "description": "Customer complained", "kind": "bug", "privacy_mode": True},
        headers=h,
    ).json()
    assert r["provider"] == "template" and "Steps to reproduce" in r["description"]
    assert llm.calls == [], "privacy mode rewrites never call the LLM"

    advice = client.post(f"/api/projects/{pid}/advice", json={"privacy_mode": True}, headers=h).json()
    client.post(f"/api/projects/{pid}/status-report", json={"privacy_mode": True}, headers=h)
    sent = " ".join(user for _, user in llm.calls) + " ".join(f["text"] for f in advice["findings"])
    assert llm.calls, "aggregate findings may still be summarised"
    for t in tasks:
        assert t["title"] not in sent
    for name in themes:
        assert name not in sent


def test_rewrite_uses_llm_outside_privacy_mode_and_falls_back(client, demo, fake_llm):
    h, pid = demo["headers"], demo["project_id"]
    body = {"title": "Fix stuff", "description": "", "kind": "feature"}
    fake_llm(json.dumps({"title": "Clarified title for the export", "description": "Acceptance criteria:\n- [ ] x"}))
    assert client.post(f"/api/projects/{pid}/rewrite", json=body, headers=h).json()["provider"] == "groq"
    fake_llm("garbage")
    r = client.post(f"/api/projects/{pid}/rewrite", json=body, headers=h).json()
    assert r["provider"] == "template" and "Acceptance criteria" in r["description"]


def test_status_report_rejects_invented_numbers(client, demo, fake_llm):
    h, pid = demo["headers"], demo["project_id"]
    fake_llm("## Summary\nWe shipped 999 tickets.")
    r = client.post(f"/api/projects/{pid}/status-report", json={}, headers=h).json()
    assert r["provider"] == "template" and r["report"].startswith("# Atlas Billing (demo): weekly status")
    fake_llm("## Summary\nDelivery is steady.\n\n## Risks\n- Overdue work needs triage.")
    r = client.post(f"/api/projects/{pid}/status-report", json={}, headers=h).json()
    assert r["provider"] == "groq" and "Delivery is steady" in r["report"]


def test_rate_limit_falls_back_to_rules(client, demo, fake_llm):
    h, pid = demo["headers"], demo["project_id"]
    llm = fake_llm(suggestions())
    for _ in range(6):
        client.post(f"/api/projects/{pid}/advice", json={}, headers=h)
    assert len(llm.calls) == 6
    seventh = client.post(f"/api/projects/{pid}/advice", json={}, headers=h).json()
    assert len(llm.calls) == 6 and "6 requests a minute" in seventh["error"]
    assert seventh["provider"] == "rules" and seventh["suggestions"]


def test_feedback_is_stored_and_summarised(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    a = client.post(f"/api/projects/{pid}/advice", json={}, headers=h).json()
    s1, s2 = a["suggestions"][:2]
    url = f"/api/projects/{pid}/feedback"
    assert (
        client.post(url, json={"suggestion_key": s1["key"], "source": "rules", "helpful": False}, headers=h).status_code
        == 204
    )
    client.post(url, json={"suggestion_key": s1["key"], "source": "rules", "helpful": True}, headers=h)  # changed mind
    client.post(url, json={"suggestion_key": s2["key"], "source": "rules", "helpful": False}, headers=h)
    fb = client.get(f"/api/projects/{pid}/analytics/evaluation", headers=h).json()["advice"]["feedback"]["rules"]
    assert fb == {"helpful": 1, "not_helpful": 1, "helpful_rate": 0.5}
    again = client.post(f"/api/projects/{pid}/advice", json={}, headers=h).json()
    assert again["feedback"] == {s1["key"]: True, s2["key"]: False}
    bad = client.post(url, json={"suggestion_key": "x", "source": "gpt", "helpful": True}, headers=h)
    assert bad.status_code == 422


def test_small_project_advice_does_not_crash(client, make_user):
    u = make_user()
    p = client.post(f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "New"}, headers=u["headers"]).json()
    a = client.post(f"/api/projects/{p['id']}/advice", json={}, headers=u["headers"]).json()
    assert a["findings"] == [] and a["suggestions"] == []
    r = client.post(f"/api/projects/{p['id']}/status-report", json={}, headers=u["headers"]).json()
    assert "No significant risks" in r["report"]
