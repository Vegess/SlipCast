"""The advice layer: the LLM only turns computed findings into advice.

Single, grounded calls, never RAG or agents. Every LLM suggestion is validated: it
must cite at least one real finding ID and may only use numbers that appear in the
findings (small integers up to 5 are allowed for phrasing such as "pick 2 tickets").
If there is no API key, or every suggestion fails, rule-based suggestions are used.
"""

import hashlib
import json
import logging
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.config import get_settings
from app.services.findings import Finding

log = logging.getLogger("slipcast.advice")
NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")
SMALL_INTS = {str(i) for i in range(6)}


class LLM(Protocol):
    def complete(self, system: str, user: str, json_mode: bool = True) -> str: ...


class GroqLLM:
    """Minimal Groq client over the OpenAI-compatible chat API (stdlib only)."""

    name = "groq"

    def __init__(self, api_key: str, model: str, url: str, timeout: float = 25.0):
        self.api_key, self.model, self.url, self.timeout = api_key, model, url, timeout

    def complete(self, system: str, user: str, json_mode: bool = True) -> str:
        body = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (fixed https URL)
            return json.loads(resp.read())["choices"][0]["message"]["content"]


def get_llm() -> LLM | None:
    """The configured LLM, or None when no key is set. Tests replace this."""
    s = get_settings()
    return GroqLLM(s.groq_api_key, s.groq_model, s.groq_url) if s.groq_api_key else None


# ---------- validation ----------
def numbers_in(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUMBER.findall(text)}


def allowed_numbers(findings: list[Finding]) -> set[str]:
    allowed = set(SMALL_INTS)
    for f in findings:
        for n in numbers_in(f.text):
            allowed.add(n)
            if "." in n:
                allowed.add(n.rstrip("0").rstrip("."))
            allowed.add(str(round(float(n))))
    return allowed


def validate(suggestion: dict, findings: list[Finding], allowed: set[str]) -> str | None:
    """Return why a suggestion is rejected, or None if it is grounded."""
    ids = {f.id for f in findings}
    cited = suggestion.get("finding_ids")
    if not isinstance(cited, list) or not cited:
        return "cites no finding"
    bad = [c for c in cited if c not in ids]
    if bad:
        return f"cites unknown finding {bad[0]}"
    for key in ("title", "action"):
        if not isinstance(suggestion.get(key), str) or not suggestion[key].strip():
            return f"missing {key}"
    invented = sorted(numbers_in(f"{suggestion['title']} {suggestion['action']}") - allowed)
    if invented:
        return f"uses a number not in the findings ({invented[0]})"
    return None


# ---------- suggestions ----------
@dataclass
class AdviceResult:
    provider: str
    suggestions: list[dict]
    llm_called: bool = False
    error: str | None = None
    generated: int = 0
    accepted: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def rejected(self) -> int:
        return self.generated - self.accepted

    def validation(self) -> dict | None:
        if not self.llm_called:
            return None
        return {
            "generated": self.generated,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "problems": self.problems,
        }


def _key(source: str, title: str) -> str:
    return hashlib.sha1(f"{source}:{title.strip().lower()}".encode()).hexdigest()[:16]


SYSTEM = (
    "You are a delivery coach for a software team. You receive numbered findings computed by "
    "statistical models. Write 3 to 5 concrete actions for this week. Rules: use ONLY facts in the "
    "findings; every suggestion must cite the IDs of the findings it addresses; never write a number "
    "that does not appear in the findings (you may use 1 to 5 when counting actions); do not invent "
    "names, tickets or dates. Reply with JSON only: "
    '{"suggestions": [{"title": str, "action": str, "finding_ids": [str], "impact": "high"|"medium"|"low"}]}'
)


def _findings_prompt(findings: list[Finding]) -> str:
    return "Findings:\n" + "\n".join(f"{f.id} [{f.severity}] {f.text}" for f in findings)


RULES: dict[str, Callable[[Finding], tuple[str, str, str]]] = {
    "overdue": lambda f: (
        "Triage the overdue tickets today",
        (
            f"Walk through the {f.data['count']} overdue tickets with their owners: re-plan the ones still worth "
            "doing with an honest date and close the rest."
            if f.data["count"] > 1
            else "Agree with its owner whether the overdue ticket still matters: re-plan it honestly or close it."
        ),
        "high",
    ),
    "blocked": lambda f: (
        "Unblock before starting anything new",
        (
            f"Give each of the {f.data['count']} blocked tickets a named person who will chase the blocker"
            if f.data["count"] > 1
            else "Give the blocked ticket a named person who will chase the blocker"
        )
        + ", and raise any external dependency at stand-up.",
        "high",
    ),
    "overload": lambda f: (
        f"Rebalance {f.data['owner']}'s queue",
        f"{f.data['owner']} holds {f.data['count']} open tickets. Move the ones nobody has started to "
        "teammates with lighter queues.",
        "medium",
    ),
    "aging": lambda f: (
        "Swarm on the oldest work in progress",
        "Pair on the tickets that are past the usual finish age before pulling new work; old tickets rarely "
        "close on their own.",
        "high",
    ),
    "high_risk": lambda f: (
        "Re-plan the tickets most likely to slip",
        "Review the high slip-risk tickets: split large ones, give them more time, or tell stakeholders early.",
        "medium",
    ),
    "under_planned": lambda f: (
        "Align plans with how long similar work really took",
        "Use the reference-class ranges on the under-planned tickets to reset their due dates before they start.",
        "medium",
    ),
    "theme_late": lambda f: (
        "Investigate the theme that slips most",
        "Run a short retro on why work in this area misses its dates, and add buffer to its plans until it improves.",
        "medium",
    ),
    "throughput_drop": lambda f: (
        "Find out why throughput dropped",
        "Check for interruptions, blocked work or too much work in progress, and limit how many tickets each "
        "person starts.",
        "medium",
    ),
    "duplicates": lambda f: (
        "Merge duplicate tickets",
        "Review the likely duplicates and close or link them so effort is not split.",
        "low",
    ),
    "low_quality": lambda f: (
        "Tighten the weakest tickets before they start",
        "Add a clear description and acceptance criteria to the low-scoring tickets; vague tickets take longer.",
        "low",
    ),
}


def rule_suggestions(findings: list[Finding], limit: int = 5) -> list[dict]:
    out = []
    for f in findings:
        rule = RULES.get(f.kind)
        if rule is None:
            continue
        title, action, impact = rule(f)
        out.append(
            {
                "key": _key("rules", title),
                "title": title,
                "action": action,
                "finding_ids": [f.id],
                "impact": impact,
                "source": "rules",
            }
        )
        if len(out) == limit:
            break
    return out


def suggest(findings: list[Finding], llm: LLM | None) -> AdviceResult:
    if not findings:
        return AdviceResult("rules", [])
    if llm is None:
        return AdviceResult("rules", rule_suggestions(findings))
    allowed = allowed_numbers(findings)
    result = AdviceResult("groq", [], llm_called=True)
    try:
        raw = json.loads(llm.complete(SYSTEM, _findings_prompt(findings)))
        items = raw.get("suggestions", []) if isinstance(raw, dict) else []
        if not isinstance(items, list):
            items = []
    except (json.JSONDecodeError, urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as exc:
        log.warning("LLM call failed: %s", exc)
        result.error = "The AI service could not be reached or replied with something unreadable."
        items = []
    result.generated = len(items)
    for item in items[:5]:
        problem = validate(item, findings, allowed) if isinstance(item, dict) else "is not an object"
        if problem:
            title = item.get("title", "?") if isinstance(item, dict) else "?"
            result.problems.append(f"“{str(title)[:60]}” {problem}")
            continue
        impact = item.get("impact") if item.get("impact") in ("high", "medium", "low") else "medium"
        result.suggestions.append(
            {
                "key": _key("llm", item["title"]),
                "title": item["title"].strip(),
                "action": item["action"].strip(),
                "finding_ids": item["finding_ids"],
                "impact": impact,
                "source": "llm",
            }
        )
    result.problems += [f"extra suggestion {i + 6} ignored" for i in range(max(0, len(items) - 5))]
    result.accepted = len(result.suggestions)
    log.info("advice: generated=%d accepted=%d rejected=%d", result.generated, result.accepted, result.rejected)
    if not result.suggestions:
        result.error = result.error or "None of the AI suggestions passed the grounding check."
        result.provider = "rules"
        result.suggestions = rule_suggestions(findings)
    return result


# ---------- ticket rewrite ----------
REWRITE_SYSTEM = (
    "Rewrite a software ticket so it is clear and ready to work on. Keep every fact from the original and "
    "invent none: where information is missing, write a placeholder in square brackets such as [which "
    "browser?]. Use a specific title. For bugs include Steps to reproduce, Expected result and Actual "
    "result; otherwise include Acceptance criteria as a checklist. Reply with JSON only: "
    '{"title": str, "description": str}'
)


def template_rewrite(title: str, description: str, kind: str | None) -> dict:
    title = title.strip() or "[What needs to change, and where]"
    if len(title.split()) < 4:
        title = f"{title}: [what is wrong, and where]"
    context = description.strip() or "[What is happening, who is affected and why it matters]"
    if kind == "bug":
        body = (
            f"{context}\n\nSteps to reproduce:\n1. [First step]\n2. [Second step]\n\n"
            "Expected result: [what should happen]\nActual result: [what happens instead]"
        )
    else:
        body = (
            f"{context}\n\nAcceptance criteria:\n- [ ] [Observable outcome 1]\n- [ ] [Observable outcome 2]\n"
            "- [ ] [How it will be tested]"
        )
    return {"title": title[:140], "description": body[:5000], "provider": "template"}


def rewrite(title: str, description: str, kind: str | None, llm: LLM | None, privacy: bool) -> dict:
    if privacy or llm is None:
        return template_rewrite(title, description, kind)
    try:
        out = json.loads(
            llm.complete(REWRITE_SYSTEM, json.dumps({"title": title, "description": description, "type": kind}))
        )
        if isinstance(out.get("title"), str) and isinstance(out.get("description"), str) and out["title"].strip():
            return {
                "title": out["title"].strip()[:140],
                "description": out["description"].strip()[:5000],
                "provider": "groq",
            }
    except (json.JSONDecodeError, urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError, AttributeError):
        log.warning("LLM rewrite failed; using the template")
    return template_rewrite(title, description, kind)


# ---------- weekly status report ----------
REPORT_SYSTEM = (
    "Write a short weekly status report in Markdown for a software project using ONLY the numbered findings "
    "given. Sections: '## Summary' (2 sentences), '## Delivery', '## Risks', '## Focus next week' (3 bullets). "
    "Never write a number that is not in the findings. Do not mention finding IDs."
)


def template_report(project_name: str, findings: list[Finding], suggestions: list[dict]) -> str:
    by_kind = {f.kind: f for f in findings}
    risks = [f.text for f in findings if f.severity in ("critical", "warning")]
    delivery = [by_kind[k].text for k in ("forecast", "slowest_type", "throughput_drop") if k in by_kind]
    summary = (
        "Delivery is on track: nothing is overdue, blocked or aging."
        if not risks
        else f"There {'is' if len(risks) == 1 else 'are'} {len(risks)} open "
        f"risk{'s' if len(risks) != 1 else ''} to address this week."
    )
    lines = [f"# {project_name}: weekly status", "", "## Summary", summary, "", "## Delivery"]
    lines += [f"- {d}" for d in delivery] or ["- Not enough finished work yet to measure delivery."]
    lines += ["", "## Risks"] + ([f"- {r}" for r in risks] or ["- No significant risks found."])
    lines += ["", "## Focus next week"] + ([f"- {s['title']}" for s in suggestions[:3]] or ["- Keep the current pace."])
    return "\n".join(lines)


def status_report(project_name: str, findings: list[Finding], llm: LLM | None) -> tuple[str, str]:
    """Markdown report and its provider. LLM text that uses invented numbers is discarded."""
    fallback = template_report(project_name, findings, rule_suggestions(findings))
    if llm is None or not findings:
        return fallback, "template"
    try:
        text = llm.complete(REPORT_SYSTEM, f"Project: {project_name}\n{_findings_prompt(findings)}", json_mode=False)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError):
        return fallback, "template"
    invented = numbers_in(text) - allowed_numbers(findings) - numbers_in(project_name)
    if not text.strip() or invented:
        log.info("LLM report rejected: invented numbers %s", sorted(invented)[:5])
        return fallback, "template"
    return text.strip(), "groq"
