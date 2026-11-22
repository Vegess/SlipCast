"""Sends simulated order events to a SlipCast Ship project, so the screens update live.

Each order gets a realistic timeline (ordered, packed, dispatched, in transit, out for
delivery, delivered, sometimes an exception) that ends around now. Events are sent oldest
first in small batches with a pause between them, so you can watch the board, the Delivery
tab and the alerts move. Timestamps are real, so delivery times stay realistic.

Needs only Python 3.10+. Usage:
    python scripts/simulate_orders.py --project <project id> --key <API key> [--orders 40]
    [--api https://slipcast-api.onrender.com] [--pause 1.5] [--seed 1]

Create the API key on the project's Live feed tab. Re-running with the same --seed within the
same hour sends the same events, and SlipCast ignores events it has already seen. Use a new
--seed for new orders.
"""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

ORIGINS = ["Chennai", "Mumbai"]
DESTINATIONS = {"Chennai": 0, "Bengaluru": 1, "Hyderabad": 1, "Pune": 1, "Delhi": 2, "Kolkata": 2,
                "Jaipur": 2, "Guwahati": 3}  # fmt: skip
SAME_REGION = {("Mumbai", "Pune"), ("Chennai", "Bengaluru"), ("Chennai", "Hyderabad")}
CARRIERS = {"SwiftLine": 0.85, "Coastal Express": 1.0, "MetroPost": 1.25, "Kite Logistics": 1.1}
BASE_DAYS = [1.0, 2.2, 3.8, 6.5]
PROMISE = [2, 3, 5, 6]


def tier(origin: str, dest: str) -> int:
    if origin == dest:
        return 0
    if DESTINATIONS[dest] == 3:
        return 3
    return 1 if (origin, dest) in SAME_REGION else 2


def order_events(n: int, r: random.Random, now: datetime) -> list[dict]:
    origin, dest = r.choice(ORIGINS), r.choice(list(DESTINATIONS))
    carrier = r.choice(list(CARRIERS))
    t = tier(origin, dest)
    total = BASE_DAYS[t] * CARRIERS[carrier] * r.lognormvariate(0, 0.25)
    exception = r.random() < 0.06
    total += r.uniform(1.5, 3.5) if exception else 0
    # Place orders so about two thirds have arrived by now and the rest are on the way.
    ordered = now - timedelta(days=r.uniform(0.2, total * 1.5 + 0.5))
    steps = [("ordered", 0.0), ("packed", r.uniform(0.1, 0.6)), ("dispatched", r.uniform(0.2, 0.4)),
             ("in_transit", r.uniform(0.05, 0.2))]  # fmt: skip
    times, at = [], ordered
    for stage, gap in steps:
        at += timedelta(days=gap)
        times.append((stage, at))
    delivered = ordered + timedelta(days=max(total, times[-1][1].timestamp() - ordered.timestamp() + 0.2))
    if exception:
        hit = at + (delivered - at) * 0.3
        times += [("exception", hit), ("in_transit", hit + timedelta(hours=r.uniform(8, 30)))]
    times += [("out_for_delivery", delivered - timedelta(hours=r.uniform(2, 5))), ("delivered", delivered)]
    weight = round(r.uniform(0.3, 8), 1)
    fields = {
        "external_id": f"SIM-{n}",
        "title": f"Order #SIM-{n} · {origin} → {dest}",
        "description": f"{weight} kg. Simulated order.",
        "owner": carrier,
        "item_type": "order",
        "due": (ordered + timedelta(days=PROMISE[t])).date().isoformat(),
        "attributes": {"origin": origin, "destination": dest, "carrier": carrier, "service": "standard",
                       "weight_kg": weight, "order_value": r.randrange(400, 6000, 10)},
    }  # fmt: skip
    return [
        {**fields, "stage": stage, "occurred_at": when.replace(microsecond=0).isoformat()}
        for stage, when in times
        if when <= now
    ]


def send(api: str, project: str, key: str, events: list[dict]) -> dict:
    req = urllib.request.Request(
        f"{api.rstrip('/')}/api/projects/{project}/events",
        data=json.dumps({"events": events}).encode(),
        headers={"Content-Type": "application/json", "X-SlipCast-Key": key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", required=True, help="Project id (from the project's URL)")
    p.add_argument("--key", required=True, help="API key from the Live feed tab")
    p.add_argument("--api", default="https://slipcast-api.onrender.com")
    p.add_argument("--orders", type=int, default=40)
    p.add_argument("--pause", type=float, default=1.5, help="Seconds between batches")
    p.add_argument("--batch", type=int, default=8, help="Events per batch")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()

    r = random.Random(a.seed)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)  # same hour, same events
    events = [e for n in range(1, a.orders + 1) for e in order_events(a.seed * 10000 + n, r, now)]
    events.sort(key=lambda e: e["occurred_at"])
    print(f"Sending {len(events)} events for {a.orders} orders to {a.api} …")
    for i in range(0, len(events), a.batch):
        chunk = events[i : i + a.batch]
        try:
            result = send(a.api, a.project, a.key, chunk)
        except urllib.error.HTTPError as e:
            sys.exit(f"Stopped: HTTP {e.code} {e.read().decode()[:300]}")
        except urllib.error.URLError as e:
            sys.exit(f"Stopped: can't reach {a.api} ({e.reason}). The API may be waking up; try again.")
        print(f"  {i + len(chunk):>4}/{len(events)}  created {result.get('created', 0)}, "
              f"updated {result.get('updated', 0)}, already seen {result.get('duplicates', 0)}")  # fmt: skip
        if i + a.batch < len(events):
            time.sleep(a.pause)
    print("Done. Open the project's Delivery tab to see on-time rates and orders at risk.")


if __name__ == "__main__":
    main()
