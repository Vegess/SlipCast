"""Exports: an Excel workbook for people and tidy CSVs for Tableau or Power BI.

Both are built from the same cached analysis the app uses, so the numbers match
the screens exactly.
"""

import io
import re
import zipfile

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Forecast

README = [
    ("Tickets", "ticket_id", "SlipCast's ID for the ticket."),
    ("Tickets", "title", "Ticket title."),
    ("Tickets", "type", "bug, feature, tech_debt or support. Labelled by a person, or predicted from the text."),
    ("Tickets", "type_source", "label (set by a person or imported) or predicted (by the text classifier)."),
    ("Tickets", "theme", "Theme found by clustering ticket text (named by its 3 strongest words)."),
    ("Tickets", "status", "planned, in_progress, blocked or done."),
    ("Tickets", "priority", "low, medium or high."),
    ("Tickets", "owner", "Assignee; empty when unassigned."),
    ("Tickets", "created_at", "When the ticket was created (UTC)."),
    ("Tickets", "started_at", "When work first started (UTC); empty if never started."),
    ("Tickets", "completed_at", "When the ticket was finished (UTC); empty if open."),
    ("Tickets", "due_date", "Planned due date; empty if none."),
    ("Tickets", "planned_days", "Due date minus creation date, in days: the plan."),
    ("Tickets", "cycle_days", "Completed minus started (or created if never started), in days. Finished tickets only."),
    ("Tickets", "finished_late", "1 if finished after the due date, 0 if on time; empty if open or no due date."),
    ("Tickets", "quality_score", "0-100 readiness score from the ticket text, owner and due date."),
    ("Tickets", "slip_risk", "Predicted chance (0-1) an open ticket finishes after its due date."),
    ("Status history", "ticket_id", "The ticket whose status changed."),
    ("Status history", "from_status", "Status before the change; empty for the first event."),
    ("Status history", "to_status", "Status after the change."),
    ("Status history", "changed_at", "When the change happened (UTC)."),
    ("Cycle times", "ticket_id", "A finished ticket."),
    ("Cycle times", "cycle_days", "How long it took from start to done, in days."),
    ("Cycle times", "completed_at", "When it finished; use this as the x-axis of a control chart."),
    ("Weekly throughput", "week_start", "Monday of the week (UTC)."),
    ("Weekly throughput", "tickets_finished", "Tickets finished that week. The last row is the current, partial week."),
    ("Forecast", "percentile", "50%, 85% or 95%: the chance all open tickets are done by that date."),
    ("Forecast", "date", "Forecast completion date from 10,000 Monte Carlo simulations."),
    ("Forecast", "weeks", "Weeks from today."),
    ("Forecast ledger", "kind", "project_completion or ticket_reference_class."),
    ("Forecast ledger", "hit_p85", "1 if the outcome landed within the 85% estimate; empty while pending or void."),
    ("Model metrics", "model", "Which model or forecast is being evaluated."),
    ("Model metrics", "metric", "The measure, computed on a time-based test split (train old, test new)."),
    ("Model metrics", "value", "SlipCast's score."),
    ("Model metrics", "baseline", "The same measure for a simple baseline, for comparison."),
]


def _risk(analysis) -> pd.Series:
    if not analysis.risk.available:
        return pd.Series(dtype=float)
    items = analysis.risk.open_risks()["items"]
    return pd.Series({i["id"]: i["risk"] for i in items}, dtype=float)


def tickets_frame(analysis) -> pd.DataFrame:
    t = analysis.tickets
    themes = analysis.themes
    risk = _risk(analysis)
    return pd.DataFrame(
        {
            "ticket_id": t["id"],
            "title": t["title"],
            "type": analysis.effective_kind,
            "type_source": t["kind_source"].map(lambda s: "label" if s == "label" else "predicted"),
            "theme": themes if themes is not None else "",
            "status": t["status"],
            "priority": t["priority"],
            "owner": t["owner"],
            "created_at": t["created_at"],
            "started_at": t["started_at"],
            "completed_at": t["completed_at"],
            "due_date": t["due"],
            "planned_days": t["planned_days"].astype("Int64"),
            "cycle_days": t["cycle_days"].round(2),
            "finished_late": t["late"].astype("Int64"),
            "quality_score": analysis.quality.round(0).astype("Int64"),
            "slip_risk": t["id"].map(risk).round(3),
        }
    ).sort_values("created_at", kind="stable")


def events_frame(analysis) -> pd.DataFrame:
    e = analysis.events
    return pd.DataFrame(
        {"ticket_id": e["task_id"], "from_status": e["from_status"], "to_status": e["to_status"], "changed_at": e["at"]}
    )


def cycle_frame(tickets: pd.DataFrame) -> pd.DataFrame:
    done = tickets[tickets["cycle_days"].notna()]
    cols = ["ticket_id", "title", "type", "theme", "owner", "started_at", "completed_at", "cycle_days", "finished_late"]
    return done[cols].sort_values("completed_at", kind="stable")


def throughput_frame(analysis) -> pd.DataFrame:
    tp = analysis.flow["throughput"]
    return pd.DataFrame({"week_start": pd.to_datetime(tp["weeks"]), "tickets_finished": tp["counts"]})


def forecast_frame(analysis) -> pd.DataFrame:
    f = analysis.forecast()["forecast"]
    if not f["available"]:
        return pd.DataFrame({"percentile": ["—"], "date": [None], "weeks": [None], "note": [f["reason"]]})
    rows = [(p, pd.Timestamp(f[f"p{p}"]), f[f"weeks_p{p}"]) for p in (50, 85, 95)]
    out = pd.DataFrame(rows, columns=["percentile", "date", "weeks"])
    out["percentile"] = out["percentile"].map(lambda p: f"{p}%")
    out["note"] = f"{f['remaining']} open tickets; {f['simulations']:,} simulations of the last 12 weeks"
    return out


def ledger_frame(db: Session, analysis) -> pd.DataFrame:
    rows = db.scalars(
        select(Forecast).where(Forecast.project_id == analysis.project_id).order_by(Forecast.made_at)
    ).all()
    cols = [
        "forecast_id",
        "kind",
        "subject_id",
        "made_at",
        "p50_date",
        "p85_date",
        "p10_days",
        "p50_days",
        "p85_days",
        "p90_days",
        "resolved_at",
        "actual_date",
        "actual_days",
        "hit_p85",
    ]
    data = [
        (
            r.id,
            r.kind,
            r.subject_id,
            r.made_at,
            r.p50_date,
            r.p85_date,
            r.p10_days,
            r.p50_days,
            r.p85_days,
            r.p90_days,
            r.resolved_at,
            r.actual_date,
            r.actual_days,
            None if r.hit_p85 is None else int(r.hit_p85),
        )
        for r in rows
    ]
    df = pd.DataFrame(data, columns=cols)
    df["hit_p85"] = df["hit_p85"].astype("Int64")
    for c in ("made_at", "resolved_at"):
        df[c] = pd.to_datetime(df[c], utc=True).dt.tz_localize(None)
    for c in ("p50_date", "p85_date", "actual_date"):
        df[c] = pd.to_datetime(df[c])
    return df


def metrics_frame(analysis, ledger_summary: dict) -> pd.DataFrame:
    e = analysis.evaluation
    rows = []
    c = e["classifier"]
    if c["available"]:
        rows += [
            ("Type classifier", "accuracy", c["accuracy"], c["baseline"]["accuracy"]),
            ("Type classifier", "macro F1", c["macro_f1"], c["baseline"]["macro_f1"]),
        ]
    r = e["risk"]
    if r["available"]:
        rows += [
            ("Slip-risk model", "ROC-AUC", r["roc_auc"], r["baseline"]["roc_auc"]),
            ("Slip-risk model", "average precision", r["average_precision"], r["baseline"]["average_precision"]),
            ("Slip-risk model", "Brier score", r["brier"], None),
        ]
    b = e["forecast_backtest"]
    if b["available"]:
        rows += [
            ("Monte Carlo backtest", "P85 hit rate", b["p85_hit_rate"], 0.85),
            ("Monte Carlo backtest", "P50 mean absolute error (days)", b["p50_mean_abs_error_days"], None),
        ]
    rc = e["reference_class"]
    if rc["available"]:
        rows += [
            ("Reference class", "P10-P90 coverage", rc["coverage_p10_p90"], rc["target_coverage"]),
            ("Reference class", "P50 mean absolute error (days)", rc["p50_mae_days"], rc["baseline"]["p50_mae_days"]),
        ]
    if e["topics"]["available"]:
        rows.append(("Themes", "cosine silhouette", e["topics"]["silhouette"], None))
    if ledger_summary["available"]:
        rows.append(("Forecast ledger", "hit rate within P85", ledger_summary["hit_rate"], 0.85))
    if not rows:
        rows.append(("—", "Not enough data to evaluate any model yet", None, None))
    return pd.DataFrame(rows, columns=["model", "metric", "value", "baseline"])


def _readme_frame() -> pd.DataFrame:
    return pd.DataFrame(README, columns=["sheet", "column", "meaning"])


def workbook(db: Session, analysis, project_name: str, ledger_summary: dict) -> bytes:
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    tickets = tickets_frame(analysis)
    sheets = {
        "README": _readme_frame(),
        "Tickets": tickets,
        "Status history": events_frame(analysis),
        "Cycle times": cycle_frame(tickets),
        "Weekly throughput": throughput_frame(analysis),
        "Forecast": forecast_frame(analysis),
        "Forecast ledger": ledger_frame(db, analysis),
        "Model metrics": metrics_frame(analysis, ledger_summary),
    }
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl", datetime_format="yyyy-mm-dd hh:mm", date_format="yyyy-mm-dd") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = Font(bold=True)
            for i, col in enumerate(df.columns, start=1):
                width = max([len(str(col))] + [len(str(v)) for v in df[col].head(200).tolist()])
                ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 60)
                if col in ("due_date", "week_start", "date", "p50_date", "p85_date", "actual_date"):
                    for (c,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                        c.number_format = "yyyy-mm-dd"
        xw.book["README"].insert_rows(1, 2)
        xw.book["README"]["A1"] = f"SlipCast export: {project_name}"
        xw.book["README"]["A1"].font = Font(bold=True, size=14)
        xw.book["README"].freeze_panes = "A4"
    return buf.getvalue()


def _iso(df: pd.DataFrame, date_only: tuple[str, ...] = ()) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            fmt = "%Y-%m-%d" if col in date_only else "%Y-%m-%dT%H:%M:%S"
            out[col] = out[col].dt.strftime(fmt)
    return out


def bi_zip(db: Session, analysis) -> bytes:
    tickets = tickets_frame(analysis)
    files = {
        "tickets.csv": _iso(tickets, ("due_date",)),
        "events.csv": _iso(events_frame(analysis)),
        "cycle_times.csv": _iso(cycle_frame(tickets)),
        "weekly_throughput.csv": _iso(throughput_frame(analysis), ("week_start",)),
        "forecasts.csv": _iso(ledger_frame(db, analysis), ("p50_date", "p85_date", "actual_date")),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, df in files.items():
            zf.writestr(name, df.to_csv(index=False))
        zf.writestr("README.txt", "\n".join(f"{s} / {c}: {m}" for s, c, m in README) + "\n")
    return buf.getvalue()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "project"
