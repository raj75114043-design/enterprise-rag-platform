"""Query understanding: follow-up resolution, site / version / date filters and comparison decomposition."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ragp.corpus.spec import SITES

SITE_NAMES = {v.lower(): v for v in SITES.values()}
FOLLOW_UP = re.compile(r"^(and|what about|how about|same for|and for|also for)\b", re.I)
COMPARE = re.compile(r"\b(compare|comparison|difference|differ|versus|vs\.?)\b", re.I)
HISTORY = re.compile(r"\b(previous|earlier|old|superseded|used to|was|were|before)\b", re.I)
CHANGES = re.compile(r"\b(change|changed|changes|revision|history|what is new|updated)\b", re.I)


@dataclass
class QueryPlan:
    original: str
    resolved: str                        # after follow-up resolution
    sites: list[str] = field(default_factory=list)
    version: str | None = None           # explicit version, e.g. "3.0"
    as_of: str | None = None             # ISO date for "as of / in 2024" questions
    wants_history: bool = False
    wants_changes: bool = False
    sub_queries: list[dict] = field(default_factory=list)   # [{query, site}]
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _sites(text: str) -> list[str]:
    return [name for key, name in SITE_NAMES.items() if re.search(rf"\b{key}\b", text, re.I)]


def _strip_sites(text: str) -> str:
    for key in SITE_NAMES:
        text = re.sub(rf"\s*\b(at|for|in)?\s*{key}\b", "", text, flags=re.I)
    return text.strip()


def plan(question: str, previous: str | None = None) -> QueryPlan:
    q = question.strip()
    notes = []
    resolved = q
    if previous and (FOLLOW_UP.match(q) or len(q.split()) <= 4):
        cue = FOLLOW_UP.sub("", q).strip(" ?")
        base = _strip_sites(previous).rstrip("?")
        resolved = f"{base} {('at ' + cue) if _sites(cue) else cue}".strip() + "?"
        notes.append(f"follow-up resolved using previous question: {resolved!r}")
    sites = _sites(resolved)
    m = re.search(r"\b(?:version|v)\s?(\d+(?:\.\d+)?)", resolved, re.I)
    version = (m.group(1) if "." in m.group(1) else m.group(1) + ".0") if m else None
    y = re.search(r"\b(?:in|during|as of|before)\s+(20\d\d)\b", resolved, re.I)
    as_of = f"{y.group(1)}-12-31" if y and "before" not in y.group(0).lower() else (f"{int(y.group(1)) - 1}-12-31" if y else None)
    p = QueryPlan(q, resolved, sites, version, as_of, wants_history=bool(version or as_of or HISTORY.search(resolved) and version),
                  wants_changes=bool(CHANGES.search(resolved)), notes=notes)
    if COMPARE.search(resolved) and len(sites) >= 2:
        topic = _strip_sites(COMPARE.sub("", resolved)).replace(" between ", " ").replace(" and ", " ").strip(" ?.")
        p.sub_queries = [{"query": f"{topic} at {s}", "site": s} for s in sites]
        notes.append(f"comparison decomposed into {len(sites)} site-specific sub-queries")
    else:
        p.sub_queries = [{"query": resolved, "site": sites[0] if len(sites) == 1 else None}]
    if version:
        notes.append(f"version filter: {version}")
    if as_of:
        notes.append(f"as-of date filter: {as_of}")
    if sites:
        notes.append(f"site filter: {', '.join(sites)}")
    return p
