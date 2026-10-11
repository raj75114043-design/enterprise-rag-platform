"""Document, chunk and query-log store (PostgreSQL in production, SQLite in lite mode)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Column, Float, Integer, MetaData, String, Table, Text, create_engine, delete, insert, select, update
from sqlalchemy.engine import Engine

metadata = MetaData()

documents = Table(
    "documents", metadata,
    Column("doc_key", String, primary_key=True),          # DOC-ID@version
    Column("doc_id", String, index=True), Column("version", String), Column("title", String),
    Column("doc_type", String), Column("department", String), Column("status", String, index=True),
    Column("effective_date", String), Column("superseded_on", String), Column("access", String, index=True),
    Column("site", String), Column("parent", String), Column("source", String), Column("content_hash", String),
    Column("ingested_at", String))
chunks = Table(
    "chunks", metadata,
    Column("chunk_id", String, primary_key=True),          # DOC-ID@version#section
    Column("doc_key", String, index=True), Column("section", String), Column("heading", String),
    Column("text", Text), Column("ordinal", Integer), Column("n_tokens", Integer))
ingestion_runs = Table(
    "ingestion_runs", metadata,
    Column("run_id", Integer, primary_key=True, autoincrement=True), Column("started_at", String),
    Column("added", Integer), Column("updated", Integer), Column("unchanged", Integer), Column("removed", Integer),
    Column("chunks", Integer), Column("errors", Text))
query_log = Table(
    "query_log", metadata,
    Column("run_id", String, primary_key=True), Column("created_at", String), Column("role", String),
    Column("question", Text), Column("rewritten", Text), Column("answer", Text), Column("mode", String),
    Column("confidence", String), Column("abstained", Integer), Column("latency_ms", Float),
    Column("citations", Text), Column("trace", Text), Column("feedback", Integer), Column("feedback_comment", Text))


def now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def make_engine(url: str) -> Engine:
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    engine = create_engine(url, future=True, **kwargs)
    metadata.create_all(engine)
    return engine


class Store:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _q(self, stmt) -> list[dict]:
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(stmt)]

    # ------------------------------------------------------------------ documents and chunks
    def document_hashes(self) -> dict[str, str]:
        return {r["doc_key"]: r["content_hash"] for r in self._q(select(documents.c.doc_key, documents.c.content_hash))}

    def upsert_document(self, doc: dict, doc_chunks: list[dict]) -> None:
        with self.engine.begin() as c:
            c.execute(delete(chunks).where(chunks.c.doc_key == doc["doc_key"]))
            c.execute(delete(documents).where(documents.c.doc_key == doc["doc_key"]))
            c.execute(insert(documents), [{**doc, "ingested_at": now()}])
            if doc_chunks:
                c.execute(insert(chunks), doc_chunks)

    def remove_document(self, doc_key: str) -> None:
        with self.engine.begin() as c:
            c.execute(delete(chunks).where(chunks.c.doc_key == doc_key))
            c.execute(delete(documents).where(documents.c.doc_key == doc_key))

    def documents(self, access: list[str] | None = None) -> list[dict]:
        stmt = select(documents).order_by(documents.c.doc_id, documents.c.version)
        if access is not None:
            stmt = stmt.where(documents.c.access.in_(access))
        return self._q(stmt)

    def all_chunks(self) -> list[dict]:
        stmt = select(chunks, documents).join(documents, documents.c.doc_key == chunks.c.doc_key).order_by(chunks.c.chunk_id)
        return self._q(stmt)

    def record_ingestion(self, row: dict) -> None:
        with self.engine.begin() as c:
            c.execute(insert(ingestion_runs), [{**row, "started_at": now()}])

    def ingestion_history(self, limit: int = 10) -> list[dict]:
        return self._q(select(ingestion_runs).order_by(ingestion_runs.c.run_id.desc()).limit(limit))

    # ------------------------------------------------------------------ query log and feedback
    def log_query(self, row: dict) -> None:
        with self.engine.begin() as c:
            c.execute(insert(query_log), [{**row, "created_at": now(), "citations": json.dumps(row["citations"]),
                                           "trace": json.dumps(row["trace"], default=str)}])

    def get_run(self, run_id: str) -> dict | None:
        r = self._q(select(query_log).where(query_log.c.run_id == run_id))
        if not r:
            return None
        r[0]["citations"], r[0]["trace"] = json.loads(r[0]["citations"]), json.loads(r[0]["trace"])
        return r[0]

    def recent_runs(self, limit: int = 20) -> list[dict]:
        return self._q(select(query_log.c.run_id, query_log.c.created_at, query_log.c.role, query_log.c.question, query_log.c.mode,
                              query_log.c.confidence, query_log.c.abstained, query_log.c.latency_ms, query_log.c.feedback)
                       .order_by(query_log.c.created_at.desc()).limit(limit))

    def add_feedback(self, run_id: str, rating: int, comment: str | None) -> bool:
        with self.engine.begin() as c:
            res = c.execute(update(query_log).where(query_log.c.run_id == run_id).values(feedback=rating, feedback_comment=comment))
        return res.rowcount == 1
