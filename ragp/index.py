"""Hybrid index: BM25 (lexical) + dense vectors, fused with Reciprocal Rank Fusion.

Dense backends
  lsa        TF-IDF + truncated SVD (latent semantic analysis). Fully offline; default for CI and the demo.
  fastembed  BAAI/bge-small-en-v1.5 via ONNX Runtime (no PyTorch). Set EMBEDDINGS=fastembed.
Both backends embed the chunk breadcrumb header together with the text ("contextual chunk headers").
"""
from __future__ import annotations

import logging

import numpy as np
from rank_bm25 import BM25Okapi

from ragp.text import query_tokens, tokens

log = logging.getLogger("ragp.index")


class LSAEmbedder:
    name = "lsa-tfidf-svd"

    def fit(self, texts: list[str]) -> np.ndarray:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vec = TfidfVectorizer(tokenizer=tokens, lowercase=False, ngram_range=(1, 2), sublinear_tf=True, min_df=1,
                                   token_pattern=None)
        x = self.vec.fit_transform(texts)
        self.svd = TruncatedSVD(n_components=min(128, x.shape[1] - 1, x.shape[0] - 1), random_state=0)
        return self._norm(self.svd.fit_transform(x))

    def encode(self, texts: list[str]) -> np.ndarray:
        return self._norm(self.svd.transform(self.vec.transform(texts)))

    @staticmethod
    def _norm(m: np.ndarray) -> np.ndarray:
        return m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-9, None)


class FastEmbedder(LSAEmbedder):  # pragma: no cover - needs model download
    name = "bge-small-en-v1.5"

    def fit(self, texts):
        from fastembed import TextEmbedding
        self.model = TextEmbedding("BAAI/bge-small-en-v1.5")
        return self.encode(texts)

    def encode(self, texts):
        return self._norm(np.array(list(self.model.embed(texts))))


class HybridIndex:
    def __init__(self, chunk_rows: list[dict], embeddings: str = "lsa"):
        self.chunks = chunk_rows
        self.ids = [c["chunk_id"] for c in chunk_rows]
        docs = [f"{c['heading']}. {c['text']}" for c in chunk_rows]
        self.bm25 = BM25Okapi([tokens(d) for d in docs])
        try:
            self.embedder = FastEmbedder() if embeddings == "fastembed" else LSAEmbedder()
            self.vectors = self.embedder.fit(docs)
        except Exception as exc:  # fall back to the offline embedder rather than failing startup
            log.warning("embedder_fallback", extra={"requested": embeddings, "error": str(exc)[:200]})
            self.embedder = LSAEmbedder()
            self.vectors = self.embedder.fit(docs)

    def search(self, query: str, allowed: np.ndarray, k: int = 30) -> dict:
        """Return per-retriever ranked candidate indices plus fused RRF scores, restricted to `allowed` rows."""
        qt = query_tokens(query)
        bm = np.array(self.bm25.get_scores(qt)) if qt else np.zeros(len(self.ids))
        dense = self.vectors @ self.embedder.encode([query])[0]
        bm[~allowed], dense[~allowed] = -np.inf, -np.inf
        bm_rank = [i for i in np.argsort(-bm)[:k] if np.isfinite(bm[i]) and bm[i] > 0]
        dn_rank = [i for i in np.argsort(-dense)[:k] if np.isfinite(dense[i])]
        rrf: dict[int, float] = {}
        for ranking in (bm_rank, dn_rank):
            for r, i in enumerate(ranking):
                rrf[int(i)] = rrf.get(int(i), 0.0) + 1.0 / (60 + r + 1)
        return {"bm25": {int(i): float(bm[i]) for i in bm_rank}, "dense": {int(i): float(dense[i]) for i in dn_rank},
                "rrf": rrf, "bm25_rank": [int(i) for i in bm_rank], "dense_rank": [int(i) for i in dn_rank]}
