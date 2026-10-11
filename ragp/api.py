"""FastAPI service.

Authentication: `X-API-Key` maps to a role (operator, qa_analyst, qa_head) via API_KEYS, standing in for SSO groups.

  POST /v1/ask                  ask a question (optionally with the previous question for follow-ups)
  POST /v1/feedback             thumbs up/down on an answer
  GET  /v1/documents            document library visible to the caller's role
  GET  /v1/runs/{run_id}        full trace of an answer (audit)
  POST /v1/ingest               incremental re-ingestion (qa_head only)
  GET  /health, /ready, /metrics
"""
from __future__ import annotations

import time
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from ragp import logging_setup
from ragp.corpus.spec import ROLES
from ragp.pipeline import ask, get_container, reindex

logging_setup.configure()
app = FastAPI(title="Enterprise RAG Platform", version="1.0.0", description="Governed retrieval-augmented QA over GxP controlled documents")

REQUESTS = Counter("rag_http_requests_total", "HTTP requests", ["path", "status"])
ANSWERS = Counter("rag_answers_total", "Answers", ["mode", "abstained", "role"])
LATENCY = Histogram("rag_answer_seconds", "Answer latency", buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10))
FEEDBACK = Counter("rag_feedback_total", "User feedback", ["rating"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    token = logging_setup.request_id.set(rid)
    try:
        response = await call_next(request)
    finally:
        logging_setup.request_id.reset(token)
    response.headers["X-Request-ID"] = rid
    path = "/v1/runs/{id}" if request.url.path.startswith("/v1/runs/") else request.url.path
    REQUESTS.labels(path, response.status_code).inc()
    return response


def role_of(x_api_key: str | None = Header(default=None)) -> str:
    role = get_container().settings.api_keys.get(x_api_key or "")
    if not role:
        raise HTTPException(401, "Invalid or missing API key")
    return role


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500, examples=["How long do we have to complete a Phase I OOS investigation?"])
    previous: str | None = Field(default=None, max_length=500, description="Previous question, for follow-ups such as 'And at Baddi?'")


class Feedback(BaseModel):
    run_id: str
    rating: int = Field(ge=-1, le=1)
    comment: str | None = Field(default=None, max_length=1000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    c = get_container()
    return {"status": "ready", "documents": len(c.store.documents()), "chunks": len(c.index.ids),
            "embeddings": c.index.embedder.name, "llm": {"provider": c.llm.provider, "model": c.llm.model}}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/ask")
def ask_endpoint(req: AskRequest, role: str = Depends(role_of)):
    t0 = time.perf_counter()
    r = ask(get_container(), req.question, role, req.previous)
    LATENCY.observe(time.perf_counter() - t0)
    ANSWERS.labels(r["mode"], str(r["abstained"]).lower(), role).inc()
    return r


@app.post("/v1/feedback")
def feedback(f: Feedback, role: str = Depends(role_of)):
    if not get_container().store.add_feedback(f.run_id, f.rating, f.comment):
        raise HTTPException(404, "Run not found")
    FEEDBACK.labels(str(f.rating)).inc()
    return {"status": "recorded"}


@app.get("/v1/documents")
def documents(role: str = Depends(role_of)):
    return [{k: d[k] for k in ("doc_id", "version", "title", "doc_type", "status", "effective_date", "access", "site")}
            for d in get_container().store.documents(ROLES[role])]


@app.get("/v1/runs/{run_id}")
def run(run_id: str, role: str = Depends(role_of)):
    r = get_container().store.get_run(run_id)
    if not r or (role != "qa_head" and r["role"] != role):
        raise HTTPException(404, "Run not found")
    return r


@app.post("/v1/ingest")
def ingest(role: str = Depends(role_of)):
    if role != "qa_head":
        raise HTTPException(403, "Only qa_head may trigger ingestion")
    return reindex(get_container())
