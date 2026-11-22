"""Eleven weeks of simulated service jobs for the Serve demo: a home-services company in Bengaluru.

The company and technicians are made up. Each technician's day is simulated job by job
(travel between areas, overruns pushing later visits back), so the patterns are the kind
real field-service data shows:
- AC repairs are booked as 2-hour jobs but usually take nearly 3.
- Deepa is the fastest technician and the most booked, so her busy days run late.
- Manoj works slowly; Whitefield and Electronic City are far, so visits there arrive late more.
- Afternoon windows are missed more often than morning ones, because earlier jobs overrun.
- Repairs get rescheduled more (parts not in the van); a few jobs are cancelled.
Times are stored in UTC; appointment windows are local (India, UTC+5:30).
"""

import random
from datetime import date, datetime, timedelta

import numpy as np

IST = timedelta(hours=5, minutes=30)
AREAS = ["Indiranagar", "Koramangala", "HSR Layout", "Jayanagar", "Whitefield", "Hebbal", "Electronic City"]
FAR = {"Whitefield", "Electronic City"}
SLOTS = [(9, 11), (11, 13), (14, 16), (16, 18)]
SLOT_WEIGHTS = [0.3, 0.3, 0.25, 0.15]
# name: (booked estimate in hours, typical real hours, chance of a reschedule)
SERVICES = {
    "AC service": (1.5, 1.4, 0.02),
    "AC repair": (2.0, 2.8, 0.12),
    "Washing machine repair": (1.5, 1.7, 0.10),
    "Water purifier install": (1.0, 1.0, 0.02),
    "Electrical fault": (1.0, 1.3, 0.05),
    "Plumbing leak": (1.5, 1.6, 0.06),
    "Appliance install": (2.0, 1.9, 0.03),
}
SERVICE_WEIGHTS = [0.2, 0.18, 0.14, 0.12, 0.14, 0.12, 0.1]
# name: (speed, how often customers book them, home areas)
TECHNICIANS = {
    "Deepa": (0.85, 0.32, {"Indiranagar", "Koramangala", "HSR Layout"}),
    "Ravi": (1.0, 0.2, {"Jayanagar", "HSR Layout", "Koramangala"}),
    "Imran": (1.0, 0.18, {"Whitefield", "Indiranagar"}),
    "Manoj": (1.3, 0.15, {"Hebbal", "Indiranagar"}),
    "Kavya": (0.95, 0.15, {"Electronic City", "HSR Layout", "Jayanagar"}),
}
ISSUES = {
    "AC service": "Routine service: filters, coil cleaning and gas check.",
    "AC repair": "AC not cooling; outdoor unit makes a rattling noise.",
    "Washing machine repair": "Drum doesn't spin and the machine shows an error code.",
    "Water purifier install": "New purifier to mount in the kitchen and connect to the inlet.",
    "Electrical fault": "Two sockets in the bedroom stopped working; breaker trips.",
    "Plumbing leak": "Leak under the kitchen sink; water collecting in the cabinet.",
    "Appliance install": "Install a new chimney and connect the duct.",
}


def _utc(day: date, hour: float) -> datetime:
    """A local (IST) time on `day` as naive UTC."""
    return datetime(day.year, day.month, day.day) + timedelta(hours=hour) - IST


def _pick(r: random.Random, names, weights):
    return r.choices(list(names), weights=list(weights))[0]


def generate_jobs(today: datetime, days: int = 75, ahead: int = 6, seed: int = 21) -> list[dict]:
    """`today` is naive UTC. Returns staged rows: past jobs finished, upcoming ones booked."""
    r = random.Random(seed)
    rng = np.random.default_rng(seed)
    local_today = (today + IST).date()
    first = local_today - timedelta(days=days)

    # 1. Book jobs onto days; a rescheduled job moves to a later day with the same slot.
    plan: dict[date, list[dict]] = {}
    number = 5000
    for d in range(days + ahead + 1):
        day = first + timedelta(days=d)
        rate = 3.0 if day.weekday() == 6 else 7.5 if day.weekday() == 5 else 6.5
        for _ in range(int(rng.poisson(rate))):
            number += 1
            area = r.choice(AREAS)
            local = [t for t, (_, _, home) in TECHNICIANS.items() if area in home]
            pool = local if local and r.random() > 0.2 else list(TECHNICIANS)
            tech = _pick(r, pool, [TECHNICIANS[t][1] for t in pool])
            service = _pick(r, SERVICES, SERVICE_WEIGHTS)
            slot = _pick(r, SLOTS, SLOT_WEIGHTS)
            job = {
                "number": number, "area": area, "tech": tech, "service": service, "slot": slot,
                "urgent": r.random() < 0.15, "day": day, "original": None, "events": [],
            }  # fmt: skip
            start = _utc(day, slot[0])
            job["booked"] = start - timedelta(hours=r.uniform(4, 24 * 8))
            fate = r.random()
            if fate < 0.03:
                job["cancel_at"] = start - timedelta(hours=r.uniform(2, 30))
            elif fate < 0.03 + SERVICES[service][2]:
                job["resched_at"] = start - timedelta(hours=r.uniform(1, 20))
                job["original"] = (day, slot)
                job["day"] = day + timedelta(days=r.randint(1, 3))
            plan.setdefault(job["day"], []).append(job)

    # 2. Simulate each technician's day in window order.
    rows = []
    for day in sorted(plan):
        by_tech: dict[str, list[dict]] = {}
        for job in plan[day]:
            by_tech.setdefault(job["tech"], []).append(job)
        for tech, jobs in by_tech.items():
            speed, _, home = TECHNICIANS[tech]
            free = _utc(day, 8.75)
            for job in sorted(jobs, key=lambda j: j["slot"]):
                rows.append(_finish(r, rng, job, tech, speed, home, free, today))
                if "done" in job:
                    free = job["done"]
    return rows


def _finish(r, rng, job: dict, tech: str, speed: float, home: set, free: datetime, today: datetime) -> dict:
    est, typical, _ = SERVICES[job["service"]]
    day, (a, b) = job["day"], job["slot"]
    w_start, w_end = _utc(day, a), _utc(day, b)
    ev = [("booked", job["booked"]), ("scheduled", job["booked"] + timedelta(minutes=r.uniform(5, 60)))]
    if job.get("cancel_at"):
        ev.append(("cancelled", max(job["cancel_at"], ev[-1][1] + timedelta(minutes=5))))
    else:
        if job["original"]:
            moved = max(job["resched_at"], ev[-1][1] + timedelta(minutes=5))
            ev += [("rescheduled", moved), ("scheduled", moved + timedelta(minutes=r.uniform(20, 120)))]
        assigned = max(_utc(day - timedelta(days=1), 19), ev[-1][1] + timedelta(minutes=10))
        ev.append(("assigned", assigned))
        travel = 25 + (20 if job["area"] not in home else 0) + (25 if job["area"] in FAR else 0)
        travel = timedelta(minutes=travel * float(rng.lognormal(0, 0.25)))
        arrive = max(w_start - timedelta(minutes=r.uniform(0, 15)), free + travel)
        hours = typical * speed * float(rng.lognormal(0, 0.25))
        job["done"] = arrive + timedelta(hours=hours)
        ev += [("en_route", arrive - travel), ("on_site", arrive), ("done", job["done"])]
    ev = [(s, t.replace(microsecond=0)) for s, t in ev if t <= today]
    attrs = {
        "service_type": job["service"], "area": job["area"], "technician": tech,
        "window_start": w_start.isoformat() + "Z", "window_end": w_end.isoformat() + "Z",
        "estimate_hours": est,
    }  # fmt: skip
    if job["original"]:
        o_day, (oa, ob) = job["original"]
        attrs["original_window_start"] = _utc(o_day, oa).isoformat() + "Z"
    return {
        "external_id": f"JOB-{job['number']}",
        "title": f"Job #{job['number']} · {job['service']} · {job['area']}",
        "description": ISSUES[job["service"]],
        "owner": tech,
        "priority": "high" if job["urgent"] else "medium",
        "due": day,
        "item_type": "job",
        "attributes": attrs,
        "events": ev,
    }
