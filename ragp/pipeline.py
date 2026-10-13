"""End-to-end question answering with a step-by-step trace."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ragp.answer import Answerer, idf_table
from ragp.config import Settings, get_settings
from ragp.corpus.spec import ROLES
from ragp.index import HybridIndex
from ragp.ingest import ingest_directory
from ragp.llm import LLMClient, LLMUsage, build_llm
from ragp.query import plan as make_plan
from ragp.retriever import Retriever
from ragp.store import Store, make_engine

log = logging.getLogger("ragp.pipeline")


@dataclass
class Container:
    settings: Settings
    store: Store
    index: HybridIndex
    retriever: Retriever
    answerer: Answerer
    llm: LLMClient


def build(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    store = Store(make_engine(settings.database_url))
    ingest_directory(store, settings.corpus_dir)
    return _assemble(settings, store)


def _assemble(settings: Settings, store: Store) -> Container:
    rows = store.all_chunks()
    index = HybridIndex(rows, settings.embeddings)
    llm = build_llm(settings)
    return Container(settings, store, index, Retriever(index), Answerer(idf_table(rows), settings.min_support, llm), llm)


def reindex(c: Container) -> dict:
    """Incremental ingestion followed by an index rebuild (used by the API and console)."""
    stats = ingest_directory(c.store, c.settings.corpus_dir)
    fresh = _assemble(c.settings, c.store)
    c.index, c.retriever, c.answerer = fresh.index, fresh.retriever, fresh.answerer
    return stats


@lru_cache(maxsize=4)
def _cached(sig: tuple) -> Container:
    return build()


def get_container() -> Container:
    import os
    return _cached(tuple(os.getenv(k, "") for k in ("LLM_PROVIDER", "LLM_MODEL", "GROQ_API_KEY", "LLM_API_KEY", "EMBEDDINGS", "CORPUS_DIR")))


def ask(c: Container, question: str, role: str = "qa_analyst", previous: str | None = None, persist: bool = True) -> dict:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    t0 = time.perf_counter()
    trace, usage = [], LLMUsage()

    def step(name, started, **info):
        trace.append({"step": name, "ms": round((time.perf_counter() - started) * 1000, 1), **info})

    s = time.perf_counter()
    p = make_plan(question, previous)
    step("query_understanding", s, resolved=p.resolved, notes=p.notes, sub_queries=[q["query"] for q in p.sub_queries])

    hits_by_sub, all_hits, retrieval_info = [], {}, []
    for sub in p.sub_queries:
        s = time.perf_counter()
        hits, info = c.retriever.retrieve(sub["query"], role, p, sub["site"], k=c.settings.top_k)
        hits_by_sub.append(hits)
        for h in hits:
            all_hits.setdefault(h.id, h)
        retrieval_info.append(info)
        step("retrieve", s, query=sub["query"], **info, top=[h.id for h in hits])

    s = time.perf_counter()
    ext = c.answerer.extractive(p.sub_queries, hits_by_sub)
    step("extractive_answer", s, support=ext["support"], abstained=ext["abstained"])

    s = time.perf_counter()
    gen_hits = [h for hits in hits_by_sub for h in hits[:3]]
    result, mode = c.answerer.generate(p.resolved, gen_hits, ext, usage)
    step("generate", s, mode=mode, llm_calls=usage.calls, llm_failures=usage.failures)

    latency = round((time.perf_counter() - t0) * 1000, 1)
    run_id = "RUN-" + uuid.uuid4().hex[:10].upper()
    out = {"run_id": run_id, "question": question, "resolved_question": p.resolved, "role": role, "answer": result["answer"],
           "mode": mode, "abstained": result["abstained"], "confidence": result["confidence"], "support": result["support"],
           "citations": result["citations"], "plan": p.as_dict(), "retrieval": retrieval_info,
           "sources": [h.as_dict() for h in all_hits.values()], "trace": trace, "latency_ms": latency,
           "llm": {"provider": c.llm.provider, "model": c.llm.model, "calls": usage.calls, "failures": usage.failures,
                   "prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens,
                   "errors": [e for e in usage.events if not e.get("ok")]}}
    if persist:
        c.store.log_query({"run_id": run_id, "role": role, "question": question, "rewritten": p.resolved, "answer": out["answer"],
                           "mode": mode, "confidence": out["confidence"], "abstained": int(out["abstained"]), "latency_ms": latency,
                           "citations": out["citations"], "trace": trace})
    log.info("ask", extra={"run_id": run_id, "role": role, "mode": mode, "abstained": out["abstained"], "latency_ms": latency})
    return out
