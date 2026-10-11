"""Command line: `python -m ragp.cli ingest` or `python -m ragp.cli ask "question" --role qa_analyst`."""
from __future__ import annotations

import argparse
import json

from ragp.pipeline import ask, get_container, reindex


def main() -> None:
    ap = argparse.ArgumentParser(prog="ragp")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest", help="incremental ingestion of the corpus directory")
    q = sub.add_parser("ask", help="ask a question")
    q.add_argument("question")
    q.add_argument("--role", default="qa_analyst", choices=["operator", "qa_analyst", "qa_head"])
    q.add_argument("--previous")
    q.add_argument("--json", action="store_true")
    a = ap.parse_args()
    c = get_container()
    if a.cmd == "ingest":
        print(json.dumps(reindex(c), indent=2))
    else:
        r = ask(c, a.question, a.role, a.previous)
        if a.json:
            print(json.dumps(r, indent=2, default=str))
        else:
            print(r["answer"])
            print(f"\n[{r['mode']} · confidence {r['confidence']} · {r['latency_ms']} ms · {r['run_id']}]")


if __name__ == "__main__":
    main()
