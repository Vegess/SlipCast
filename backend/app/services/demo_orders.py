"""Four months of simulated orders for the Ship demo: a D2C brand shipping across India.

The carriers and the brand are made up. The patterns are the kind real order data shows, so
the charts and estimates have something genuine to find:
- Remote destinations (Guwahati, Port Blair) are promised too few days and often arrive late.
- MetroPost is cheap and slow, with more exceptions; SwiftLine is fast in the metros but
  struggles on remote routes; Kite Logistics got slower over the last six weeks.
- Orders dispatched on a Sunday lose a day, and heavy parcels take a little longer.
- A sale in the last 8 days doubled orders, so more are on the way than usual.
"""

import random
from datetime import datetime, timedelta

import numpy as np

REGIONS = {
    "Chennai": "south", "Bengaluru": "south", "Hyderabad": "south", "Kochi": "south",
    "Mumbai": "west", "Pune": "west", "Ahmedabad": "west",
    "Delhi": "north", "Jaipur": "north", "Lucknow": "north",
    "Kolkata": "east", "Guwahati": "remote", "Port Blair": "remote",
}  # fmt: skip
WAREHOUSES = {"Chennai": 0.55, "Mumbai": 0.45}
DESTINATIONS = {
    "Chennai": 9, "Bengaluru": 12, "Hyderabad": 9, "Kochi": 5, "Mumbai": 11, "Pune": 7,
    "Ahmedabad": 5, "Delhi": 12, "Jaipur": 4, "Lucknow": 4, "Kolkata": 7, "Guwahati": 3, "Port Blair": 2,
}  # fmt: skip
# Typical days door to door, by distance tier: same city, same region, across regions, remote.
BASE_DAYS = [1.0, 2.2, 3.8, 6.5]
PROMISE = {"standard": [2, 3, 5, 6], "express": [1, 2, 3, 5]}
CARRIERS = {
    #               speed, spread, exception rate, extra days on remote routes
    "SwiftLine": (0.85, 0.15, 0.02, 1.8),
    "Coastal Express": (1.0, 0.18, 0.03, 0.3),
    "MetroPost": (1.25, 0.3, 0.08, 0.8),
    "Kite Logistics": (1.0, 0.2, 0.04, 0.5),
}
CHOICE = {
    "express": {"SwiftLine": 0.5, "Coastal Express": 0.4, "Kite Logistics": 0.1},
    "standard": {"SwiftLine": 0.2, "Coastal Express": 0.2, "MetroPost": 0.35, "Kite Logistics": 0.25},
}
PRODUCTS = ["Cotton kurta", "Steel bottle", "Desk lamp", "Bedsheet set", "Running shoes", "Ceramic mugs",
            "Yoga mat", "Backpack", "Phone stand", "Spice box", "Wall clock", "Throw cushions"]  # fmt: skip


def tier(origin: str, destination: str) -> int:
    if origin == destination:
        return 0
    if REGIONS[destination] == "remote":
        return 3
    return 1 if REGIONS[origin] == REGIONS[destination] else 2


def _pick(r: random.Random, weights: dict[str, float]) -> str:
    return r.choices(list(weights), weights=list(weights.values()))[0]


def _business(at: datetime, earliest: int = 9, latest: int = 20) -> datetime:
    """Moves a warehouse action into working hours."""
    if at.hour < earliest:
        return at.replace(hour=earliest, minute=at.minute)
    if at.hour >= latest:
        return (at + timedelta(days=1)).replace(hour=earliest, minute=at.minute)
    return at


def generate_orders(today: datetime, days: int = 120, seed: int = 11) -> list[dict]:
    r = random.Random(seed)
    rng = np.random.default_rng(seed)
    start = (today - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    drift_from = today - timedelta(days=42)
    sale_from = today - timedelta(days=8)
    rows: list[dict] = []
    number = 10400
    for d in range(days + 1):
        day = start + timedelta(days=d)
        rate = (3.2 if day.weekday() < 5 else 4.4) * (2.2 if day >= sale_from.replace(hour=0) else 1)
        volume = int(rng.poisson(rate))  # weekend shoppers, and the sale
        for _ in range(volume):
            created = day + timedelta(hours=r.uniform(7, 23.5))
            if created > today:
                continue
            number += 1
            origin = _pick(r, WAREHOUSES)
            dest = _pick(r, DESTINATIONS)
            service = "express" if r.random() < 0.22 else "standard"
            carrier = _pick(r, CHOICE[service])
            speed, spread, exc_rate, remote_extra = CARRIERS[carrier]
            if carrier == "Kite Logistics" and created >= drift_from:
                speed *= 1.35
            t = tier(origin, dest)
            items = r.choices([1, 2, 3, 4], weights=[55, 28, 12, 5])[0]
            weight = round(float(min(18, rng.lognormal(0.2, 0.7)) * items), 1)
            value = int(round(r.uniform(350, 4200) * items, -1))

            packed = _business(created + timedelta(hours=r.uniform(2, 18)))
            dispatched = _business(packed + timedelta(hours=r.uniform(2, 9)), latest=21)
            in_transit = dispatched + timedelta(hours=r.uniform(1, 5))
            total = BASE_DAYS[t] * (0.6 if service == "express" else 1.0) * speed
            total *= float(rng.lognormal(0, spread))
            total += remote_extra if t == 3 else 0
            total += 0.5 if weight > 10 else 0
            total += 1 if dispatched.weekday() == 6 else 0
            exception = r.random() < exc_rate
            if exception:
                total += r.uniform(1.5, 4)
            delivered = created + timedelta(days=max(total, 0.45))
            delivered = delivered.replace(hour=r.randint(10, 19), minute=r.randint(0, 59))
            if delivered <= in_transit + timedelta(hours=3):
                delivered = in_transit + timedelta(hours=r.uniform(4, 8))
            out = delivered - timedelta(hours=r.uniform(2, 6))
            if out <= in_transit:
                out = in_transit + (delivered - in_transit) / 2

            events = [("ordered", created), ("packed", packed), ("dispatched", dispatched),
                      ("in_transit", in_transit)]  # fmt: skip
            if exception:
                hit = in_transit + (out - in_transit) * r.uniform(0.2, 0.6)
                events += [("exception", hit), ("in_transit", hit + (out - hit) * r.uniform(0.3, 0.7))]
            events += [("out_for_delivery", out), ("delivered", delivered)]
            events = [(s, at.replace(microsecond=0)) for s, at in events if at <= today]

            lines = f"{items} item{'s' if items > 1 else ''}: " + ", ".join(r.sample(PRODUCTS, items))
            rows.append({
                "external_id": f"ORD-{number}",
                "title": f"Order #{number} · {origin} → {dest}",
                "description": f"{lines}. {weight} kg, ₹{value:,}. {service.capitalize()} delivery via {carrier}.",
                "owner": carrier,
                "priority": "high" if service == "express" else "medium",
                "due": (created + timedelta(days=PROMISE[service][t])).date(),
                "item_type": "order",
                "attributes": {
                    "origin": origin, "destination": dest, "carrier": carrier, "service": service,
                    "weight_kg": weight, "order_value": value, "items": items,
                },
                "events": events,
            })  # fmt: skip
    return rows
