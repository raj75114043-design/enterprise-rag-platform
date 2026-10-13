"""Quality knowledge assistant console (Streamlit)."""
from __future__ import annotations

import os
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)

import streamlit as st  # noqa: E402

try:  # Streamlit Cloud secrets -> environment (GROQ_API_KEY enables the LLM answer writer)
    for key in ("GROQ_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "EMBEDDINGS"):
        if key in st.secrets:
            os.environ[key] = str(st.secrets[key])
except Exception:
    pass

import pandas as pd  # noqa: E402

from ragp.corpus.spec import ROLES  # noqa: E402
from ragp.ingest import IngestError, parse_front_matter  # noqa: E402
from ragp.pipeline import ask, get_container, reindex  # noqa: E402

st.set_page_config(page_title="Enterprise RAG Platform", page_icon="📘", layout="wide")
c = get_container()

EXAMPLES = {
    "Current procedure": "How long do we have to complete a Phase I OOS laboratory investigation?",
    "Version history": "What was the Phase I OOS investigation timeline in version 3.0?",
    "Site annex": "What is the dirty hold time at Sikkim?",
    "Comparison": "Compare the minor deviation closure timeline between Goa and Baddi.",
    "Acronyms": "How often should the HPLC audit trail be reviewed?",
    "Restricted (try as qa_analyst, then qa_head)": "What was the root cause of the contamination in batch MP-2309?",
    "Not in the documents": "How often is the purified water system sampled for TOC?",
}

with st.sidebar:
    st.markdown("### 📘 Enterprise RAG Platform")
    st.caption("Governed question answering over GxP controlled documents · Meridian Pharma (fictional)")
    role = st.selectbox("Signed-in role (simulated SSO)", list(ROLES), index=1,
                        help="Access control is enforced before retrieval: operator → public, qa_analyst → +internal, qa_head → +confidential")
    st.caption(f"Can read: {', '.join(ROLES[role])} documents")
    llm = f"{c.llm.provider} · {c.llm.model}" if c.llm.available else "none (extractive answers)"
    st.markdown(f"**LLM:** `{llm}`  \n**Embeddings:** `{c.index.embedder.name}`  \n**Chunks indexed:** `{len(c.index.ids)}`")
    st.divider()
    st.markdown("**Try a scenario**")
    for label, q in EXAMPLES.items():
        if st.button(label, width="stretch", help=q):
            st.session_state["pending"] = q
    if st.button("Follow-up: 'And at Baddi?'", width="stretch", help="Asks 'What is the closure timeline for a minor deviation?' then 'And at Baddi?'"):
        st.session_state["history"] = []
        st.session_state["queue"] = ["What is the closure timeline for a minor deviation?", "And at Baddi?"]
    if st.button("Clear conversation", width="stretch"):
        st.session_state["history"] = []
    st.divider()
    st.caption("Synthetic documents only. Set `GROQ_API_KEY` to let an open-weight LLM write the answer; citations and numbers are verified.")

st.session_state.setdefault("history", [])
tab_ask, tab_docs, tab_ingest, tab_eval, tab_arch = st.tabs(["💬 Ask", "📚 Documents", "⚙️ Ingestion", "🧪 Evaluation", "🏗️ Architecture"])


def run_question(q: str):
    prev = st.session_state["history"][-1]["question"] if st.session_state["history"] else None
    st.session_state["history"].append(ask(c, q, role, previous=prev))


with tab_ask:
    queue = st.session_state.pop("queue", None) or ([st.session_state.pop("pending")] if "pending" in st.session_state else [])
    typed = st.chat_input("Ask about an SOP, policy or site annex…")
    for q in queue + ([typed] if typed else []):
        run_question(q)
    if not st.session_state["history"]:
        st.info("Ask a question, or pick a scenario in the sidebar. Switch roles to see access control in action.")
    for i, r in enumerate(st.session_state["history"]):
        with st.chat_message("user"):
            st.markdown(r["question"])
            if r["resolved_question"] != r["question"]:
                st.caption(f"Interpreted as: {r['resolved_question']}")
        with st.chat_message("assistant"):
            (st.warning if r["abstained"] else st.markdown)(r["answer"])
            st.caption(f"{r['mode']} · confidence {r['confidence'] or '—'} · support {r['support']} · {r['latency_ms']} ms · "
                       f"role {r['role']} · LLM calls {r['llm']['calls']} · `{r['run_id']}`")
            if r["llm"].get("errors"):
                e = r["llm"]["errors"][-1]
                st.caption(f"⚠️ LLM call failed ({e.get('error')} {e.get('status') or ''}) — check GROQ_API_KEY in the app secrets; extractive answer shown.")
            elif r["mode"] == "extractive_fallback" and r["llm"].get("rejections"):
                st.caption(f"LLM draft rejected by the citation/number check: {r['llm']['rejections'][-1]} Extractive answer shown.")
            cited = [s for s in r["sources"] if s["chunk_id"] in r["citations"]]
            if cited:
                with st.expander(f"Sources ({len(cited)})"):
                    for s in cited:
                        badge = "🟢 effective" if s["status"] == "effective" else "🟠 superseded"
                        st.markdown(f"**{s['heading']}**  \n{badge} · {s['access']} · {s['site']} · `{s['chunk_id']}`")
                        st.caption(s["text"])
            with st.expander("Retrieval trace"):
                for info in r["retrieval"]:
                    st.markdown("Filters applied before search: " + " · ".join(info["filters"]) + f" — {info['candidates']} eligible chunks")
                st.dataframe(pd.DataFrame([{k: v for k, v in s.items() if k in ("chunk_id", "status", "score", "rrf", "bm25", "dense", "coverage")}
                                           for s in r["sources"]]), hide_index=True, width="stretch")
                st.json(r["trace"], expanded=False)
            a, b, _ = st.columns([1, 1, 8])
            if a.button("👍", key=f"up{i}"):
                c.store.add_feedback(r["run_id"], 1, None)
                st.toast("Feedback recorded")
            if b.button("👎", key=f"down{i}"):
                c.store.add_feedback(r["run_id"], -1, None)
                st.toast("Feedback recorded — this answer will be reviewed")

with tab_docs:
    docs = pd.DataFrame(c.store.documents(ROLES[role]))
    st.markdown(f"**{len(docs)} document versions visible to `{role}`** (restricted documents are not listed)")
    st.dataframe(docs[["doc_id", "version", "title", "doc_type", "status", "effective_date", "superseded_on", "access", "site", "parent"]],
                 hide_index=True, width="stretch")
    pick = st.selectbox("Open a document", [f"{d['doc_id']}@{d['version']}" for d in c.store.documents(ROLES[role])])
    src = next(d["source"] for d in c.store.documents(ROLES[role]) if f"{d['doc_id']}@{d['version']}" == pick)
    st.markdown(Path(c.settings.corpus_dir, src).read_text(encoding="utf-8").split("---", 2)[2])

with tab_ingest:
    st.markdown("Incremental ingestion: unchanged documents are skipped by content hash, changed ones are re-chunked, removed ones are deleted.")
    if role != "qa_head":
        st.info("Uploading and re-indexing are restricted to `qa_head`.")
    else:
        up = st.file_uploader("Upload a controlled document (Markdown with front matter)", type=["md"])
        if up is not None:
            text = up.getvalue().decode("utf-8")
            try:
                meta, _ = parse_front_matter(text)
                Path(c.settings.corpus_dir, Path(up.name).name).write_text(text, encoding="utf-8")
                st.success(f"Validated {meta['doc_id']} v{meta['version']} ({meta['status']}, {meta['access']}). Run ingestion to index it.")
            except IngestError as exc:
                st.error(f"Rejected: {exc}")
        if st.button("Run incremental ingestion", type="primary"):
            st.json(reindex(c))
    st.markdown("**Ingestion history**")
    st.dataframe(pd.DataFrame(c.store.ingestion_history()), hide_index=True, width="stretch")
    st.markdown("**Recent questions**")
    st.dataframe(pd.DataFrame(c.store.recent_runs(20)), hide_index=True, width="stretch")

with tab_eval:
    st.markdown("Runs the golden set (current, version history, site annex, comparison, follow-up, restricted and unanswerable "
                "questions) through the full pipeline and checks the CI quality gates.")
    if st.button("Run evaluation", type="primary"):
        from ragp.eval.run import THRESHOLDS, evaluate, gate
        with st.spinner("Evaluating 75 questions…"):
            rep = evaluate()
        m = rep["metrics"]
        cols = st.columns(4)
        for col, k in zip(cols * 2, ["recall_at_k", "answer_accuracy", "abstention_accuracy", "false_abstention", "acl_leakage",
                                      "stale_version_rate", "citation_validity", "mrr"], strict=False):
            col.metric(k.replace("_", " ").title(), f"{m[k]:.1%}", help=f"Gate: {THRESHOLDS.get(k, '—')}")
        breaches = gate(m)
        (st.error if breaches else st.success)("Quality gate " + ("FAILED: " + "; ".join(breaches) if breaches else "PASSED"))
        st.markdown("**Accuracy by scenario**")
        st.table(pd.DataFrame(m["by_type"].items(), columns=["scenario", "correct"]))
        if rep["failures"]:
            st.markdown("**Failures**")
            st.dataframe(pd.DataFrame(rep["failures"]), hide_index=True, width="stretch")

with tab_arch:
    st.graphviz_chart("""
    digraph R { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#f4f4f4", fontname=Helvetica];
      D [label="Controlled documents\\n(Markdown + front matter)"]; I [label="Incremental ingestion\\nhash · heading chunking"];
      S [label="PostgreSQL / SQLite\\ndocuments · chunks · query log"]; X [label="Hybrid index\\nBM25 + dense (LSA / bge-small)"];
      Q [label="Query understanding\\nfollow-ups · sites · versions · comparisons"]; F [label="Governance filters\\nrole ACL · version · site"];
      R [label="Retrieve + RRF + rerank"]; E [label="Extractive answer\\nsupport score → abstain"]; L [label="LLM writer (optional)\\ncitation + number guard"];
      A [label="Answer + citations\\n+ audit trace"];
      D -> I -> S -> X; Q -> F -> R; X -> R -> E -> L -> A; E -> A [style=dashed, label="no LLM / guard failed"]; }""")
    st.markdown("Source, ADRs and evaluation notes are in the GitHub repository.")
