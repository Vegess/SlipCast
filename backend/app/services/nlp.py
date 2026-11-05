"""Classical NLP over ticket text: quality score and similar-ticket search.

Everything here is measurable and explainable; nothing calls an LLM.
"""

import re
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services.reference_class import ticket_text

DUPLICATE_THRESHOLD = 0.72

# scikit-learn 1.5 passes an option newer SciPy no longer knows; the fit is unaffected.
warnings.filterwarnings("ignore", message="Unknown solver options")

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


# ---------- ticket type classifier ----------
MIN_LABELLED = 40
KINDS = ("bug", "feature", "tech_debt", "support")


def time_split(df: pd.DataFrame, test_share: float = 0.25) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Train on the oldest tickets, test on the newest, the way the model is used."""
    df = df.sort_values("created_at", kind="stable")
    cut = int(round(len(df) * (1 - test_share)))
    train, test = df.iloc[:cut], df.iloc[cut:]
    when = test["created_at"].min()
    return train, test, f"train on tickets created before {when.date().isoformat()}, test on the rest"


def _type_pipeline():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    return make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", min_df=1),
        LogisticRegression(class_weight="balanced", max_iter=2000, C=4.0),
    )


def train_classifier(tickets: pd.DataFrame) -> dict:
    """Evaluate on a time-based split, then refit on every label to type unlabelled tickets."""
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

    labelled = tickets[(tickets["kind_source"] == "label") & tickets["kind"].notna()]
    unlabelled = tickets[~tickets.index.isin(labelled.index)]
    base = {"available": False, "predicted_unlabeled": 0, "predictions": pd.Series(dtype=object)}
    if len(labelled) < MIN_LABELLED or labelled["kind"].nunique() < 2:
        return {
            **base,
            "reason": f"The type classifier needs at least {MIN_LABELLED} tickets with a type label and two "
            f"different types; this project has {len(labelled)} labelled.",
        }
    text = ticket_text(labelled["title"], labelled["description"])
    train, test, split = time_split(labelled.assign(text=text))
    labels = sorted(labelled["kind"].unique())
    if train["kind"].nunique() < 2 or test.empty:
        return {**base, "reason": "The oldest labelled tickets all share one type, so there is nothing to learn yet."}
    model = _type_pipeline().fit(train["text"], train["kind"])
    pred = model.predict(test["text"])
    majority = train["kind"].mode().iloc[0]
    base_pred = np.full(len(test), majority)
    prec, rec, f1, sup = precision_recall_fscore_support(test["kind"], pred, labels=labels, zero_division=0)

    vec, lr = model.steps[0][1], model.steps[1][1]
    terms = np.array(vec.get_feature_names_out())
    top_terms = {str(c): terms[np.argsort(-lr.coef_[i])[:6]].tolist() for i, c in enumerate(lr.classes_)}
    if len(lr.classes_) == 2:  # binary models expose one coefficient row
        top_terms = {
            str(lr.classes_[1]): terms[np.argsort(-lr.coef_[0])[:6]].tolist(),
            str(lr.classes_[0]): terms[np.argsort(lr.coef_[0])[:6]].tolist(),
        }

    final = _type_pipeline().fit(text, labelled["kind"])
    predictions = pd.Series(dtype=object)
    if len(unlabelled):
        predictions = pd.Series(
            final.predict(ticket_text(unlabelled["title"], unlabelled["description"])), index=unlabelled.index
        )
    return {
        "available": True,
        "reason": "",
        "labels": labels,
        "accuracy": round(float(accuracy_score(test["kind"], pred)), 3),
        "macro_f1": round(float(f1_score(test["kind"], pred, average="macro", labels=labels, zero_division=0)), 3),
        "train_size": int(len(train)),
        "test_size": int(len(test)),
        "split": split,
        "baseline": {
            "name": f"always predict the most common type ({majority})",
            "accuracy": round(float(accuracy_score(test["kind"], base_pred)), 3),
            "macro_f1": round(
                float(f1_score(test["kind"], base_pred, average="macro", labels=labels, zero_division=0)), 3
            ),
        },
        "per_class": [
            {
                "label": lab,
                "precision": round(float(prec[i]), 3),
                "recall": round(float(rec[i]), 3),
                "f1": round(float(f1[i]), 3),
                "support": int(sup[i]),
            }
            for i, lab in enumerate(labels)
        ],
        "confusion_matrix": confusion_matrix(test["kind"], pred, labels=labels).tolist(),
        "top_terms": top_terms,
        "predicted_unlabeled": int(len(predictions)),
        "predictions": predictions,
        "model": final,
    }


# ---------- themes ----------
DOMAIN_STOP_WORDS = {
    "fix", "fixes", "add", "adds", "allow", "support", "bug", "issue", "issues", "error", "errors", "update", "please",
    "customer", "customers", "ticket", "tickets", "user", "users", "admin", "admins", "account", "accounts", "plan",
    "seen", "affects", "touches", "page", "need", "needs", "want", "wants", "make", "new", "use", "using", "work",
    "works", "working", "change", "changes", "check", "help", "request", "requests", "question", "problem", "team",
    "reply", "day", "confirm", "settings", "stuff", "misc", "look", "flaky", "intermittent", "investigate",
    "expected", "actual", "result", "steps", "reproduce", "click", "open", "save", "saved", "saving", "criteria",
    "acceptance", "definition", "done", "tests", "test", "pass", "note", "happens", "root", "cause", "unknown",
    "corp", "starter", "pro", "business", "enterprise", "inc", "ltd", "slack", "thread", "complained", "great",
}  # fmt: skip
MIN_THEME_TICKETS = 30


def find_themes(tickets: pd.DataFrame, k_range=range(3, 9), seed: int = 0) -> dict:
    """K-means over TF-IDF; k chosen by cosine silhouette; each theme named by its top 3 terms."""
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    from sklearn.metrics import silhouette_score

    base = {"available": False, "silhouette": None, "items": [], "labels": None, "count": 0}
    text = ticket_text(tickets["title"], tickets["description"])
    if len(tickets) < MIN_THEME_TICKETS:
        return {
            **base,
            "reason": f"Themes need at least {MIN_THEME_TICKETS} tickets with text; this project has {len(tickets)}.",
        }
    vec = TfidfVectorizer(
        stop_words=list(ENGLISH_STOP_WORDS | DOMAIN_STOP_WORDS),
        max_df=0.2,
        min_df=2,
        sublinear_tf=True,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+(?:-[a-zA-Z]+)*\b",
    )
    try:
        x = vec.fit_transform(text)
    except ValueError:
        return {**base, "reason": "Ticket text is too short or repetitive to find themes."}
    keep = np.asarray(x.sum(axis=1)).ravel() > 0
    if keep.sum() < MIN_THEME_TICKETS:
        return {**base, "reason": "Too few tickets have distinctive words to find themes."}
    xk = x[keep]
    best = None
    sample = min(xk.shape[0], 1000)
    for k in k_range:
        if k >= xk.shape[0]:
            break
        km = KMeans(n_clusters=k, n_init=4, random_state=seed).fit(xk)
        score = float(silhouette_score(xk, km.labels_, metric="cosine", sample_size=sample, random_state=seed))
        if best is None or score > best[0]:
            best = (score, k, km)
    if best is None:
        return {**base, "reason": "Not enough distinct tickets to cluster."}
    score, k, km = best
    terms = np.array(vec.get_feature_names_out())
    names = {}
    keywords = {}
    for c in range(k):
        top = terms[np.argsort(-km.cluster_centers_[c])[:8]].tolist()
        keywords[c] = top
        names[c] = ", ".join(top[:3])
    labels = pd.Series("Other", index=tickets.index, dtype=object)
    labels[tickets.index[keep]] = [names[c] for c in km.labels_]
    return {
        "available": True,
        "reason": "",
        "silhouette": round(score, 3),
        "count": int(k),
        "labels": labels,
        "keywords": {names[c]: keywords[c] for c in range(k)},
    }


# ---------- duplicates ----------
def duplicate_pairs(index: "TextIndex | None", threshold: float = DUPLICATE_THRESHOLD, limit: int = 50) -> list[dict]:
    """All pairs at least `threshold` similar; pairs involving open tickets first."""
    if index is None:
        return []
    from scipy import sparse

    sims = sparse.triu(index.matrix @ index.matrix.T, k=1).tocoo()
    hits = sims.data >= threshold
    t = index.tickets
    pairs = []
    for i, j, s in zip(sims.row[hits], sims.col[hits], sims.data[hits], strict=False):
        a, b = t.iloc[i], t.iloc[j]
        if a["status"] == "done" and b["status"] != "done":
            a, b = b, a
        pairs.append(
            {
                "similarity": round(float(s), 3),
                "a": {"id": a["id"], "title": a["title"], "status": a["status"]},
                "b": {"id": b["id"], "title": b["title"], "status": b["status"]},
            }
        )
    pairs.sort(key=lambda p: (p["a"]["status"] == "done" and p["b"]["status"] == "done", -p["similarity"]))
    return pairs[:limit]
