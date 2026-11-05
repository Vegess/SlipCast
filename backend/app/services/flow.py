"""Flow metrics: cycle time, throughput, cumulative flow, breakdowns and aging work.

Cycle time is `completed_at - started_at` (falling back to `created_at` when a ticket
was never marked in progress), in fractional days.
"""

from datetime import datetime

import numpy as np
import pandas as pd

THROUGHPUT_WEEKS = 26
HISTORY_WEEKS = 12
CFD_DAYS = 120
STATUSES = ("planned", "in_progress", "blocked", "done")


def percentiles(values: pd.Series | np.ndarray, qs=(50, 85, 95)) -> dict[str, float]:
    arr = np.asarray(pd.Series(values).dropna(), dtype=float)
    if arr.size == 0:
        return {}
    return {f"p{q}": round(float(np.percentile(arr, q)), 1) for q in qs}


def week_start(ts: pd.Series | pd.Timestamp):
    """Monday 00:00 of the week containing each timestamp."""
    if isinstance(ts, pd.Series):
        day = ts.dt.normalize()
        return day - pd.to_timedelta(day.dt.weekday, unit="D")
    day = pd.Timestamp(ts).normalize()
    return day - pd.Timedelta(days=day.weekday())


def weekly_throughput(tickets: pd.DataFrame, now: datetime, weeks: int = THROUGHPUT_WEEKS) -> pd.Series:
    """Finished tickets per week, oldest first; the last entry is the current, partial week."""
    current = week_start(pd.Timestamp(now))
    index = pd.DatetimeIndex([current - pd.Timedelta(weeks=i) for i in range(weeks - 1, -1, -1)])
    done = tickets.loc[tickets["finished"], "completed_at"]
    counts = week_start(done).value_counts() if len(done) else pd.Series(dtype=int)
    return counts.reindex(index, fill_value=0).astype(int)


def history_weeks(tickets: pd.DataFrame, now: datetime, weeks: int = HISTORY_WEEKS) -> list[int]:
    """Throughput of the last `weeks` complete weeks, skipping weeks before the project began."""
    if tickets.empty or tickets["created_at"].isna().all():
        return []
    series = weekly_throughput(tickets, now, weeks + 1).iloc[:-1]  # drop the current partial week
    first = week_start(tickets["created_at"].min())
    return [int(v) for v in series[series.index >= first].tolist()]


def cumulative_flow(tickets: pd.DataFrame, events: pd.DataFrame, now: datetime, days: int = CFD_DAYS) -> dict:
    """Status of every ticket at the end of each of the last `days` days, from its event history."""
    today = pd.Timestamp(now).normalize()
    day_list = [today - pd.Timedelta(days=i) for i in range(days - 1, -1, -1)]
    snaps = [d + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1) for d in day_list[:-1]] + [pd.Timestamp(now)]
    empty = {"dates": [d.date().isoformat() for d in day_list], "series": {s: [0] * days for s in STATUSES}}
    if tickets.empty or events.empty:
        return empty
    grid = pd.DataFrame({"snap": pd.to_datetime(snaps), "day": range(days)})
    cross = pd.DataFrame({"task_id": tickets["id"]}).merge(grid, how="cross").sort_values("snap")
    ev = events[["task_id", "to_status", "at"]].rename(columns={"at": "snap"}).sort_values("snap")
    ev["snap"] = ev["snap"].astype("datetime64[ns]")
    cross["snap"] = cross["snap"].astype("datetime64[ns]")
    merged = pd.merge_asof(cross, ev, on="snap", by="task_id", direction="backward").dropna(subset=["to_status"])
    table = merged.groupby(["day", "to_status"]).size().unstack(fill_value=0).reindex(range(days), fill_value=0)
    return {
        "dates": empty["dates"],
        "series": {s: [int(v) for v in table[s]] if s in table else [0] * days for s in STATUSES},
    }


def _round(v) -> float | None:
    return None if v is None or pd.isna(v) else round(float(v), 1)


def breakdown(tickets: pd.DataFrame, keys: pd.Series) -> list[dict]:
    """Open/done counts, median and P85 cycle time and late rate for each group."""
    rows = []
    for key, g in tickets.groupby(keys.values, sort=False):
        cycles = g.loc[g["finished"], "cycle_days"]
        late = g["late"].dropna()
        rows.append(
            {
                "key": str(key),
                "open": int((g["status"] != "done").sum()),
                "done": int(g["finished"].sum()),
                "median_cycle_days": _round(cycles.median()) if len(cycles) else None,
                "p85_cycle_days": _round(np.percentile(cycles, 85)) if len(cycles) else None,
                "slip_rate": round(float(late.mean()), 3) if len(late) else None,
            }
        )
    return sorted(rows, key=lambda r: (-(r["open"] + r["done"]), r["key"]))


def aging(tickets: pd.DataFrame, now: datetime, p85: float | None, limit: int = 15) -> list[dict]:
    active = tickets[tickets["status"].isin(["in_progress", "blocked"])].copy()
    if active.empty:
        return []
    active["age_days"] = (pd.Timestamp(now) - active["start"]).dt.total_seconds() / 86400
    active = active.sort_values("age_days", ascending=False).head(limit)
    return [
        {
            "id": r.id,
            "title": r.title,
            "owner": r.owner,
            "status": r.status,
            "age_days": round(float(r.age_days), 1),
            "over_p85": bool(p85 is not None and r.age_days > p85),
        }
        for r in active.itertuples()
    ]


def compute(
    tickets: pd.DataFrame,
    events: pd.DataFrame,
    now: datetime,
    kinds: pd.Series,
    themes: pd.Series | None = None,
) -> dict:
    finished = tickets[tickets["finished"]]
    pct = percentiles(finished["cycle_days"])
    owners = tickets["owner"].where(tickets["owner"] != "", "Unassigned")
    tp = weekly_throughput(tickets, now)
    out = {
        "available": len(finished) >= 5,
        "reason": ""
        if len(finished) >= 5
        else f"Flow metrics need at least 5 finished tickets; this project has {len(finished)}.",
        "cycle_time": {
            "percentiles": pct,
            "points": [
                {
                    "id": r.id,
                    "title": r.title,
                    "date": r.completed_at.isoformat(),
                    "days": round(float(r.cycle_days), 1),
                    "kind": str(kinds.loc[r.Index]),
                }
                for r in finished.itertuples()
            ],
        },
        "throughput": {"weeks": [d.date().isoformat() for d in tp.index], "counts": tp.tolist()},
        "cfd": cumulative_flow(tickets, events, now),
        "by_kind": breakdown(tickets, kinds),
        "by_owner": breakdown(tickets, owners),
        "by_topic": breakdown(tickets, themes) if themes is not None else [],
        "aging": aging(tickets, now, pct.get("p85")),
    }
    return out
