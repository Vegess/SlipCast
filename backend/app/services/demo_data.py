"""Generates six months of realistic ticket history for a demo project.

The generator bakes in patterns real teams show (payments bugs are slow, vague
tickets slip, an overloaded owner finishes later) so every chart and model has
something genuine to find.
"""

import random
from datetime import datetime, timedelta

import numpy as np

TEAM = ["Priya", "Arun", "Meera", "Karthik", "Divya", "Rahul"]

TOPICS = {
    "payments": {
        "comps": [
            "checkout",
            "invoice generator",
            "refund flow",
            "Stripe webhook handler",
            "subscription renewal",
            "billing page",
        ],
        "things": ["invoice total", "tax amount", "refund status", "proration", "card details"],
        "owners": ["Arun", "Arun", "Karthik"],
        "slow": 1.6,
    },
    "auth": {
        "comps": [
            "login form",
            "password reset",
            "SSO callback",
            "session handling",
            "OAuth consent screen",
            "two-factor setup",
        ],
        "things": ["session token", "redirect URL", "OTP code", "user role"],
        "owners": ["Karthik", "Rahul"],
        "slow": 1.2,
    },
    "onboarding": {
        "comps": [
            "signup page",
            "onboarding wizard",
            "welcome email",
            "trial setup",
            "workspace setup checklist",
            "invite teammates step",
        ],
        "things": ["progress indicator", "trial end date", "workspace name", "invite link"],
        "owners": ["Priya", "Meera"],
        "slow": 0.9,
    },
    "reporting": {
        "comps": [
            "usage dashboard",
            "CSV export",
            "revenue chart",
            "analytics report",
            "scheduled report email",
            "metrics widget",
        ],
        "things": ["date range filter", "chart legend", "export columns", "monthly totals"],
        "owners": ["Meera", "Divya"],
        "slow": 1.0,
    },
    "notifications": {
        "comps": [
            "email notification",
            "Slack alert",
            "push notification",
            "daily digest",
            "reminder scheduler",
        ],
        "things": ["unsubscribe link", "alert threshold", "digest timing", "message template"],
        "owners": ["Divya", "Rahul"],
        "slow": 0.9,
    },
    "infra": {
        "comps": [
            "database migration",
            "CI pipeline",
            "Redis cache",
            "job queue",
            "logging pipeline",
            "Kubernetes deployment",
        ],
        "things": ["connection pool", "build time", "cache hit rate", "worker memory"],
        "owners": ["Arun", "Karthik"],
        "slow": 1.4,
    },
}

CONTEXT = {
    "payments": [
        "Affects billing for paying customers: invoices, refunds and Stripe charges.",
        "Payment flow issue; revenue and invoice accuracy are at stake.",
        "Touches the billing service, Stripe integration and refund ledger.",
    ],
    "auth": [
        "Affects login and account security: sessions, SSO and password reset.",
        "Authentication flow; users may be locked out or see the wrong account.",
        "Touches the identity service, OAuth tokens and two-factor login.",
    ],
    "onboarding": [
        "Affects new signups during the trial and first-run onboarding.",
        "Onboarding funnel; activation rate for new workspaces depends on this.",
        "Touches signup, the setup wizard and welcome emails for trial users.",
    ],
    "reporting": [
        "Affects dashboards, charts and exported analytics reports.",
        "Reporting accuracy; customers use these metrics and exports monthly.",
        "Touches the analytics warehouse, chart rendering and CSV exports.",
    ],
    "notifications": [
        "Affects email, Slack and push notifications sent to users.",
        "Notification delivery; reminders and digests may be missed.",
        "Touches the notification service, templates and delivery scheduler.",
    ],
    "infra": [
        "Affects infrastructure: database, CI, cache and deployment pipeline.",
        "Platform reliability; deploys, queues and database load depend on this.",
        "Touches Kubernetes, Redis, the job queue and database migrations.",
    ],
}
PLANS = ["Starter", "Pro", "Business", "Enterprise"]

KIND_WEIGHTS = {"bug": 0.35, "feature": 0.3, "tech_debt": 0.2, "support": 0.15}
BASE_CYCLE = {"bug": 2.5, "feature": 6.0, "tech_debt": 5.0, "support": 1.2}
PLANNED = {"bug": (3, 9), "feature": (7, 21), "tech_debt": (6, 18), "support": (1, 5)}
ORGS = ["Acme Corp", "Globex", "Initech", "Umbrella Health", "Stark Retail", "Wayne Logistics"]


def _title_and_desc(r: random.Random, kind: str, topic: str, vague: bool, risky: bool) -> tuple[str, str]:
    t = TOPICS[topic]
    comp, thing = r.choice(t["comps"]), r.choice(t["things"])
    Comp = comp[0].upper() + comp[1:]
    if vague:
        title = r.choice(
            [
                f"Fix {comp} stuff",
                f"{Comp} issue",
                f"Misc {comp} changes",
                f"Look into {comp}",
                f"Some issues with {comp}",
            ]
        )
        desc = r.choice(
            [
                "",
                "",
                f"{Comp} not great, please check.",
                f"See Slack thread about {comp}.",
                f"Customer complained about {comp}.",
            ]
        )
        return title, desc

    if kind == "bug":
        title = r.choice(
            [
                f"{Comp} fails when {thing} is empty",
                f"{Comp} shows wrong {thing}",
                f"Error 500 on {comp} for some accounts",
                f"{Comp} times out for large accounts",
                f"Duplicate {thing} created after {comp} retry",
            ]
        )
        desc = (
            f"When the {thing} is changed, the {comp} returns an error instead of saving.\n\n"
            f"Steps to reproduce:\n1. Open the {comp}\n2. Update the {thing}\n3. Click save\n\n"
            f"Expected result: the change is saved.\nActual result: error toast and nothing saved."
        )
    elif kind == "feature":
        title = r.choice(
            [
                f"Add {thing} to {comp}",
                f"Allow admins to configure {thing} in {comp}",
                f"Support bulk actions in {comp}",
                f"Show {thing} on {comp}",
            ]
        )
        desc = (
            f"As an account admin, I want to manage the {thing} from the {comp} so that I don't "
            f"need to contact support.\n\nAcceptance criteria:\n- [ ] {Comp} shows the {thing}\n"
            f"- [ ] Admins can edit it\n- [ ] Change is recorded in the audit log"
        )
    elif kind == "tech_debt":
        title = r.choice(
            [
                f"Refactor {comp} module",
                f"Migrate {comp} to the new service layer",
                f"Remove legacy {comp} code",
                f"Add integration tests for {comp}",
                f"Upgrade dependencies used by {comp}",
            ]
        )
        desc = (
            f"The {comp} code has grown hard to change and has little test coverage. "
            f"Plan: split responsibilities, add tests around {thing}, then delete dead paths.\n\n"
            f"Definition of done: tests pass in CI and no behaviour changes."
        )
    else:
        org = r.choice(ORGS)
        title = r.choice(
            [
                f"{org} cannot access {comp}",
                f"Question from {org} about {thing}",
                f"Help {org} with {comp} setup",
                f"{org} requests {thing} correction",
            ]
        )
        desc = (
            f"Support ticket: {org} reports a problem with the {comp} related to {thing}. "
            f"Please confirm the account settings and reply to the customer within one day."
        )
    org, plan = r.choice(ORGS), r.choice(PLANS)
    desc = f"{r.choice(CONTEXT[topic])} Seen by {org} on the {plan} plan.\n\n" + desc
    if risky:
        title = r.choice(["Flaky: ", "Intermittent: ", "Investigate: "]) + title
        desc += "\n\nNote: happens intermittently, root cause unknown."
    return title, desc


def generate(today: datetime, n: int = 420, days: int = 182, seed: int = 42) -> list[dict]:
    r = random.Random(seed)
    np_r = np.random.default_rng(seed)
    start = today - timedelta(days=days)
    tickets: list[dict] = []

    for _ in range(n):
        kind = r.choices(list(KIND_WEIGHTS), weights=list(KIND_WEIGHTS.values()))[0]
        topic = r.choice(list(TOPICS))
        vague = r.random() < 0.14
        risky = (not vague) and r.random() < 0.12
        title, desc = _title_and_desc(r, kind, topic, vague, risky)

        owner = "" if r.random() < 0.04 else (r.choice(TOPICS[topic]["owners"]) if r.random() < 0.8 else r.choice(TEAM))
        priority = r.choices(["high", "medium", "low"], weights=[0.25, 0.5, 0.25])[0]

        created = min(start + timedelta(days=r.uniform(0, days)), today - timedelta(hours=1))
        lo, hi = PLANNED[kind]
        due = None if r.random() < 0.08 else (created + timedelta(days=r.randint(lo, hi))).date()

        wait = np_r.exponential(0.8 if priority == "high" else 3.0)
        cycle = BASE_CYCLE[kind] * TOPICS[topic]["slow"] * float(np_r.lognormal(0, 0.55))
        cycle *= 1.8 if vague else 1.0
        cycle *= 1.6 if risky else 1.0
        cycle *= 1.35 if owner == "Arun" else 1.0
        cycle *= 1.25 if not owner else 1.0

        events = [(None, "planned", created)]
        started = created + timedelta(days=wait)
        events.append(("planned", "in_progress", started))
        t = started
        if r.random() < 0.08:  # bounced back to planned, then picked up again
            back = t + timedelta(days=cycle * 0.3)
            events += [
                ("in_progress", "planned", back),
                ("planned", "in_progress", back + timedelta(days=r.uniform(1, 4))),
            ]
            t = events[-1][2]
            cycle *= 0.8
        blocked_p = 0.3 if topic == "infra" else 0.15
        if r.random() < blocked_p:
            b_at = t + timedelta(days=cycle * 0.4)
            b_len = float(np_r.exponential(3.0)) + 0.5
            events += [
                ("in_progress", "blocked", b_at),
                ("blocked", "in_progress", b_at + timedelta(days=b_len)),
            ]
            cycle += b_len
        completed = started + timedelta(days=cycle)
        events.append(("in_progress", "done", completed))

        events = [e for e in events if e[2] <= today]
        status = events[-1][1]
        labelled = r.random() < 0.85
        tickets.append(
            {
                "title": title,
                "description": desc,
                "owner": owner,
                "priority": priority,
                "due": due,
                "status": status,
                "created_at": created,
                "started_at": started if started <= today else None,
                "completed_at": completed if status == "done" else None,
                "kind": kind if labelled else None,
                "kind_source": "label" if labelled else "",
                "events": events,
            }
        )

    # near-duplicates: the same problem reported twice
    recent = [t for t in tickets if t["description"] and t["created_at"] > today - timedelta(days=40)]
    originals = r.sample(recent, min(14, len(recent)))
    for o in originals:
        created = o["created_at"] + timedelta(days=r.uniform(2, 20))
        if created > today:
            continue
        tickets.append(
            {
                **o,
                "title": r.choice(["", "Again: ", "Reported again: "]) + o["title"],
                "description": "Another customer hit this. " + o["description"],
                "status": "planned",
                "created_at": created,
                "started_at": None,
                "completed_at": None,
                "due": (created + timedelta(days=r.randint(3, 10))).date(),
                "events": [(None, "planned", created)],
            }
        )
    tickets.sort(key=lambda t: t["created_at"])
    return tickets
