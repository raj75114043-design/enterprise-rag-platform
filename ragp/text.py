"""Tokenisation, light stemming and pharma-domain query expansion shared by indexing and answering."""
from __future__ import annotations

import re
from functools import lru_cache

import snowballstemmer

STOP = set("""a an the is are was were be been being to of in on for and or with by from at as it this that these those its
our we us you your do does did how what when where which who whom why can could should shall would will may might must
there their they them than then into about after before during per any all each every if not no so such also have has had
i me my please tell need needed long much many often soon quickly fast under over up down out
happen happens happened someone anyone thing things get got done allowed overall exactly typically generally actually""".split())

# Domain abbreviations and synonyms (query side); keys and values are matched after lower-casing.
EXPANSIONS = {
    "oos": "out of specification", "oot": "out of trend", "capa": "corrective preventive action",
    "apqr": "annual product quality review", "pqr": "product quality review", "csv": "computerised system validation",
    "di": "data integrity", "hplc": "chromatography", "cds": "chromatography data system", "lims": "laboratory information",
    "qms": "quality management system", "ccb": "change control board", "pai": "pre approval inspection",
    "ra": "regulatory affairs", "sop": "procedure", "qa": "quality assurance", "qc": "quality control",
    "login": "login credentials", "ids": "credentials", "password": "passwords", "temperature": "temperature excursion",
    "complaint": "complaints", "lab": "laboratory", "deadline": "completed within", "timeline": "within",
    "kept": "retained", "keep": "retained", "retain": "retained", "contamination": "contamination root cause",
    "computerized": "computerised", "validation": "validated",
    "closure": "closed", "close": "closed", "record": "logged", "recorded": "logged", "limit": "within",
    "required": "requires", "approving": "approval", "default": "target", "due": "target completion",
    "extended": "extension", "extend": "extension", "notified": "notify", "escalated": "escalation",
    "frequency": "every", "time": "within", "detected": "detection", "deleted": "deletions", "instrument": "instruments", "tolerance": "out-of-tolerance",
}

_STEMMER = snowballstemmer.stemmer("english")
_ROMAN = [(re.compile(r"\bphase\s+ii\b", re.I), "phasetwo"), (re.compile(r"\bphase\s+i\b", re.I), "phaseone")]


def stem(tok: str) -> str:
    return tok if any(ch.isdigit() for ch in tok) else _STEMMER.stemWord(tok)


def words(text: str) -> list[str]:
    for rx, rep in _ROMAN:
        text = rx.sub(rep, text)
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())


def tokens(text: str) -> list[str]:
    """Index-side tokens: stemmed content words."""
    return list(_tokens(text))


@lru_cache(maxsize=50_000)
def _tokens(text: str) -> tuple[str, ...]:
    return tuple(stem(w) for w in words(text) if w not in STOP)


def identifiers(text: str) -> set[str]:
    """Specific identifiers in a question (batch numbers, document IDs) that an answer must actually contain."""
    ids = {m.lower() for m in re.findall(r"\b[A-Z]{1,5}-?\d{2,}\b", text)}
    return {re.sub(r"[^a-z0-9]", "", i) for i in ids}


def query_groups(text: str) -> list[set[str]]:
    """One group per query concept: the stemmed word plus its domain expansions (any member satisfies the concept)."""
    groups, seen = [], set()
    for w in words(text):
        if w in STOP:
            continue
        g = {stem(w)} | {stem(x) for x in words(EXPANSIONS.get(w, "")) if x not in STOP}
        key = stem(w)
        if key not in seen:
            seen.add(key)
            groups.append(g)
    return groups


def query_tokens(text: str) -> list[str]:
    """Flat list of query tokens including expansions (used for lexical search)."""
    out, seen = [], set()
    for g in query_groups(text):
        for t in sorted(g):
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text) if s.strip()]
