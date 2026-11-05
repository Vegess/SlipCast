"""Reference-class forecasting per ticket.

For a ticket, find the most similar *finished* tickets by text (TF-IDF cosine
similarity) and report how long they really took. This is reference-class
forecasting (Kahneman and Flyvbjerg) applied to ticket text: instead of trusting
the plan, look at what happened to tickets like this one.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

K = 20
MIN_SIMILARITY = 0.15
MIN_N = 8
SHOWN = 3


def ticket_text(title: pd.Series | str, description: pd.Series | str):
    """Title counts twice: it is the most deliberate summary of the work."""
    return title + " " + title + " " + description


def make_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", min_df=1)


def _fmt(v: float) -> str:
    return f"{v:.0f}" if v >= 3 else f"{v:.1f}".rstrip("0").rstrip(".")


def summarise(
    sims: np.ndarray,
    cycle_days: np.ndarray,
    late: np.ndarray,
    meta: pd.DataFrame | None = None,
    planned_days: float | None = None,
    k: int = K,
    min_similarity: float = MIN_SIMILARITY,
    min_n: int = MIN_N,
) -> dict:
    """Reference class from a similarity vector over candidate finished tickets.

    `sims`, `cycle_days` and `late` are aligned arrays over the candidates (callers mask
    out anything that must not be used, e.g. tickets that finished later, by passing
    similarity -1). `meta` holds id and title for the candidates, for the examples.
    """
    order = np.argsort(-sims, kind="stable")[:k]
    order = order[sims[order] >= min_similarity]
    n = int(order.size)
    out: dict = {"n": n, "k": k, "min_similarity": min_similarity, "similar": []}
    if meta is not None:
        out["similar"] = [
            {
                "id": meta.iloc[i]["id"],
                "title": meta.iloc[i]["title"],
                "days": round(float(cycle_days[i]), 1),
                "similarity": round(float(sims[i]), 2),
            }
            for i in order[:SHOWN]
        ]
    if n < min_n:
        out.update(
            available=False,
            reason=f"Only {n} finished ticket{'s are' if n != 1 else ' is'} similar enough to compare "
            f"(at least {min_n} are needed), so there is no reference class yet.",
        )
        return out
    days = cycle_days[order]
    p10, p25, p50, p85, p90 = (float(v) for v in np.percentile(days, [10, 25, 50, 85, 90]))
    lates = late[order]
    lates = lates[~np.isnan(lates)]
    out.update(
        available=True,
        reason="",
        p10=round(p10, 1),
        p25=round(p25, 1),
        p50=round(p50, 1),
        p85=round(p85, 1),
        p90=round(p90, 1),
        late_rate=round(float(lates.mean()), 3) if lates.size else None,
        summary=f"Tickets like this took {_fmt(p10)}–{_fmt(p90)} days (n={n}).",
    )
    out["plan"] = plan_check(out, planned_days)
    return out


def plan_check(ref: dict, planned_days: float | None) -> dict:
    """Flag plans shorter than what 75% of similar tickets needed."""
    if planned_days is None or pd.isna(planned_days):
        return {"planned_days": None, "under_planned": False, "message": "No due date, so there is no plan to compare."}
    planned = float(planned_days)
    under = planned < ref["p25"]
    span = f"similar tickets took {_fmt(ref['p10'])}–{_fmt(ref['p90'])}"
    unit = "day" if planned == 1 else "days"
    message = (
        f"Planned {_fmt(planned)} {unit}; {span}. Three in four similar tickets needed more than "
        f"{_fmt(ref['p25'])} days."
        if under
        else f"Planned {_fmt(planned)} {unit}; {span}."
    )
    return {"planned_days": round(planned, 1), "under_planned": bool(under), "message": message}


@dataclass
class ReferenceIndex:
    """TF-IDF index over a project's finished tickets."""

    vectorizer: TfidfVectorizer
    matrix: object
    finished: pd.DataFrame

    @classmethod
    def build(cls, tickets: pd.DataFrame) -> "ReferenceIndex | None":
        finished = tickets[tickets["finished"]].reset_index(drop=True)
        text = ticket_text(finished["title"], finished["description"])
        if finished.empty or not text.str.strip().any():
            return None
        vec = make_vectorizer()
        try:
            matrix = vec.fit_transform(text)
        except ValueError:  # every word is a stop word
            return None
        return cls(vec, matrix, finished)

    def similarities(self, title: str, description: str) -> np.ndarray:
        q = self.vectorizer.transform([ticket_text(title, description)])
        return (self.matrix @ q.T).toarray().ravel()

    def query(
        self, title: str, description: str, planned_days: float | None = None, exclude_id: str | None = None
    ) -> dict:
        sims = self.similarities(title, description)
        if exclude_id is not None:
            sims = np.where(self.finished["id"].to_numpy() == exclude_id, -1.0, sims)
        return summarise(
            sims,
            self.finished["cycle_days"].to_numpy(dtype=float),
            self.finished["late"].to_numpy(dtype=float),
            self.finished[["id", "title"]],
            planned_days,
        )


def unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason, "n": 0, "similar": [], "plan": None}


def evaluate(tickets: pd.DataFrame, test_share: float = 0.25) -> dict:
    """Time-based backtest: older finished tickets form the reference classes for newer ones.

    Test tickets are the newest `test_share` of finished tickets by creation date; their
    reference classes may only use tickets that had finished before the cutoff. Reports
    P10–P90 coverage (target about 80%) and the P50 error against the project median.
    """
    finished = tickets[tickets["finished"]].sort_values("created_at").reset_index(drop=True)
    if len(finished) < 40:
        return {
            "available": False,
            "reason": f"Needs at least 40 finished tickets to backtest; this project has {len(finished)}.",
        }
    cutoff = finished["created_at"].quantile(1 - test_share)
    train = finished[finished["completed_at"] < cutoff].reset_index(drop=True)
    test = finished[finished["created_at"] >= cutoff].reset_index(drop=True)
    if len(train) < 20 or test.empty:
        return {"available": False, "reason": "Not enough history before the test period to build reference classes."}
    vec = make_vectorizer()
    x_train = vec.fit_transform(ticket_text(train["title"], train["description"]))
    x_test = vec.transform(ticket_text(test["title"], test["description"]))
    sims = (x_test @ x_train.T).toarray()
    cycle = train["cycle_days"].to_numpy(dtype=float)
    late = train["late"].to_numpy(dtype=float)
    baseline = float(np.median(cycle))
    rows = []
    for i, actual in enumerate(test["cycle_days"].to_numpy(dtype=float)):
        ref = summarise(sims[i], cycle, late)
        if ref["available"]:
            rows.append((actual, ref["p10"], ref["p50"], ref["p90"]))
    if not rows:
        return {"available": False, "reason": "No test ticket had enough similar history."}
    arr = np.array(rows)
    actual, p10, p50, p90 = arr.T
    covered = (actual >= p10) & (actual <= p90)
    return {
        "available": True,
        "reason": "",
        "split": f"trained on tickets finished before {cutoff.date().isoformat()}, tested on tickets created after",
        "train_size": int(len(train)),
        "test_size": int(len(test)),
        "evaluated": int(len(rows)),
        "coverage_p10_p90": round(float(covered.mean()), 3),
        "target_coverage": 0.8,
        "p50_mae_days": round(float(np.mean(np.abs(actual - p50))), 2),
        "baseline": {
            "name": "project-wide median cycle time",
            "p50_mae_days": round(float(np.mean(np.abs(actual - baseline))), 2),
        },
    }
