"""Render the document families in `spec.py` into controlled Markdown documents and a golden QA set.

    python -m ragp.corpus.generator          # writes corpus/*.md and eval/golden.jsonl

Each document carries YAML front matter (id, version, status, effective date, access level, site) that the
ingestion pipeline uses for access control and version filtering.
"""
from __future__ import annotations

import json
from pathlib import Path

from ragp.corpus.spec import FAMILIES, SITES, UNANSWERABLE, Fact, Family

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "corpus"
GOLDEN_PATH = ROOT / "eval" / "golden.jsonl"
LABELS = {"minor_close": "minor deviation closure timeline", "dirty_hold": "dirty equipment hold time",
          "phase1": "Phase I investigation timeline", "qa_notify": "QA notification time",
          "critical_notify": "critical deviation escalation time", "major_close": "major deviation closure timeline",
          "password": "password change interval"}


def _status(fam: Family, version: str) -> tuple[str, str | None]:
    """Return (status, superseded_on) for a version."""
    idx = [v for v, _ in fam.versions].index(version)
    if idx == len(fam.versions) - 1:
        return "effective", None
    return "superseded", fam.versions[idx + 1][1]


def render(fam: Family, version: str, effective: str) -> str:
    status, superseded_on = _status(fam, version)
    site = SITES.get(fam.site, "All sites") if fam.site else "All sites"
    fm = ["---", f"doc_id: {fam.doc_id}", f"title: {fam.title}", f"version: \"{version}\"", f"doc_type: {fam.doc_type}",
          f"department: {fam.department}", f"status: {status}", f"effective_date: {effective}",
          f"superseded_on: {superseded_on or ''}", f"access: {fam.access}", f"site: {site}", f"parent: {fam.parent or ''}", "---", ""]
    out = fm + [f"# {fam.doc_id} — {fam.title}", "",
                f"**Version:** {version} · **Effective:** {effective} · **Status:** {status.title()} · **Site:** {site}", ""]
    if status == "superseded":
        out += [f"> This version was superseded on {superseded_on}. Refer to the current effective version.", ""]
    out += ["## 1. Purpose", fam.purpose, "", "## 2. Scope", fam.scope, "", "## 3. Responsibilities"]
    out += [f"- {r}" for r in fam.responsibilities] + [""]
    out += ["## 4. Definitions"] + ([f"- {d}" for d in fam.definitions] or ["- Not applicable."]) + [""]
    out += ["## 5. Procedure", ""]
    for i, (sub, items) in enumerate(fam.procedure, start=1):
        out += [f"### 5.{i} {sub}"]
        for it in items:
            out.append(it.template.format(v=it.value(version)) if isinstance(it, Fact) else it)
        out.append("")
    out += ["## 6. Records", fam.records, "", "## 7. Revision History", "", "| Version | Effective | Summary of changes |", "|---|---|---|"]
    for i, (v, eff) in enumerate(fam.versions):
        if v > version:
            break
        if i == 0:
            summary = "New document." if v in ("1.0",) else "Periodic revision; content aligned with current practice."
        else:
            prev = fam.versions[i - 1][0]
            changes = [f"Section 5.{n} {LABELS.get(f.key, f.key)} changed from {f.value(prev)} to {f.value(v)}"
                       for n, (_, items) in enumerate(fam.procedure, start=1) for f in items
                       if isinstance(f, Fact) and f.value(prev) != f.value(v)]
            summary = "; ".join(changes) or "Editorial changes."
        out.append(f"| {v} | {eff} | {summary} |")
    return "\n".join(out) + "\n"


def _facts(fam: Family):
    for n, (_, items) in enumerate(fam.procedure, start=1):
        for it in items:
            if isinstance(it, Fact):
                yield n, it


def golden() -> list[dict]:
    rows: list[dict] = []
    by_id = {f.doc_id: f for f in FAMILIES}

    def add(**kw):
        kw["id"] = f"Q{len(rows) + 1:03d}"
        rows.append(kw)

    for fam in FAMILIES:
        current, _ = fam.versions[-1]
        role = "qa_head" if fam.access == "confidential" else ("operator" if fam.access == "public" else "qa_analyst")
        for _, fact in _facts(fam):
            for q in fact.questions:
                add(question=q, role=role, type="site" if fam.site and fam.parent else ("confidential" if fam.access == "confidential" else "current"),
                    expected_doc=fam.doc_id, expected_version=current, expected=[fact.value(current)])
            if fam.access == "confidential":
                add(question=fact.questions[0], role="qa_analyst", type="acl_denied", expected_doc=None, expected_version=None, expected=[],
                    forbidden=[fact.value(current)])
            if fact.history_question and len(fam.versions) > 1:
                old = fam.versions[-2][0]
                add(question=fact.history_question, role=role, type="history", expected_doc=fam.doc_id, expected_version=old,
                    expected=[fact.value(old)])
        if fam.parent:  # site annex: comparison, fallback and follow-up questions
            parent = by_id[fam.parent]
            for _, fact in _facts(fam):
                pfact = next(f for _, f in _facts(parent) if f.key == fact.key)
                other = next(c for c in SITES if c != fam.site)
                site, other_site = SITES[fam.site], SITES[other]
                add(question=f"Compare the {LABELS.get(fact.key, fact.key.replace('_', ' '))} between {other_site} and {site}.", role="qa_analyst",
                    type="comparison", expected_doc=fam.doc_id, expected_version=fam.versions[-1][0],
                    expected=[pfact.value(parent.versions[-1][0]), fact.value(fam.versions[-1][0])])
                add(question=pfact.questions[0].rstrip("?") + f" at {other_site}?", role="qa_analyst", type="site_fallback",
                    expected_doc=parent.doc_id, expected_version=parent.versions[-1][0], expected=[pfact.value(parent.versions[-1][0])])
                add(question=f"And at {site}?", previous=pfact.questions[0], role="qa_analyst", type="follow_up",
                    expected_doc=fam.doc_id, expected_version=fam.versions[-1][0], expected=[fact.value(fam.versions[-1][0])])
    for q, role in UNANSWERABLE:
        add(question=q, role=role, type="unanswerable", expected_doc=None, expected_version=None, expected=[])
    return rows


def main() -> None:
    CORPUS_DIR.mkdir(exist_ok=True)
    GOLDEN_PATH.parent.mkdir(exist_ok=True)
    for old in CORPUS_DIR.glob("*.md"):
        old.unlink()
    n = 0
    for fam in FAMILIES:
        for version, effective in fam.versions:
            (CORPUS_DIR / f"{fam.doc_id}_v{version}.md").write_text(render(fam, version, effective), encoding="utf-8")
            n += 1
    rows = golden()
    GOLDEN_PATH.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    print(f"wrote {n} documents to {CORPUS_DIR} and {len(rows)} golden questions to {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
