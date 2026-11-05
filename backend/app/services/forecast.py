"""Monte Carlo completion forecast from recent weekly throughput.

Each simulation draws random weeks (with replacement) from the last 12 complete weeks
of throughput until the remaining tickets are done. The final week is interpolated:
if 3 tickets were left and the drawn week finished 6, that week counts as half.
"""

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

SIMULATIONS = 10_000
MIN_HISTORY_WEEKS = 4
MAX_WEEKS = 520
SEED = 20240611


def simulate(
    history: np.ndarray, remaining: int, sims: int = SIMULATIONS, seed: int = SEED, max_weeks: int = MAX_WEEKS
) -> np.ndarray:
    """Weeks needed to finish `remaining` tickets in each simulation (NaN if never)."""
    history = np.asarray(history, dtype=float)
    result = np.full(sims, np.nan)
    if remaining <= 0:
        return np.zeros(sims)
    rng = np.random.default_rng(seed)
    cum = np.zeros(sims)
    active = np.arange(sims)
    week = 0
    while active.size and week < max_weeks:
        drawn = rng.choice(history, size=active.size)
        total = cum[active] + drawn
        finished = total >= remaining
        idx = active[finished]
        result[idx] = week + (remaining - cum[idx]) / drawn[finished]
        cum[active] = total
        active = active[~finished]
        week += 1
    return result


def forecast(history: np.ndarray, remaining: int, today: date, target: date | None = None) -> dict:
    history = np.asarray(history, dtype=int)
    base = {"available": False, "remaining": remaining, "history_weeks": history.tolist()}
    if remaining == 0:
        return {"forecast": {**base, "reason": "Every ticket is done, so there is nothing left to forecast."}}
    if history.size < MIN_HISTORY_WEEKS:
        return {
            "forecast": {
                **base,
                "reason": f"The forecast needs at least {MIN_HISTORY_WEEKS} complete weeks of history; "
                f"this project has {history.size}.",
            }
        }
    if history.sum() == 0:
        return {
            "forecast": {
                **base,
                "reason": f"No tickets were finished in the last {history.size} weeks, so there is no pace to project.",
            }
        }
    weeks = simulate(history, remaining)
    if np.isnan(weeks).any():
        return {"forecast": {**base, "reason": "At the recent pace this work would take more than 10 years."}}

    p50, p85, p95 = (float(v) for v in np.percentile(weeks, [50, 85, 95]))

    def to_date(w: float) -> str:
        return (today + timedelta(days=int(np.ceil(w * 7)))).isoformat()

    buckets = np.maximum(np.ceil(weeks).astype(int) - 1, 0)
    counts = np.bincount(buckets)
    out = {
        **base,
        "available": True,
        "simulations": int(weeks.size),
        "weeks_p50": round(p50, 2),
        "weeks_p85": round(p85, 2),
        "weeks_p95": round(p95, 2),
        "p50": to_date(p50),
        "p85": to_date(p85),
        "p95": to_date(p95),
        "histogram": [
            {"week": int(i), "probability": round(float(c) / weeks.size, 4)} for i, c in enumerate(counts) if c
        ],
    }
    if target is not None:
        days = (target - today).days
        out["target"] = target.isoformat()
        out["target_probability"] = round(float(np.mean(weeks * 7 <= days)), 3)
    return {"forecast": out}


def burnup(tickets: pd.DataFrame, now: datetime, result: dict, weeks: int = 26) -> dict:
    """Weekly scope and done lines, plus straight-line projections to the P50 and P85 dates."""
    now_ts = pd.Timestamp(now)
    points = [now_ts.normalize() - pd.Timedelta(weeks=i) for i in range(weeks, 0, -1)] + [now_ts]
    if not tickets.empty:
        first = tickets["created_at"].min().normalize()
        points = [p for p in points if p >= first] or [now_ts]
    created = tickets["created_at"].dropna().sort_values().to_numpy()
    done = tickets.loc[tickets["finished"], "completed_at"].sort_values().to_numpy()
    scope = [int(np.searchsorted(created, p.to_datetime64(), side="right")) for p in points]
    finished = [int(np.searchsorted(done, p.to_datetime64(), side="right")) for p in points]
    out = {"dates": [p.date().isoformat() for p in points], "scope": scope, "done": finished}
    f = result["forecast"]
    if f["available"]:
        today = now_ts.date().isoformat()
        total = len(tickets)
        done_now = total - f["remaining"]
        out["projection"] = {
            "p50": [[today, done_now], [f["p50"], total]],
            "p85": [[today, done_now], [f["p85"], total]],
        }
    return out
