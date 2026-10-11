# ADR-0001: Enforce access, version and site rules before retrieval

**Status:** Accepted · 2026-10-11

## Context
Controlled documents carry governance metadata: access level, lifecycle status (effective / superseded) and site
applicability. A common RAG pattern retrieves top-k chunks and filters afterwards. That leaks information (a
restricted chunk can still shape scores, snippets or "no access" messages) and can return fewer than k usable chunks.

## Decision
The retriever builds an eligibility mask from the caller's role, the requested version or as-of date, and the site
mentioned in the question, and both BM25 and dense search operate only on eligible chunks. Site annexes are only
eligible for questions about their site. Restricted documents are also hidden from the document library.

## Consequences
+ Restricted content can never reach the answer writer; access-denied questions are indistinguishable from unanswerable ones.
+ Superseded versions are excluded unless the user explicitly asks for history.
− The index is shared and filtered per request; at very large scale the mask should become a native vector-store filter (pgvector / Qdrant payload filters).
