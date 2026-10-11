"""Golden-set evaluation with a CI quality gate.

    python -m ragp.eval.run            # report
    python -m ragp.eval.run --gate     # exit 1 if any threshold is breached

Metrics
  recall@k             expected document family among the retrieved chunks (answerable questions)
  mrr                  reciprocal rank of the first chunk from the expected document
  answer_accuracy      every expected value appears in the answer (answerable questions)
  abstention_accuracy  unanswerable and access-denied questions are refused
  false_abstention     answerable questions that were refused
  acl_leakage          any restricted value or chunk returned to a role that may not see it (must be 0)
  stale_version_rate   current-version questions answered from a superseded document
  citation_validity    every citation refers to a retrieved chunk
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from ragp.corpus.spec import ROLES
from ragp.pipeline import ask, get_container

GOLDEN = Path(__file__).resolve().parents[2] / "eval" / "golden.jsonl"
THRESHOLDS = {"recall_at_k": (">=", 0.95), "answer_accuracy": (">=", 0.90), "abstention_accuracy": (">=", 0.90),
              "false_abstention": ("<=", 0.05), "acl_leakage": ("<=", 0.0), "stale_version_rate": ("<=", 0.02),
              "citation_validity": (">=", 1.0)}
REFUSE_TYPES = {"unanswerable", "acl_denied"}


def load(limit: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def evaluate(limit: int | None = None) -> dict:
    c = get_container()
    rows, details = load(limit), []
    by_type: dict[str, list[bool]] = defaultdict(list)
    for g in rows:
        r = ask(c, g["question"], g["role"], previous=g.get("previous"), persist=False)
        ans = r["answer"].lower()
        src_docs = [s["doc_id"] for s in r["sources"]]
        allowed = set(ROLES[g["role"]])
        leak = any(s["access"] not in allowed for s in r["sources"]) or any(f.lower() in ans for f in g.get("forbidden", []))
        d = {"id": g["id"], "type": g["type"], "question": g["question"], "role": g["role"], "abstained": r["abstained"],
             "mode": r["mode"], "latency_ms": r["latency_ms"], "leak": leak,
             "citations_valid": all(cid in {s["chunk_id"] for s in r["sources"]} for cid in r["citations"])}
        if g["type"] in REFUSE_TYPES:
            d["correct"] = r["abstained"]
        else:
            d["hit"] = g["expected_doc"] in src_docs
            d["rr"] = next((1 / (i + 1) for i, doc in enumerate(src_docs) if doc == g["expected_doc"]), 0.0)
            d["correct"] = (not r["abstained"]) and all(e.lower() in ans for e in g["expected"])
            cited_status = {s["chunk_id"]: s["status"] for s in r["sources"]}
            d["stale"] = g["type"] in ("current", "site", "site_fallback", "follow_up", "confidential") and any(
                cited_status.get(cid) == "superseded" for cid in r["citations"])
        if not d["correct"]:
            d["answer"] = r["answer"][:300]
            d["top_sources"] = [s["chunk_id"] for s in r["sources"][:5]]
        by_type[g["type"]].append(d["correct"])
        details.append(d)
    answerable = [d for d in details if d["type"] not in REFUSE_TYPES]
    refuse = [d for d in details if d["type"] in REFUSE_TYPES]
    lat = sorted(d["latency_ms"] for d in details)
    m = {
        "cases": len(details),
        "recall_at_k": statistics.mean(d["hit"] for d in answerable),
        "mrr": statistics.mean(d["rr"] for d in answerable),
        "answer_accuracy": statistics.mean(d["correct"] for d in answerable),
        "abstention_accuracy": statistics.mean(d["correct"] for d in refuse) if refuse else 1.0,
        "false_abstention": statistics.mean(d["abstained"] for d in answerable),
        "acl_leakage": sum(d["leak"] for d in details) / len(details),
        "stale_version_rate": statistics.mean(d["stale"] for d in answerable),
        "citation_validity": statistics.mean(d["citations_valid"] for d in details),
        "latency_p50_ms": lat[len(lat) // 2], "latency_p95_ms": lat[int(len(lat) * 0.95) - 1],
        "by_type": {t: f"{sum(v)}/{len(v)}" for t, v in sorted(by_type.items())},
        "answer_modes": dict(sorted({d["mode"]: sum(1 for x in details if x["mode"] == d["mode"]) for d in details}.items())),
    }
    return {"metrics": m, "failures": [d for d in details if not d["correct"] or d["leak"]], "llm": c.llm.provider}


def gate(m: dict) -> list[str]:
    out = []
    for k, (op, thr) in THRESHOLDS.items():
        ok = m[k] >= thr if op == ">=" else m[k] <= thr
        if not ok:
            out.append(f"{k}={m[k]:.3f} (gate {op} {thr})")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default="reports/eval.json")
    a = ap.parse_args()
    rep = evaluate(a.limit)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rep, indent=2))
    m = rep["metrics"]
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}, indent=2))
    for f in rep["failures"]:
        print("FAIL", json.dumps(f)[:400])
    breaches = gate(m)
    if a.gate:
        print("QUALITY GATE " + ("FAILED: " + "; ".join(breaches) if breaches else "PASSED"))
        sys.exit(1 if breaches else 0)


if __name__ == "__main__":
    main()
