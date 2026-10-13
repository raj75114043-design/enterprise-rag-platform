"""Grounded answer generation with abstention and citation/number guards.

1. Extractive answerer (always runs): scores sentences of the retrieved chunks against the query with
   IDF-weighted term support. If support is below MIN_SUPPORT the system abstains instead of guessing.
2. LLM answerer (optional, Groq / Ollama): rewrites the answer fluently from the same chunks. Its output is
   accepted only if every citation refers to a retrieved chunk and every number it states appears in the
   cited text; otherwise it gets one corrective retry and then falls back to the extractive answer.
"""
from __future__ import annotations

import json
import math
import re

from ragp.llm import LLMClient, LLMUsage
from ragp.retriever import Hit
from ragp.text import identifiers, query_groups, sentences, tokens

ABSTAIN = ("I could not find this in the controlled documents available to your role. "
           "Please rephrase the question or contact Quality Assurance.")
CITE = re.compile(r"\[([A-Z][A-Z0-9-]+@[\d.]+#[\d.p]+)\]")
NUM = re.compile(r"\b\d+(?:[.,]\d+)?\b")
QUANTITY = re.compile(r"\b\d+(?:\.\d+)?\s*(%|ppm|hours?|days?|minutes?|months?|years?|working|calendar|consecutive)?|"
                      r"\b(monthly|weekly|daily|annually|quarterly|every|before each|immediately|one|two|five)\b", re.I)
QUANTITY_Q = re.compile(r"\b(how (long|often|soon|quickly|fast|many|much)|when|deadline|timeline|limit|frequency|within|"
                        r"how frequently|time|period|pass mark|cpk|value)\b", re.I)
IGNORE = {"site", "goa", "baddi", "sikkim", "version", "compar", "between", "requir", "meridian"}

SYSTEM = """You are a GxP quality-documentation assistant for a pharmaceutical company.
Answer ONLY from the provided document excerpts. Rules:
- Cite the excerpt ID in square brackets after each statement, e.g. [SOP-QA-001@4.0#5.1].
- Copy numbers, durations and limits exactly as written. Never add facts that are not in the excerpts.
- If the excerpts describe different sites or versions, say which value applies where.
- Be concise: at most 90 words, no preamble."""


class Answerer:
    def __init__(self, idf: dict[str, float], min_support: float, llm: LLMClient):
        self.idf, self.min_support, self.llm = idf, min_support, llm
        vals = sorted(idf.values()) or [1.0]
        self.unknown = vals[int(len(vals) * 0.75)]   # a term absent from the corpus is treated as informative

    # ------------------------------------------------------------------ extractive
    def _weight(self, group: set[str]) -> float:
        return max(self.idf.get(t, self.unknown) for t in group)

    def _support(self, groups: list[set[str]], sent: str, heading: str) -> float:
        """IDF-weighted share of query concepts present in the sentence (full credit) or its heading (half credit)."""
        st, ht = set(tokens(sent)), set(tokens(heading))
        total = sum(self._weight(g) for g in groups) or 1.0
        got = sum(self._weight(g) * (1.0 if g & st else 0.5 if g & ht else 0.0) for g in groups)
        return got / total

    def best_sentence(self, query: str, hits: list[Hit], site: str | None = None) -> dict | None:
        qt = [g for g in query_groups(query) if not (g & IGNORE) and not any(re.fullmatch(r"v?\d+\.\d+", t) for t in g)]
        wants_quantity = bool(QUANTITY_Q.search(query))
        anchors = identifiers(query)
        best, candidates = None, []
        for rank, h in enumerate(hits):
            section = h.chunk["section"].split(".")[0]
            annex_for_site = bool(site and h.chunk.get("parent") and h.chunk["site"] == site)
            flat = re.sub(r"[^a-z0-9]", "", (h.chunk["heading"] + h.chunk["text"]).lower())
            anchor_ok = all(a in flat for a in anchors)
            for s in sentences(h.chunk["text"]):
                if len(s.split()) < 5:
                    continue
                sup = self._support(qt, s, h.chunk["heading"]) * (1.0 if anchor_ok else 0.3)
                has_qty = bool(QUANTITY.search(s))
                score = (sup + (0.25 if wants_quantity and has_qty else 0.05 if has_qty else 0)
                         + (0.05 if " shall " in f" {s} " else 0) - (0.15 if section in ("1", "2", "3") else 0)
                         - (0.1 if s.startswith("This annex") else 0) - (0.1 if section == "4" else 0)
                         + (0.15 if annex_for_site else 0) - 0.02 * rank)
                st = set(tokens(s))
                cand = {"sentence": s, "support": sup, "score": score, "hit": h, "covers": {i for i, g in enumerate(qt) if g & st}}
                candidates.append(cand)
                if best is None or score > best["score"]:
                    best = cand
        if best:  # add a second sentence from the same chunk when it is nearly as relevant (e.g. due date + extension)
            runner = max((c for c in candidates if c is not best and c["hit"] is best["hit"]), key=lambda c: c["score"], default=None)
            adds_concept = runner and bool(runner["covers"] - best["covers"])
            if runner and adds_concept and runner["support"] >= 0.8 * self.min_support and runner["score"] >= 0.6 * best["score"] \
                    and QUANTITY.search(runner["sentence"]) and not runner["sentence"].startswith("This annex"):
                best = {**best, "sentence": best["sentence"] + " " + runner["sentence"]}
        return best

    def extractive(self, plan_subs: list[dict], hits_by_sub: list[list[Hit]]) -> dict:
        parts = []
        for sub, hits in zip(plan_subs, hits_by_sub, strict=True):
            parts.append((sub, self.best_sentence(sub["query"], hits, sub["site"])))
        support = min((p[1]["support"] if p[1] else 0.0) for p in parts)
        if support < self.min_support:
            return {"answer": ABSTAIN, "abstained": True, "support": round(support, 3), "citations": [], "confidence": None}
        lines, cites = [], []
        for sub, best in parts:
            c = best["hit"].chunk
            prefix = f"**{sub['site']}:** " if len(parts) > 1 and sub["site"] else ""
            lines.append(f"{'- ' if len(parts) > 1 else ''}{prefix}{best['sentence']} [{c['chunk_id']}]")
            cites.append(c["chunk_id"])
            if c["status"] == "superseded":
                lines.append(f"  _Note: {c['doc_id']} v{c['version']} was superseded on {c['superseded_on']}; this is a historical value._")
            if c.get("parent"):
                lines.append(f"  _{c['doc_id']} is a site annex that modifies {c['parent']} for {c['site']}._")
        conf = "HIGH" if support >= 0.75 else "MEDIUM"
        return {"answer": "\n".join(lines), "abstained": False, "support": round(support, 3), "citations": cites, "confidence": conf}

    # ------------------------------------------------------------------ LLM
    def generate(self, question: str, hits: list[Hit], extractive: dict, usage: LLMUsage) -> tuple[dict, str]:
        if extractive["abstained"] or not self.llm.available:
            return extractive, ("abstained" if extractive["abstained"] else "extractive")
        ctx = [{"id": h.id, "source": h.chunk["heading"], "status": h.chunk["status"], "text": h.chunk["text"]} for h in hits]
        allowed = {h.id: h.chunk["text"] for h in hits}
        prompt = json.dumps({"question": question, "excerpts": ctx})
        for attempt in range(2):
            text = self.llm.chat(SYSTEM, prompt, usage=usage, max_tokens=350)
            if not isinstance(text, str):
                break
            problem = self._check(text, allowed)
            usage.events.append({"model": getattr(self.llm, "model", ""), "ok": True, "rejected": problem} if problem else {"ok": True, "accepted": True})
            if not problem:
                return {**extractive, "answer": text.strip(), "citations": sorted(set(CITE.findall(text)))}, ("llm" if attempt == 0 else "llm_corrected")
            prompt = json.dumps({"question": question, "excerpts": ctx, "previous_answer": text,
                                 "problem": problem + " Rewrite the answer following the rules."})
        return extractive, "extractive_fallback"

    @staticmethod
    def _check(text: str, allowed: dict[str, str]) -> str | None:
        cites = CITE.findall(text)
        if not cites:
            return "The answer has no citations."
        bad = [c for c in cites if c not in allowed]
        if bad:
            return f"These citations are not excerpt IDs: {bad}."
        cited_text = " ".join(allowed[c] for c in cites)
        body = CITE.sub("", text)
        unsupported = [n for n in NUM.findall(body) if n not in cited_text]
        if unsupported:
            return f"These numbers do not appear in the cited excerpts: {unsupported}."
        return None


def idf_table(chunk_rows: list[dict]) -> dict[str, float]:
    df: dict[str, int] = {}
    for c in chunk_rows:
        for t in set(tokens(c["heading"] + " " + c["text"])):
            df[t] = df.get(t, 0) + 1
    n = len(chunk_rows)
    return {t: math.log(1 + n / d) for t, d in df.items()}
