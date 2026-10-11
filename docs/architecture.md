# Architecture

## Request flow
1. **Query understanding** (`query.py`) — resolves follow-ups against the previous question, detects sites, explicit
   versions (`version 3.0`, `v1`) and years (`in 2024` → as-of 2024-12-31), and decomposes comparisons into one
   sub-query per site.
2. **Governance filters** (`retriever.py`) — eligibility mask from role → access levels, version/as-of rule and site rule.
3. **Hybrid search** (`index.py`) — BM25 over stemmed tokens with domain expansion, dense search (LSA or bge-small),
   fused with Reciprocal Rank Fusion (k = 60).
4. **Rerank** — fused score, query-concept coverage, heading overlap, site-annex boost, penalties for revision-history
   tables (unless the question asks about changes) and boilerplate sections; at most 3 chunks per document version.
5. **Extractive answer** (`answer.py`) — sentence scoring by IDF-weighted concept support, answer-type preference
   (quantities for "how long / how often" questions), identifier anchoring (batch numbers must appear), optional second
   sentence when it covers a concept the first one missed. Abstain below `MIN_SUPPORT`.
6. **LLM writer** (optional) — citation and number verification, one corrective retry, extractive fallback.
7. **Audit** — the run (question, resolved question, role, answer, citations, step trace) is stored in `query_log`.

## Data model
`documents` (one row per document version) · `chunks` · `ingestion_runs` · `query_log` (with feedback).

## Scaling notes
| Concern | Current | At scale |
|---|---|---|
| Vector search | in-memory NumPy | pgvector / Qdrant with metadata payload filters |
| Embeddings | LSA (offline) | bge-small / e5 via fastembed or a hosted embedding service |
| Reranking | feature-based | cross-encoder (bge-reranker) on top 20 |
| Ingestion | directory scan | DMS webhooks on document approval / supersession |
