"""NLP and ML models and the evaluation endpoint (Phase 2C)."""

from datetime import datetime

import numpy as np
import pandas as pd

from app.services import nlp, risk_model
from app.services.analysis import build_frames


def _small_frame(n: int) -> pd.DataFrame:
    now = datetime(2026, 3, 1)
    rows = [
        (str(i), f"Ticket {i}", "", "", "done", "medium", None, "bug", "label", now, now, now, now) for i in range(n)
    ]
    return build_frames(rows, [])[0]


def test_quality_score_rewards_detail():
    vague, reasons = nlp.quality("Fix stuff", "", "", None)
    assert vague < 20 and any("stuff" in r for r in reasons)
    good, reasons = nlp.quality(
        "Invoice total ignores proration on plan upgrade",
        "Steps to reproduce:\n1. Upgrade a Pro plan mid-cycle\n2. Open the invoice\n\nExpected: prorated total.",
        "Arun",
        "2026-12-01",
    )
    assert good == 100 and reasons == []


def test_classifier_beats_majority_baseline_on_demo(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    c = client.get(f"/api/projects/{pid}/analytics/evaluation", headers=h).json()["classifier"]
    assert c["available"] and c["accuracy"] >= 0.8 and c["accuracy"] > c["baseline"]["accuracy"] + 0.3
    assert c["macro_f1"] > c["baseline"]["macro_f1"]
    assert len(c["confusion_matrix"]) == len(c["labels"]) == 4
    assert sum(map(sum, c["confusion_matrix"])) == c["test_size"]
    assert set(c["top_terms"]) == set(c["labels"]) and c["predicted_unlabeled"] > 0
    assert "train on tickets created before" in c["split"]


def test_classifier_needs_40_labels():
    result = nlp.train_classifier(_small_frame(39))
    assert result["available"] is False and "at least 40" in result["reason"]


def test_themes_on_demo(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    text = client.get(f"/api/projects/{pid}/analytics/text", headers=h).json()
    topics = text["topics"]
    assert topics["available"] and 3 <= len(topics["items"]) <= 8
    assert all(len(t["name"].split(", ")) == 3 for t in topics["items"])
    assert 0 < topics["silhouette"] < 1
    names = " ".join(t["name"] for t in topics["items"])
    assert "invoice" in names or "checkout" in names or "billing" in names
    # flow breakdown by theme becomes available once themes exist
    flow = client.get(f"/api/projects/{pid}/analytics/flow", headers=h).json()
    assert {r["key"] for r in flow["by_topic"]} >= {t["name"] for t in topics["items"]}


def test_themes_need_enough_tickets():
    result = nlp.find_themes(_small_frame(10))
    assert result["available"] is False and result["reason"]


def test_duplicates_list_open_pairs_first(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    dups = client.get(f"/api/projects/{pid}/analytics/text", headers=h).json()["duplicates"]
    assert dups and all(d["similarity"] >= 0.72 for d in dups)
    both_done = [d["a"]["status"] == "done" and d["b"]["status"] == "done" for d in dups]
    assert both_done == sorted(both_done)
    assert any(
        d["a"]["title"].startswith(("Again", "Reported again")) or d["b"]["title"].startswith("Again") for d in dups
    )


def test_owner_load_counts_open_tickets_at_creation():
    t = pd.DataFrame(
        {
            "owner": ["A", "A", "A", "B"],
            "created_at": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-10", "2026-01-03"]),
            "completed_at": pd.to_datetime(["2026-01-05", None, None, None]),
        }
    )
    assert risk_model.owner_load(t).tolist() == [0, 1, 1, 0]


def test_risk_model_beats_chance_and_explains(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    r = client.get(f"/api/projects/{pid}/analytics/evaluation", headers=h).json()["risk"]
    assert r["available"] and r["roc_auc"] > 0.7 and r["roc_auc"] >= r["baseline"]["roc_auc"]
    assert 0 < r["brier"] < 0.25 and r["average_precision"] > r["base_rate"]
    assert r["roc_curve"][0] == [0.0, 0.0] and r["roc_curve"][-1] == [1.0, 1.0]
    assert r["weights"][0]["feature"] == "planned days" and r["weights"][0]["weight"] < 0
    risks = client.get(f"/api/projects/{pid}/analytics/risk", headers=h).json()
    probs = [i["risk"] for i in risks["items"]]
    assert probs == sorted(probs, reverse=True) and all(0 <= p <= 1 for p in probs)
    top = risks["items"][0]
    assert top["factors"], "the riskiest ticket has at least one stated reason"


def test_explanations_skip_absent_binary_features(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    tasks = {t["id"]: t for t in client.get(f"/api/projects/{pid}/tasks", headers=h).json()}
    for item in client.get(f"/api/projects/{pid}/analytics/risk", headers=h).json()["items"]:
        a = client.get(f"/api/tasks/{item['id']}/analysis", headers=h).json()
        for factor in item["factors"]:
            if factor.endswith("tickets often slip"):
                assert factor.startswith(a["kind"].replace("_", " "))
            if factor == "no owner":
                assert tasks[item["id"]]["owner"] == ""


def test_risk_model_small_project_reason():
    t = _small_frame(20)
    model = risk_model.RiskModel(t, pd.Series("bug", index=t.index), pd.Series(80.0, index=t.index))
    assert model.available is False and "at least 60" in model.reason
    assert model.open_risks()["available"] is False and model.evaluation()["available"] is False


def test_ticket_check_includes_slip_risk_once_model_exists(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    body = {"title": "Flaky: Stripe webhook handler fails", "description": "Intermittent, root cause unknown."}
    risky = client.post(f"/api/projects/{pid}/ticket-check", json={**body, "owner": "Arun", "due": _days(2)}, headers=h)
    safe = client.post(
        f"/api/projects/{pid}/ticket-check", json={**body, "owner": "Meera", "due": _days(40)}, headers=h
    )
    assert risky.json()["slip_risk"]["risk"] > safe.json()["slip_risk"]["risk"]
    assert any("short plan" in f for f in risky.json()["slip_risk"]["factors"])
    no_due = client.post(f"/api/projects/{pid}/ticket-check", json=body, headers=h).json()
    assert no_due["slip_risk"] is None  # without a due date nothing can be late


def _days(n: int) -> str:
    from datetime import date, timedelta

    return (date.today() + timedelta(days=n)).isoformat()


def test_backtest_and_overview_numbers(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    e = client.get(f"/api/projects/{pid}/analytics/evaluation", headers=h).json()
    b = e["forecast_backtest"]
    assert b["available"] and len(b["points"]) >= 5 and 0.6 <= b["p85_hit_rate"] <= 1
    assert e["reference_class"]["available"] and e["ledger"]["resolved"] > 0 and "entries" not in e["ledger"]
    assert e["topics"]["available"] and e["topics"]["count"] >= 3
    o = client.get(f"/api/projects/{pid}/analytics/overview", headers=h).json()
    assert isinstance(o["high_risk"], int)


def test_task_analysis(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    unlabelled = next(t for t in client.get(f"/api/projects/{pid}/tasks", headers=h).json() if t["kind_source"] == "")
    a = client.get(f"/api/tasks/{unlabelled['id']}/analysis", headers=h).json()
    assert a["kind"] in nlp.KINDS and a["kind_source"] == "predicted"
    assert 0 <= a["quality"]["score"] <= 100 and a["reference"]["n"] >= 0 and a["theme"]


def test_small_project_model_endpoints(client, make_user):
    u = make_user()
    p = client.post(f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "Tiny"}, headers=u["headers"]).json()
    t = client.post(f"/api/projects/{p['id']}/tasks", json={"title": "Only one"}, headers=u["headers"]).json()
    base = f"/api/projects/{p['id']}/analytics"
    ev = client.get(f"{base}/evaluation", headers=u["headers"]).json()
    for key in ("classifier", "risk", "forecast_backtest", "reference_class"):
        assert ev[key]["available"] is False and ev[key]["reason"], key
    assert client.get(f"{base}/risk", headers=u["headers"]).json()["available"] is False
    text = client.get(f"{base}/text", headers=u["headers"]).json()
    assert text["topics"]["available"] is False and text["duplicates"] == []
    assert client.get(f"/api/tasks/{t['id']}/analysis", headers=u["headers"]).status_code == 200


def test_curves_are_downsampled():
    pts = [(i / 999, i / 999) for i in range(1000)]
    out = risk_model._downsample(pts, 60)
    assert len(out) == 60 and out[0] == [0.0, 0.0] and out[-1] == [1.0, 1.0]
    assert np.all(np.diff([p[0] for p in out]) >= 0)
