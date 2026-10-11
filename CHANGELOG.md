# Changelog

## 1.0.0 — 2026-10-11
- Controlled-document ingestion with front-matter validation, heading chunking and incremental re-indexing
- Hybrid BM25 + dense retrieval with RRF, reranking and per-document diversity
- Query understanding: follow-ups, site and version filters, comparison decomposition, pharma acronyms
- Role-based access, version and site filtering before retrieval
- Extractive answers with abstention; optional LLM writer with citation and number guards
- FastAPI service, Streamlit console, PostgreSQL support, Docker, CI quality gate on a generated golden set
