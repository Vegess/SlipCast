"""Loads SlipCast's demo dataset through the backend services, exactly as the API does.

Usage in a notebook (run from the notebooks/ folder):

    from slipcast_data import load_demo
    analysis = load_demo()
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.analysis import Analysis, build_frames  # noqa: E402
from app.services.demo_data import generate  # noqa: E402

# A fixed "today" keeps every number in the notebooks reproducible.
NOW = datetime(2026, 11, 5, 12, 0)


def load_demo(now: datetime = NOW) -> Analysis:
    """Generate the demo project (seeded) and wrap it in the same Analysis the API uses."""
    rows = generate(now)
    task_rows = [
        (
            f"T{i:04d}",
            r["title"],
            r["description"],
            r["owner"],
            r["status"],
            r["priority"],
            r["due"],
            r["kind"],
            r["kind_source"],
            r["created_at"],
            r["started_at"],
            r["completed_at"],
            now,
        )
        for i, r in enumerate(rows)
    ]
    event_rows = [(f"T{i:04d}", frm, to, at) for i, r in enumerate(rows) for frm, to, at in r["events"]]
    tickets, events = build_frames(task_rows, event_rows)
    return Analysis("demo", tickets, events, now)
