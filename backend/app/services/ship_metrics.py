"""Ship module metrics: on-time delivery by carrier and route, where orders wait, and late risk.

Every number here is a reference class, not a black box:
- An order's estimate comes from delivered orders most like it: same route and carrier,
  else same route, else same destination, else same carrier ("orders like this on this
  route took 3-6 days").
- An order's late risk combines two late rates: orders on the same route at the same service
  level, and the carrier's orders over the last 6 weeks. Each is pulled toward the overall
  late rate when it rests on few orders, and the two are combined in log-odds (as a naive
  Bayes model would), so both can be shown as the reason. Past the promised date, an
  exception, or being slower than 9 in 10 similar orders raise it further.
- Both are back-tested: each of the newest 30% of delivered orders is estimated from orders
  delivered before it was placed, against a baseline (the median of all earlier orders for
  the estimate; the carrier's late rate for the risk).

Times come from the order's own fields: created_at is when it was ordered, completed_at
when it was delivered, and `due` is the promised delivery date.
"""

from datetime import date, datetime, timedelta
from math import exp, log

import numpy as np
from sklearn.metrics import roc_auc_score
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BUILD_TYPES, IngestedEvent, Task
from app.timeutil import naive_utc

MIN_DELIVERED = 20
MIN_CLASS = 8
MIN_GROUP = 5
WEEKS = 12
WINDOW = timedelta(days=28)
FLOW = ["ordered", "packed", "dispatched", "in_transit", "out_for_delivery", "delivered"]
FLOW_LABELS = {
    "ordered": "Ordered → packed",
    "packed": "Packed → dispatched",
    "dispatched": "Dispatched → in transit",
    "in_transit": "In transit → out for delivery",
    "out_for_delivery": "Out for delivery → delivered",
}
HIGH, MEDIUM = 0.6, 0.3
CARRIER_RECENT = timedelta(days=42)
SMOOTHING = 10  # pseudo-orders at the overall late rate added to each group


def _days(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 86400


def _r(x: float | None, n: int = 1) -> float | None:
    return None if x is None else round(float(x), n)


def _pct(values, q: float) -> float | None:
    return _r(np.percentile(values, q)) if len(values) else None


def _rate(flags: list[bool]) -> float | None:
    return round(sum(flags) / len(flags), 3) if flags else None


def load_orders(db: Session, project_id: str) -> list[dict]:
    rows = db.execute(
        select(
            Task.id, Task.external_id, Task.title, Task.owner, Task.status, Task.stage, Task.due,
            Task.attributes, Task.created_at, Task.completed_at,
        ).where(Task.project_id == project_id, Task.item_type.notin_(BUILD_TYPES))
    ).all()  # fmt: skip
    orders = []
    for tid, ext, title, owner, status, stage, due, attrs, created, completed in rows:
        a = attrs or {}
        origin, dest = (a.get("origin") or "").strip(), (a.get("destination") or "").strip()
        created = naive_utc(created)
        completed = naive_utc(completed) if completed else None
        orders.append({
            "id": tid, "external_id": ext, "title": title, "status": status, "stage": stage,
            "carrier": (a.get("carrier") or owner or "").strip(), "origin": origin, "destination": dest,
            "service": (a.get("service") or "").strip().lower(),
            "route": f"{origin} → {dest}" if origin and dest else "", "due": due,
            "created": created, "delivered": completed if status == "done" else None,
            "planned": (due - created.date()).days if due else None,
            "transit": _days(created, completed) if status == "done" and completed else None,
            # Calendar days from order date to delivery date: what the promise is measured in.
            "cal": (completed.date() - created.date()).days if status == "done" and completed else None,
        })  # fmt: skip
    return orders


def _late(o: dict) -> bool | None:
    if o["delivered"] is None or o["due"] is None:
        return None
    return o["delivered"].date() > o["due"]


def reference_class(pool: list[dict], origin: str, destination: str, carrier: str, service: str = "") -> dict | None:
    """The most specific group of delivered orders with at least MIN_CLASS members."""
    route = f"{origin} → {destination}"
    has_route = bool(origin and destination)
    tiers = [
        (has_route and carrier and service, f"{service} orders on {route} with {carrier}",
         lambda o: o["route"] == route and o["carrier"] == carrier and o["service"] == service),
        (has_route and carrier, f"orders on {route} with {carrier}",
         lambda o: o["route"] == route and o["carrier"] == carrier),
        (has_route and service, f"{service} orders on {route}",
         lambda o: o["route"] == route and o["service"] == service),
        (has_route, f"orders on {route}", lambda o: o["route"] == route),
        (destination, f"orders to {destination}", lambda o: o["destination"] == destination),
        (carrier, f"orders with {carrier}", lambda o: o["carrier"] == carrier),
    ]  # fmt: skip
    for usable, basis, keep in tiers:
        if not usable:
            continue
        group = [o for o in pool if keep(o)]
        if len(group) >= MIN_CLASS:
            return {"basis": basis, "members": group}
    return None


def _summary(group: list[dict], planned: int | None) -> dict:
    t = [o["transit"] for o in group]
    out = {"n": len(t), "p10": _pct(t, 10), "p50": _pct(t, 50), "p90": _pct(t, 90)}
    out["late_share"] = _rate([o["cal"] > planned for o in group]) if planned is not None else None
    return out


def estimate(
    pool: list[dict], origin: str, destination: str, carrier: str, planned: int | None, service: str = ""
) -> dict:
    ref = reference_class(pool, origin, destination, carrier, service)
    if ref is None:
        return {
            "available": False,
            "reason": f"Fewer than {MIN_CLASS} delivered orders on this route, to this destination or with "
            "this carrier, so there's nothing reliable to compare with yet.",
        }
    out = {"available": True, "basis": ref["basis"], **_summary(ref["members"], planned), "planned_days": planned}
    if planned is not None and out["p10"] is not None:
        out["under_planned"] = planned < float(np.percentile([o["cal"] for o in ref["members"]], 25))
    route = f"{origin} → {destination}"
    alternatives = []
    for name in sorted({o["carrier"] for o in pool if o["route"] == route and o["carrier"]}):
        group = [o for o in pool if o["route"] == route and o["carrier"] == name]
        flags = [x for x in (_late(o) for o in group) if x is not None]
        if len(group) >= MIN_GROUP and flags:
            alternatives.append({
                "carrier": name, "delivered": len(group), "on_time_rate": round(1 - sum(flags) / len(flags), 3),
                "median_days": _pct([o["transit"] for o in group], 50),
            })  # fmt: skip
    out["carriers_on_route"] = sorted(alternatives, key=lambda c: -c["on_time_rate"])
    return out


def _logit(p: float) -> float:
    p = min(max(p, 0.01), 0.99)
    return log(p / (1 - p))


def late_risk(pool: list[dict], o: dict, at: datetime) -> dict | None:
    """Chance an order arrives after its promised date, from its route's and carrier's records."""
    flags = [(p, f) for p, f in ((p, _late(p)) for p in pool) if f is not None]
    if len(flags) < MIN_DELIVERED:
        return None
    base = sum(f for _, f in flags) / len(flags)

    def smoothed(group: list[bool]) -> tuple[float, int]:
        return (sum(group) + SMOOTHING * base) / (len(group) + SMOOTHING), len(group)

    route, n_route = smoothed([f for p, f in flags if p["route"] == o["route"] and p["service"] == o["service"]])
    carrier, n_carrier = smoothed(
        [f for p, f in flags if p["carrier"] == o["carrier"] and at - p["delivered"] <= CARRIER_RECENT]
    )
    risk = 1 / (1 + exp(-(_logit(route) + _logit(carrier) - _logit(base))))
    return {
        "risk": risk, "route_rate": round(route, 3), "route_n": n_route, "carrier_rate": round(carrier, 3),
        "carrier_n": n_carrier, "overall_rate": round(base, 3),
    }  # fmt: skip


def _open_risk(o: dict, pool: list[dict], now: datetime, has_exception: bool) -> dict:
    age = _days(o["created"], now)
    ref = reference_class(pool, o["origin"], o["destination"], o["carrier"], o["service"])
    reasons: list[str] = []
    est = None
    lr = late_risk(pool, o, now)
    risk = lr["risk"] if lr else None
    if ref is not None:
        all_t = [m["transit"] for m in ref["members"]]
        still_out = [t for t in all_t if t > age]
        expected_t = still_out if len(still_out) >= 3 else all_t
        est = {
            "basis": ref["basis"], "n": len(all_t), "p10": _pct(all_t, 10), "p50": _pct(all_t, 50),
            "p90": _pct(all_t, 90),
        }  # fmt: skip
        expected = o["created"] + timedelta(days=float(np.percentile(expected_t, 50)))
        est["expected_by"] = max(expected, now).date().isoformat()
        if o["planned"] is not None and o["planned"] < float(np.percentile([m["cal"] for m in ref["members"]], 25)):
            reasons.append(f"Promised {o['planned']} days; {est['basis']} took {est['p10']}–{est['p90']}")
        if age > float(np.percentile(all_t, 90)):
            risk = max(risk or 0, HIGH)
            reasons.append(f"Already slower than 9 in 10 {est['basis']}")
    if lr is not None and lr["route_rate"] > lr["overall_rate"] * 1.25 and lr["route_n"] >= MIN_GROUP:
        reasons.append(
            f"{round(lr['route_rate'] * 100)}% late on this route (overall {round(lr['overall_rate'] * 100)}%)"
        )
    if lr is not None and lr["carrier_rate"] > lr["overall_rate"] * 1.25 and lr["carrier_n"] >= MIN_GROUP:
        reasons.append(f"{o['carrier']}: {round(lr['carrier_rate'] * 100)}% late in the last 6 weeks")
    if has_exception:
        risk = max(risk or 0, MEDIUM + 0.1)
        reasons.insert(0, "An exception was reported in transit")
    if o["due"] is not None and now.date() > o["due"]:
        risk = 1.0
        reasons.insert(0, f"Past the promised date ({o['due'].isoformat()})")
    level = None if risk is None else "high" if risk >= HIGH else "medium" if risk >= MEDIUM else "low"
    return {
        "id": o["id"], "external_id": o["external_id"], "title": o["title"], "route": o["route"],
        "carrier": o["carrier"], "stage": o["stage"], "due": o["due"].isoformat() if o["due"] else None,
        "age_days": _r(age), "risk": _r(risk, 2), "level": level, "estimate": est,
        "rates": lr and {k: v for k, v in lr.items() if k != "risk"}, "reasons": reasons[:3],
    }  # fmt: skip


def _groups(delivered: list[dict], orders: list[dict], key: str, exc_ids: set) -> list[dict]:
    out = []
    for name in sorted({o[key] for o in delivered if o[key]}):
        group = [o for o in delivered if o[key] == name]
        if len(group) < MIN_GROUP:
            continue
        flags = [x for x in (_late(o) for o in group) if x is not None]
        t = [o["transit"] for o in group]
        every = [o for o in orders if o[key] == name]
        row = {
            key: name, "delivered": len(group), "open": sum(o["status"] != "done" for o in every),
            "on_time_rate": _r(1 - sum(flags) / len(flags), 3) if flags else None,
            "median_days": _pct(t, 50), "p10_days": _pct(t, 10), "p90_days": _pct(t, 90),
            "exception_rate": _rate([o["id"] in exc_ids for o in every]),
        }  # fmt: skip
        if key == "route":
            planned = [o["planned"] for o in group if o["planned"] is not None]
            row["promised_days"] = _r(np.median(planned)) if planned else None
        out.append(row)
    return out


def _evaluate(delivered: list[dict]) -> dict:
    """Back-test: estimate each of the newest 30% from orders delivered before it was placed."""
    ordered = sorted(delivered, key=lambda o: o["created"])
    test = ordered[int(len(ordered) * 0.7) :]
    hits, err, base_err, scores, base_scores, truth = [], [], [], [], [], []
    for o in test:
        pool = [p for p in ordered if p["delivered"] < o["created"]]
        if len(pool) < MIN_DELIVERED:
            continue
        ref = reference_class(pool, o["origin"], o["destination"], o["carrier"], o["service"])
        if ref is None:
            continue
        t = [m["transit"] for m in ref["members"]]
        p10, p50, p90 = np.percentile(t, [10, 50, 90])
        hits.append(p10 <= o["transit"] <= p90)
        err.append(abs(o["transit"] - p50))
        base_err.append(abs(o["transit"] - float(np.median([p["transit"] for p in pool]))))
        late, lr = _late(o), late_risk(pool, o, o["created"])
        if late is not None and lr is not None:
            truth.append(late)
            scores.append(lr["risk"])
            mine = [_late(p) for p in pool if p["carrier"] == o["carrier"]]
            mine = [x for x in mine if x is not None]
            base_scores.append(sum(mine) / len(mine) if mine else 0.0)
    if len(hits) < 10:
        return {"available": False, "reason": "Not enough delivered orders yet to back-test the estimates."}
    out = {
        "available": True, "tested": len(hits), "coverage_p10_p90": _r(np.mean(hits), 3),
        "mae_days": _r(np.mean(err), 2), "baseline_mae_days": _r(np.mean(base_err), 2),
        "risk_auc": None, "baseline_auc": None,
    }  # fmt: skip
    if len(set(truth)) == 2:
        out["risk_auc"] = _r(roc_auc_score(truth, scores), 3)
        out["baseline_auc"] = _r(roc_auc_score(truth, base_scores), 3)
    return out


def compute(db: Session, project_id: str, now: datetime) -> dict:
    now = naive_utc(now)
    orders = load_orders(db, project_id)
    delivered = [o for o in orders if o["transit"] is not None]
    if len(delivered) < MIN_DELIVERED:
        return {
            "available": False,
            "reason": f"{len(delivered)} delivered orders so far. Delivery times need at least {MIN_DELIVERED}; "
            "send stage updates with the event API (Live feed tab) or load the demo orders.",
            "counts": {"orders": len(orders), "delivered": len(delivered)},
        }

    timeline: dict[str, dict[str, datetime]] = {}
    exc_ext: set[str] = set()
    for ext, stage, at in db.execute(
        select(IngestedEvent.external_id, IngestedEvent.stage, IngestedEvent.occurred_at).where(
            IngestedEvent.project_id == project_id
        )
    ):
        at = naive_utc(at)
        if stage == "exception":
            exc_ext.add(ext)
        st = timeline.setdefault(ext, {})
        if stage not in st or at < st[stage]:
            st[stage] = at
    exc_ids = {o["id"] for o in orders if o["external_id"] in exc_ext or o["stage"] == "exception"}

    def window(start: datetime, end: datetime) -> list[bool]:
        return [x for x in (_late(o) for o in delivered if start <= o["delivered"] < end) if x is not None]

    recent, before = window(now - WINDOW, now), window(now - 2 * WINDOW, now - WINDOW)
    all_flags = [x for x in (_late(o) for o in delivered) if x is not None]
    transit = [o["transit"] for o in delivered]

    weekly = []
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    for w in range(WEEKS, 0, -1):
        start = week_start - timedelta(weeks=w)
        flags = window(start, start + timedelta(weeks=1))
        weekly.append({
            "week": start.date().isoformat(), "delivered": len(flags),
            "on_time_rate": _r(1 - sum(flags) / len(flags), 3) if flags else None,
        })  # fmt: skip

    dwell = []
    for a, b in zip(FLOW, FLOW[1:], strict=False):
        hours = [
            (tl[b] - tl[a]).total_seconds() / 3600 for tl in timeline.values() if a in tl and b in tl and tl[b] >= tl[a]
        ]
        dwell.append({"stage": a, "label": FLOW_LABELS[a], "n": len(hours),
                      "median_hours": _pct(hours, 50), "p85_hours": _pct(hours, 85)})  # fmt: skip

    open_orders = [o for o in orders if o["status"] != "done"]
    risks = [_open_risk(o, delivered, now, o["id"] in exc_ids) for o in open_orders if o["origin"] and o["destination"]]
    risks.sort(key=lambda r: (-(r["risk"] if r["risk"] is not None else -1), r["due"] or "9999"))

    routes = _groups(delivered, orders, "route", exc_ids)
    routes.sort(key=lambda r: (r["on_time_rate"] if r["on_time_rate"] is not None else 2, -r["delivered"]))
    carriers = _groups(delivered, orders, "carrier", exc_ids)
    carriers.sort(key=lambda c: -(c["on_time_rate"] or 0))

    return {
        "available": True,
        "counts": {
            "orders": len(orders),
            "delivered": len(delivered),
            "open": len(open_orders),
            "exceptions_open": sum(o["id"] in exc_ids and o["status"] != "done" for o in orders),
            "high_risk": sum(r["level"] == "high" for r in risks),
        },  # fmt: skip
        "on_time": {
            "value": _rate([not x for x in recent]),
            "previous": _rate([not x for x in before]),
            "all_time": _rate([not x for x in all_flags]),
            "recent_delivered": len(recent),
        },  # fmt: skip
        "transit": {"p50": _pct(transit, 50), "p85": _pct(transit, 85), "p95": _pct(transit, 95)},
        "weekly": weekly,
        "dwell": dwell,
        "carriers": carriers,
        "routes": routes[:12],
        "route_count": len(routes),
        "at_risk": risks[:25],
        "evaluation": _evaluate(delivered),
    }


def check(db: Session, project_id: str, origin: str, destination: str, carrier: str, due: date | None,
          today: date, service: str = "") -> dict:  # fmt: skip
    """Write-time estimate for an order that hasn't been placed yet."""
    pool = [o for o in load_orders(db, project_id) if o["transit"] is not None]
    planned = (due - today).days if due else None
    return estimate(pool, origin.strip(), destination.strip(), carrier.strip(), planned, service.strip().lower())
