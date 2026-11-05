"""Classical NLP over ticket text: quality score and similar-ticket search.

Everything here is measurable and explainable; nothing calls an LLM.
"""

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services.reference_class import ticket_text

DUPLICATE_THRESHOLD = 0.72

VAGUE_WORDS = {
    "stuff",
    "things",
    "thing",
    "misc",
    "miscellaneous",
    "various",
    "etc",
    "something",
    "some",
    "asap",
    "tbd",
    "todo",
    "issue",
    "issues",
    "problem",
    "problems",
    "changes",
    "tweaks",
    "cleanup",
    "improvements",
}
VAGUE_PHRASES = ("look into", "not great", "see slack", "please check", "doesn't work", "not working")
STRUCTURE = re.compile(
    r"acceptance criteria|steps to reproduce|expected( result| behaviou?r)?:|actual( result)?:|"
    r"definition of done|- \[ \]|\bgiven\b.+\bwhen\b.+\bthen\b|^\s*1[.)]\s",
    re.IGNORECASE | re.MULTILINE,
)
WORD = re.compile(r"[a-z0-9']+")


def quality(title: str, description: str, owner: str = "", due=None) -> tuple[int, list[str]]:
    """0–100 score for how ready a ticket is to work on, with the reasons points were lost."""
    title, description = (title or "").strip(), (description or "").strip()
    words = WORD.findall(title.lower())
    score, reasons = 100, []
    if len(words) < 4:
        score -= 20
        reasons.append(
            f"Title is short ({len(words)} word{'s' if len(words) != 1 else ''}); say what is wrong and where"
        )
    vague = sorted({w for w in words if w in VAGUE_WORDS})
    vague += [p for p in VAGUE_PHRASES if p in f"{title} {description}".lower()]
    if vague:
        score -= 15
        reasons.append("Vague wording: " + ", ".join(f"“{v}”" for v in vague[:3]))
    if not description:
        score -= 25
        reasons.append("No description")
    elif len(description) < 80:
        score -= 15
        reasons.append("Description is very short")
    if not STRUCTURE.search(description):
        score -= 15
        reasons.append("No acceptance criteria or reproduction steps")
    if not (owner or "").strip():
        score -= 10
        reasons.append("No owner")
    if due is None or (not isinstance(due, str) and pd.isna(due)) or due == "":
        score -= 10
        reasons.append("No due date")
    return max(score, 0), reasons


def quality_column(tickets: pd.DataFrame) -> pd.Series:
    return pd.Series(
        [quality(r.title, r.description, r.owner, r.due)[0] for r in tickets.itertuples()],
        index=tickets.index,
        dtype=float,
    )


@dataclass
class TextIndex:
    """TF-IDF over every ticket in a project, for duplicate search."""

    vectorizer: TfidfVectorizer
    matrix: object
    tickets: pd.DataFrame

    @classmethod
    def build(cls, tickets: pd.DataFrame) -> "TextIndex | None":
        text = ticket_text(tickets["title"], tickets["description"])
        if tickets.empty or not text.str.strip().any():
            return None
        vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        try:
            matrix = vec.fit_transform(text)
        except ValueError:
            return None
        return cls(vec, matrix, tickets.reset_index(drop=True))

    def similar_to(
        self, title: str, description: str, threshold: float = DUPLICATE_THRESHOLD, exclude_id: str | None = None
    ) -> list[dict]:
        q = self.vectorizer.transform([ticket_text(title, description)])
        sims = (self.matrix @ q.T).toarray().ravel()
        hits = np.flatnonzero(sims >= threshold)
        rows = [
            {
                "id": self.tickets.at[i, "id"],
                "title": self.tickets.at[i, "title"],
                "status": self.tickets.at[i, "status"],
                "similarity": round(float(sims[i]), 2),
            }
            for i in hits
            if self.tickets.at[i, "id"] != exclude_id
        ]
        return sorted(rows, key=lambda r: (r["status"] == "done", -r["similarity"]))[:5]
