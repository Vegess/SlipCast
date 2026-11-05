"""Slip-risk model: will a ticket finish after its due date?

Logistic regression on features known when the ticket is created, so it can score a
ticket before work starts. Per-ticket explanations are coefficient x standardised
value: the features pushing this ticket's risk up the most.
"""

import re

import numpy as np
import pandas as pd

from app.services import nlp

MIN_ROWS = 60
MIN_CLASS = 8
HIGH_RISK = 0.6
RISKY = re.compile(
    r"\b(flaky|intermittent(ly)?|investigate|unknown|migrat\w*|legacy|refactor\w*|race condition|time[sd]? out|"
    r"timeout|deadlock|root cause|upgrade|sometimes|random(ly)?)\b",
    re.IGNORECASE,
)
NUMERIC = ["planned_days", "owner_load", "description_length", "risky_terms", "quality", "unassigned"]
PRIORITY = ["priority_high", "priority_low"]
KIND_COLS = [f"kind_{k}" for k in nlp.KINDS]
FEATURES = NUMERIC + PRIORITY + KIND_COLS
BINARY = {"unassigned", *PRIORITY, *KIND_COLS}
LABELS = {
    "planned_days": "planned days",
    "owner_load": "owner's open tickets at creation",
    "description_length": "description length (log)",
    "risky_terms": "risky words (flaky, legacy, migrate…)",
    "quality": "quality score",
    "unassigned": "no owner",
    "priority_high": "high priority",
    "priority_low": "low priority",
    **{f"kind_{k}": f"type: {k.replace('_', ' ')}" for k in nlp.KINDS},
}


def owner_load(tickets: pd.DataFrame) -> np.ndarray:
    """For each ticket, how many other tickets its owner had open when it was created."""
    load = np.zeros(len(tickets))
    created = tickets["created_at"].to_numpy(dtype="datetime64[ns]")
    done = tickets["completed_at"].to_numpy(dtype="datetime64[ns]")
    done = np.where(np.isnat(done), np.datetime64("2262-01-01"), done)
    for owner, idx in tickets.groupby("owner").indices.items():
        if not owner:
            continue
        c, d = created[idx], done[idx]
        open_at = (c[None, :] < c[:, None]) & (d[None, :] > c[:, None])
        load[idx] = open_at.sum(axis=1)
    return load


def features(tickets: pd.DataFrame, kinds: pd.Series, quality: pd.Series, load: np.ndarray) -> pd.DataFrame:
    text = tickets["title"] + " " + tickets["description"]
    x = pd.DataFrame(index=tickets.index)
    x["planned_days"] = tickets["planned_days"].clip(lower=0, upper=60)
    x["owner_load"] = load
    x["description_length"] = np.log1p(tickets["description"].str.len())
    x["risky_terms"] = text.map(lambda s: len(RISKY.findall(s)))
    x["quality"] = quality
    x["unassigned"] = (tickets["owner"] == "").astype(float)
    x["priority_high"] = (tickets["priority"] == "high").astype(float)
    x["priority_low"] = (tickets["priority"] == "low").astype(float)
    for k in nlp.KINDS:
        x[f"kind_{k}"] = (kinds == k).astype(float)
    return x[FEATURES].astype(float)


def _pipeline():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))


def _factor_text(feature: str, value: float, owner: str) -> str:
    if feature == "planned_days":
        return f"short plan ({value:.0f} day{'s' if value != 1 else ''})"
    if feature == "owner_load":
        return f"{owner or 'owner'} already had {value:.0f} open tickets"
    if feature == "description_length":
        return "short description"
    if feature == "risky_terms":
        return "risky wording (flaky, legacy, migrate…)"
    if feature == "quality":
        return f"low quality score ({value:.0f}/100)"
    if feature == "unassigned":
        return "no owner"
    if feature.startswith("priority_"):
        return f"{feature.split('_')[1]} priority"
    return f"{feature.removeprefix('kind_').replace('_', ' ')} tickets often slip"


def explain(model, row: pd.Series, owner: str, top: int = 3) -> list[str]:
    scaler, lr = model.steps[0][1], model.steps[1][1]
    z = (row.to_numpy(dtype=float) - scaler.mean_) / np.where(scaler.scale_ == 0, 1, scaler.scale_)
    contrib = lr.coef_[0] * z
    # A binary feature that is absent ("not a bug") is not a reason to show anyone.
    present = np.array([f not in BINARY or row.iloc[i] > 0 for i, f in enumerate(FEATURES)])
    order = [i for i in np.argsort(-contrib) if present[i] and contrib[i] > 0.15]
    return [_factor_text(FEATURES[i], float(row.iloc[i]), owner) for i in order[:top]]


def _downsample(points: list[tuple[float, float]], n: int = 60) -> list[list[float]]:
    if len(points) > n:
        idx = np.linspace(0, len(points) - 1, n).round().astype(int)
        points = [points[i] for i in idx]
    return [[round(float(a), 3), round(float(b), 3)] for a, b in points]


def evaluate(x: pd.DataFrame, y: pd.Series, tickets: pd.DataFrame, kinds: pd.Series) -> dict:
    from sklearn.calibration import calibration_curve
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        precision_recall_curve,
        roc_auc_score,
        roc_curve,
    )

    train, test, split = nlp.time_split(tickets.loc[y.index].assign(_y=y))
    ytr, yte = y.loc[train.index], y.loc[test.index]
    if min(ytr.sum(), (1 - ytr).sum(), yte.sum(), (1 - yte).sum()) < 3:
        return {
            "available": False,
            "reason": "The test period has too few late (or on-time) tickets to score the model.",
        }
    model = _pipeline().fit(x.loc[train.index], ytr)
    p = model.predict_proba(x.loc[test.index])[:, 1]

    # Heuristic baseline: how far the plan falls short of the type's typical cycle time.
    med = tickets.loc[train.index].groupby(kinds.loc[train.index])["cycle_days"].median()
    typical = kinds.loc[test.index].map(med).fillna(tickets.loc[train.index, "cycle_days"].median())
    heuristic = typical / x.loc[test.index, "planned_days"].clip(lower=0.5)

    fpr, tpr, _ = roc_curve(yte, p)
    prec, rec, _ = precision_recall_curve(yte, p)
    frac, mean_pred = calibration_curve(yte, p, n_bins=8, strategy="quantile")
    pred = p >= 0.5
    lr = model.steps[1][1]
    weights = sorted(
        ({"feature": LABELS[f], "weight": round(float(w), 3)} for f, w in zip(FEATURES, lr.coef_[0], strict=False)),
        key=lambda d: -abs(d["weight"]),
    )
    return {
        "available": True,
        "reason": "",
        "roc_auc": round(float(roc_auc_score(yte, p)), 3),
        "average_precision": round(float(average_precision_score(yte, p)), 3),
        "brier": round(float(brier_score_loss(yte, p)), 4),
        "base_rate": round(float(yte.mean()), 3),
        "precision_at_50": round(float(yte[pred].mean()), 3) if pred.any() else 0.0,
        "recall_at_50": round(float(pred[yte.to_numpy() == 1].mean()), 3),
        "train_size": int(len(train)),
        "test_size": int(len(test)),
        "split": split,
        "baseline": {
            "name": "plan length vs the type's median cycle time",
            "roc_auc": round(float(roc_auc_score(yte, heuristic)), 3),
            "average_precision": round(float(average_precision_score(yte, heuristic)), 3),
        },
        "roc_curve": _downsample(list(zip(fpr, tpr, strict=False))),
        "pr_curve": _downsample(list(zip(rec, prec, strict=False))),
        "calibration": _downsample(list(zip(mean_pred, frac, strict=False))),
        "weights": weights[:8],
    }


class RiskModel:
    """Fitted on every finished ticket with a due date; scores open tickets and drafts."""

    def __init__(self, tickets: pd.DataFrame, kinds: pd.Series, quality: pd.Series):
        self.tickets = tickets
        self.kinds = kinds
        self.load = owner_load(tickets)
        self.x = features(tickets, kinds, quality, self.load)
        labelled = tickets["late"].notna()
        self.y = tickets.loc[labelled, "late"].astype(int)
        self.model = None
        n, pos = len(self.y), int(self.y.sum())
        if n < MIN_ROWS or min(pos, n - pos) < MIN_CLASS:
            self.available = False
            self.reason = (
                f"The slip-risk model needs at least {MIN_ROWS} finished tickets with due dates, including "
                f"{MIN_CLASS} late and {MIN_CLASS} on time; this project has {n} ({pos} late)."
            )
            return
        self.available, self.reason = True, ""
        self.model = _pipeline().fit(self.x.loc[self.y.index], self.y)

    def evaluation(self) -> dict:
        if not self.available:
            return {"available": False, "reason": self.reason}
        return evaluate(self.x.loc[self.y.index], self.y, self.tickets, self.kinds)

    def open_risks(self) -> dict:
        if not self.available:
            return {"available": False, "reason": self.reason, "items": []}
        t = self.tickets
        scored = t[(t["status"] != "done") & t["due"].notna()]
        if scored.empty:
            return {"available": True, "reason": "", "items": []}
        probs = self.model.predict_proba(self.x.loc[scored.index])[:, 1]
        items = [
            {
                "id": r.id,
                "title": r.title,
                "owner": r.owner,
                "status": r.status,
                "due": r.due.date().isoformat(),
                "risk": round(float(p), 3),
                "factors": explain(self.model, self.x.loc[r.Index], r.owner),
            }
            for r, p in zip(scored.itertuples(), probs, strict=False)
        ]
        items.sort(key=lambda d: -d["risk"])
        return {
            "available": True,
            "reason": "",
            "items": items,
            "unscored": int(((t["status"] != "done") & t["due"].isna()).sum()),
        }

    def score_draft(self, title: str, description: str, owner: str, planned_days: float, priority: str, kind: str):
        if not self.available:
            return None
        t = self.tickets
        draft = pd.DataFrame(
            [
                {
                    "title": title,
                    "description": description,
                    "owner": owner.strip(),
                    "priority": priority,
                    "planned_days": planned_days,
                }
            ]
        )
        load = np.array([float(((t["owner"] == owner.strip()) & (t["status"] != "done")).sum()) if owner else 0.0])
        quality = pd.Series([float(nlp.quality(title, description, owner, True)[0])])
        row = features(draft, pd.Series([kind]), quality, load).iloc[0]
        risk = float(self.model.predict_proba(row.to_frame().T)[0, 1])
        return {"risk": round(risk, 3), "factors": explain(self.model, row, owner.strip())}
