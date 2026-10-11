# Operations runbook

| Symptom | Check | Action |
|---|---|---|
| `/ready` fails | database reachable? corpus directory mounted? | fix `DATABASE_URL` / `CORPUS_DIR`; run `python -m ragp.cli ingest` |
| Many abstentions after a document update | `ingestion_runs` errors column | fix front matter (required: doc_id, version, title, status, effective_date, access) |
| Answers cite an old version | was the new version ingested with `status: effective` and the old one `superseded`? | correct front matter, re-ingest |
| `mode = extractive_fallback` spikes | `rag_answers_total{mode}`; LLM errors in logs | free-tier rate limit or model change; answers remain correct (extractive) |
| User reports wrong answer | `GET /v1/runs/{run_id}` | add the case to `ragp/corpus/spec.py` or the golden set, fix, confirm the gate passes |

Severity: any access-control leak or stale-version answer is treated as a P1 incident.
