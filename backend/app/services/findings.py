"""Turns computed analytics into numbered findings (F1, F2, …) for the advice layer.

Findings are the only facts the LLM may use. Every number it writes must come from
here, which is what the validator checks. In privacy mode findings carry no ticket
titles and no theme names, so nothing identifying leaves the server.
"""

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.services import nlp, risk_model

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass
class Finding:
    id: str
    kind: str
    severity: str
    text: str
    data: dict = field(default_factory=dict)

    def out(self) -> dict:
        return {"id": self.id, "kind": self.kind, "severity": self.severity, "text": self.text}


def _names(titles: list[str], privacy: bool, limit: int = 2) -> str:
    if privacy or not titles:
        return ""
    shown = ", ".join(f"“{t}”" for t in titles[:limit])
    return f" ({shown}{' and others' if len(titles) > limit else ''})"


def _plural(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def build(analysis, privacy: bool = False, today: date | None = None) -> list[Finding]:
    t = analysis.tickets
    today = today or analysis.today
    open_t = t[t["status"] != "done"]
    raw: list[tuple[str, str, str, dict]] = []

    overdue = open_t[open_t["due"].notna() & (open_t["due"] < pd.Timestamp(today))].sort_values("due")
    if len(overdue):
        sev = "critical" if len(overdue) >= 3 or (overdue["priority"] == "high").any() else "warning"
        raw.append(
            (
                "overdue",
                sev,
                f"{_plural(len(overdue), 'open ticket')} {'is' if len(overdue) == 1 else 'are'} past the due date"
                f"{_names(overdue['title'].tolist(), privacy)}.",
                {"count": len(overdue), "owners": overdue["owner"].replace("", "Unassigned").value_counts().to_dict()},
            )
        )

    blocked = open_t[open_t["status"] == "blocked"]
    if len(blocked):
        raw.append(
            (
                "blocked",
                "warning",
                f"{_plural(len(blocked), 'ticket')} {'is' if len(blocked) == 1 else 'are'} blocked"
                f"{_names(blocked['title'].tolist(), privacy)}.",
                {"count": len(blocked)},
            )
        )

    owners = open_t.loc[open_t["owner"] != "", "owner"].value_counts()
    if len(open_t) >= 5 and len(owners) >= 2 and owners.iloc[0] / len(open_t) > 0.3:
        share = round(100 * owners.iloc[0] / len(open_t))
        raw.append(
            (
                "overload",
                "warning",
                f"{owners.index[0]} holds {owners.iloc[0]} of the {len(open_t)} open tickets ({share}%).",
                {"owner": owners.index[0], "count": int(owners.iloc[0])},
            )
        )

    flow = analysis.flow
    kinds = [
        r for r in flow["by_kind"] if r["median_cycle_days"] is not None and r["done"] >= 5 and r["key"] != "unknown"
    ]
    if len(kinds) >= 2:
        slow = max(kinds, key=lambda r: r["median_cycle_days"])
        fast = min(kinds, key=lambda r: r["median_cycle_days"])
        raw.append(
            (
                "slowest_type",
                "info",
                f"{slow['key'].replace('_', ' ').capitalize()} tickets are the slowest type: median "
                f"{slow['median_cycle_days']} days, against {fast['median_cycle_days']} days for "
                f"{fast['key'].replace('_', ' ')}.",
                {"kind": slow["key"]},
            )
        )

    topics = [r for r in flow["by_topic"] if r["slip_rate"] is not None and r["done"] >= 8 and r["key"] != "Other"]
    if topics:
        worst = max(topics, key=lambda r: r["slip_rate"])
        if worst["slip_rate"] >= 0.3:
            name = "One theme" if privacy else f"The “{worst['key']}” theme"
            raw.append(
                (
                    "theme_late",
                    "warning" if worst["slip_rate"] >= 0.5 else "info",
                    f"{name} has the highest late rate: {round(worst['slip_rate'] * 100)}% of its finished "
                    f"tickets missed their due date (median {worst['median_cycle_days']} days).",
                    {"theme": worst["key"]},
                )
            )

    aging = [a for a in flow["aging"] if a["over_p85"]]
    if aging:
        p85 = flow["cycle_time"]["percentiles"].get("p85")
        raw.append(
            (
                "aging",
                "warning",
                f"{_plural(len(aging), 'ticket')} in progress {'is' if len(aging) == 1 else 'are'} older than "
                f"{p85} days, the age by which 85% of tickets usually finish; the oldest is "
                f"{round(aging[0]['age_days'])} days{_names([a['title'] for a in aging], privacy, 1)}.",
                {"count": len(aging)},
            )
        )

    hist = analysis.throughput_history
    if len(hist) >= 8:
        recent, before = float(np.mean(hist[-4:])), float(np.mean(hist[:-4]))
        if before > 0 and recent <= 0.75 * before:
            raw.append(
                (
                    "throughput_drop",
                    "warning",
                    f"Throughput fell to {recent:.1f} tickets a week over the last 4 weeks, from {before:.1f} before.",
                    {},
                )
            )

    fc = analysis.forecast()["forecast"]
    if fc["available"]:
        raw.append(
            (
                "forecast",
                "info",
                f"At the recent pace the {fc['remaining']} open tickets finish by {_day(fc['p50'])} (50% likely) "
                f"or {_day(fc['p85'])} (85% likely).",
                {},
            )
        )

    if analysis.risk.available:
        high = [i for i in analysis.risk.open_risks()["items"] if i["risk"] >= risk_model.HIGH_RISK]
        if high:
            raw.append(
                (
                    "high_risk",
                    "warning",
                    f"{_plural(len(high), 'open ticket')} {'has' if len(high) == 1 else 'have'} a slip risk of "
                    f"{round(risk_model.HIGH_RISK * 100)}% or more{_names([i['title'] for i in high], privacy)}; "
                    f"the top reason is “{(high[0]['factors'] or ['several small factors'])[0]}”.",
                    {"count": len(high)},
                )
            )

    dup_ids, dup_titles = [], []
    for d in nlp.duplicate_pairs(analysis.text_index, limit=500):
        for side in (d["a"], d["b"]):
            if side["status"] != "done" and side["id"] not in dup_ids:
                dup_ids.append(side["id"])
                dup_titles.append(side["title"])
    if dup_ids:
        n = len(dup_ids)
        raw.append(
            (
                "duplicates",
                "info",
                f"{_plural(n, 'open ticket')} look{'s' if n == 1 else ''} like a duplicate of another ticket"
                f"{_names(dup_titles, privacy)}.",
                {"count": n},
            )
        )

    low = open_t[analysis.quality.loc[open_t.index] < 60]
    if len(low):
        raw.append(
            (
                "low_quality",
                "info",
                f"{_plural(len(low), 'open ticket')} {'scores' if len(low) == 1 else 'score'} below 60 out of 100 "
                f"for readiness (vague title, no description or no acceptance criteria)"
                f"{_names(low['title'].tolist(), privacy)}.",
                {"count": len(low)},
            )
        )

    under = _under_planned(analysis, open_t)
    if under:
        raw.append(
            (
                "under_planned",
                "warning",
                f"{_plural(len(under), 'open ticket')} {'is' if len(under) == 1 else 'are'} planned shorter than "
                f"similar finished tickets usually take{_names([u[0] for u in under], privacy)}.",
                {"count": len(under)},
            )
        )

    raw.sort(key=lambda r: SEVERITY_ORDER[r[1]])
    return [Finding(f"F{i + 1}", kind, sev, text, data) for i, (kind, sev, text, data) in enumerate(raw)]


def _day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _under_planned(analysis, open_t: pd.DataFrame, limit: int = 40) -> list[tuple[str, dict]]:
    if analysis.reference_index is None:
        return []
    candidates = open_t[(open_t["status"] == "planned") & open_t["due"].notna()].head(limit)
    out = []
    for r in candidates.itertuples():
        ref = analysis.reference_index.query(r.title, r.description, r.planned_days)
        if ref["available"] and ref["plan"]["under_planned"]:
            out.append((r.title, ref))
    return out
