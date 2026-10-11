"""Governed retrieval: access control and version/site filtering *before* search, hybrid search, then reranking.

Filtering before search (not after) guarantees that restricted or superseded content can never reach the
answer generator, and that a user cannot infer a restricted document exists from its score or snippet.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ragp.corpus.spec import ROLES
from ragp.index import HybridIndex
from ragp.query import QueryPlan
from ragp.text import query_tokens, tokens


@dataclass
class Hit:
    chunk: dict
    score: float
    features: dict

    @property
    def id(self) -> str:
        return self.chunk["chunk_id"]

    def as_dict(self) -> dict:
        c = self.chunk
        return {"chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "version": c["version"], "status": c["status"],
                "site": c["site"], "access": c["access"], "heading": c["heading"], "text": c["text"],
                "score": round(self.score, 4), **{k: round(v, 4) if isinstance(v, float) else v for k, v in self.features.items()}}


class Retriever:
    def __init__(self, index: HybridIndex):
        self.index = index
        self.meta = index.chunks
        self.versions: dict[str, list[tuple[str, str]]] = {}
        for c in self.meta:
            self.versions.setdefault(c["doc_id"], [])
            if (c["version"], c["effective_date"]) not in self.versions[c["doc_id"]]:
                self.versions[c["doc_id"]].append((c["version"], c["effective_date"]))

    # ------------------------------------------------------------------ filters
    def allowed_mask(self, role: str, plan: QueryPlan, site: str | None) -> tuple[np.ndarray, list[str]]:
        access = set(ROLES.get(role, []))
        applied = [f"access ∈ {sorted(access)}"]
        mask = np.zeros(len(self.meta), dtype=bool)
        for i, c in enumerate(self.meta):
            if c["access"] not in access:
                continue
            if not self._version_ok(c, plan):
                continue
            is_annex = bool(c.get("parent"))
            if is_annex and (site is None or c["site"] != site):
                continue           # site annexes only apply to questions about their site
            if not is_annex and c["site"] not in ("All sites", None) and site and c["site"] != site:
                continue
            mask[i] = True
        applied.append("version: " + (f"v{plan.version}" if plan.version else f"effective on {plan.as_of}" if plan.as_of else "current effective only"))
        if site:
            applied.append(f"site: {site} (+ global documents)")
        return mask, applied

    def _version_ok(self, c: dict, plan: QueryPlan) -> bool:
        if plan.version:
            has = any(v == plan.version for v, _ in self.versions[c["doc_id"]])
            return c["version"] == plan.version if has else c["status"] == "effective"
        if plan.as_of:
            valid = [v for v, eff in self.versions[c["doc_id"]] if eff <= plan.as_of]
            if not valid:
                return False
            return c["version"] == max(valid, key=lambda v: float(v))
        return c["status"] == "effective"

    # ------------------------------------------------------------------ search + rerank
    def retrieve(self, query: str, role: str, plan: QueryPlan, site: str | None, k: int = 5) -> tuple[list[Hit], dict]:
        mask, applied = self.allowed_mask(role, plan, site)
        res = self.index.search(query, mask, k=30)
        qt = set(query_tokens(query))
        hits = []
        max_rrf = max(res["rrf"].values(), default=1.0)
        for i, rrf in res["rrf"].items():
            c = self.meta[i]
            body = set(tokens(c["text"]))
            head = set(tokens(c["heading"]))
            coverage = len(qt & (body | head)) / max(len(qt), 1)
            heading_overlap = len(qt & head) / max(len(qt), 1)
            score = 0.45 * (rrf / max_rrf) + 0.4 * coverage + 0.15 * heading_overlap
            section = c["section"].split(".")[0]
            if section == "7" and not plan.wants_changes and not plan.version:
                score -= 0.25                       # revision tables restate old values; avoid unless asked
            if section in ("1", "2", "6"):
                score -= 0.05
            if site and c.get("parent") and c["site"] == site:
                score += 0.2                        # site annex overrides the global procedure
            hits.append(Hit(c, score, {"rrf": rrf, "bm25": res["bm25"].get(i, 0.0), "dense": res["dense"].get(i, 0.0),
                                       "coverage": coverage}))
        hits.sort(key=lambda h: -h.score)
        out, per_doc = [], {}
        for h in hits:                              # diversity: at most 3 chunks per document version
            key = h.chunk["doc_key"]
            if per_doc.get(key, 0) < 3:
                out.append(h)
                per_doc[key] = per_doc.get(key, 0) + 1
            if len(out) == k:
                break
        return out, {"filters": applied, "candidates": int(mask.sum()), "bm25_hits": len(res["bm25_rank"]),
                     "dense_hits": len(res["dense_rank"]), "fused": len(res["rrf"])}
