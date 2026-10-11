"""Incremental ingestion of controlled Markdown documents.

* Front matter supplies governance metadata (version, status, effective date, access level, site).
* Documents are chunked along their heading structure; each chunk keeps a breadcrumb header
  ("SOP-QA-001 v4.0 › 5.1 Phase I – Laboratory investigation") so it is self-describing at retrieval time.
* A SHA-256 content hash makes re-ingestion incremental: unchanged documents are skipped, changed ones
  are re-chunked and documents that disappeared from the source are removed.
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from ragp.store import Store

log = logging.getLogger("ragp.ingest")
REQUIRED = ("doc_id", "version", "title", "status", "effective_date", "access")
ACCESS_LEVELS = {"public", "internal", "confidential"}
MAX_WORDS = 160


class IngestError(ValueError):
    pass


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise IngestError("missing front matter")
    _, fm, body = text.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"') or None
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        raise IngestError(f"missing front matter fields: {missing}")
    if meta["access"] not in ACCESS_LEVELS:
        raise IngestError(f"unknown access level {meta['access']!r}")
    return meta, body


def _split_long(text: str, max_words: int = MAX_WORDS) -> list[str]:
    """Split on sentence boundaries with one sentence of overlap when a section is too long."""
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    out, cur = [], []
    for s in sents:
        if cur and sum(len(x.split()) for x in cur) + len(s.split()) > max_words:
            out.append(" ".join(cur))
            cur = cur[-1:]
        cur.append(s)
    if cur:
        out.append(" ".join(cur))
    return out


def chunk_document(meta: dict, body: str) -> list[dict]:
    doc_key = f"{meta['doc_id']}@{meta['version']}"
    sections: list[tuple[str, str, list[str]]] = []   # (section number, heading, lines)
    major = ""
    for line in body.splitlines():
        m2 = re.match(r"^## (\d+)\.\s+(.*)", line)
        m3 = re.match(r"^### (\d+\.\d+)\s+(.*)", line)
        if m2:
            major = f"{m2.group(1)} {m2.group(2)}"
            sections.append((m2.group(1), major, []))
        elif m3:
            sections.append((m3.group(1), f"{m3.group(1)} {m3.group(2)}", []))
        elif sections and line.strip() and not line.startswith("# ") and not line.startswith("**Version"):
            sections[-1][2].append(line.strip().lstrip("- ").strip())
    out = []
    for sec, heading, lines in sections:
        if not lines or (len(" ".join(lines).split()) < 4):     # skip empty / "Not applicable." sections
            continue
        text = " ".join(lines) if not lines[0].startswith("|") else "\n".join(lines)
        for i, part in enumerate(_split_long(text) if not text.startswith("|") else [text]):
            cid = f"{doc_key}#{sec}" + (f".p{i + 1}" if i else "")
            header = f"{meta['doc_id']} v{meta['version']} — {meta['title']} › {heading}"
            out.append({"chunk_id": cid, "doc_key": doc_key, "section": sec, "heading": header, "text": part,
                        "ordinal": len(out), "n_tokens": len(part.split())})
    return out


def ingest_directory(store: Store, directory: str | Path) -> dict:
    directory = Path(directory)
    known = store.document_hashes()
    seen, stats, errors = set(), {"added": 0, "updated": 0, "unchanged": 0, "removed": 0, "chunks": 0}, []
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(raw.encode()).hexdigest()
        try:
            meta, body = parse_front_matter(raw)
        except IngestError as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        doc_key = f"{meta['doc_id']}@{meta['version']}"
        seen.add(doc_key)
        if known.get(doc_key) == digest:
            stats["unchanged"] += 1
            continue
        doc_chunks = chunk_document(meta, body)
        doc = {"doc_key": doc_key, "doc_id": meta["doc_id"], "version": meta["version"], "title": meta["title"],
               "doc_type": meta.get("doc_type"), "department": meta.get("department"), "status": meta["status"],
               "effective_date": meta["effective_date"], "superseded_on": meta.get("superseded_on"), "access": meta["access"],
               "site": meta.get("site") or "All sites", "parent": meta.get("parent"), "source": path.name, "content_hash": digest}
        store.upsert_document(doc, doc_chunks)
        stats["updated" if doc_key in known else "added"] += 1
        stats["chunks"] += len(doc_chunks)
    for doc_key in set(known) - seen:
        store.remove_document(doc_key)
        stats["removed"] += 1
    store.record_ingestion({**stats, "errors": "; ".join(errors) or None})
    log.info("ingestion_complete", extra={**stats, "errors": len(errors)})
    return {**stats, "errors": errors}
