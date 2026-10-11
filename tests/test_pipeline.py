from ragp.answer import ABSTAIN
from ragp.llm import LLMClient
from ragp.pipeline import ask


def test_current_answer_is_cited_from_effective_version(container):
    r = ask(container, "How long do we have to complete a Phase I OOS laboratory investigation?", "qa_analyst", persist=False)
    assert "3 working days" in r["answer"] and r["citations"] == ["SOP-QA-001@4.0#5.1"]


def test_history_question_uses_superseded_version(container):
    r = ask(container, "What was the Phase I OOS investigation timeline in version 3.0?", "qa_analyst", persist=False)
    assert "5 working days" in r["answer"] and "superseded" in r["answer"]


def test_site_annex_overrides_global_procedure(container):
    assert "24 hours" in ask(container, "What is the dirty hold time at Sikkim?", "qa_analyst", persist=False)["answer"]
    assert "48 hours" in ask(container, "What is the dirty hold time at Goa?", "qa_analyst", persist=False)["answer"]


def test_access_control_blocks_restricted_content(container):
    q = "What was the root cause of the contamination in batch MP-2309?"
    denied = ask(container, q, "qa_analyst", persist=False)
    assert denied["abstained"] and all(s["access"] != "confidential" for s in denied["sources"])
    allowed = ask(container, q, "qa_head", persist=False)
    assert "HVAC filter" in allowed["answer"]


def test_operator_cannot_see_internal_documents(container):
    r = ask(container, "What is the residue acceptance limit for cleaning validation?", "operator", persist=False)
    assert r["abstained"] and all(s["access"] == "public" for s in r["sources"])


def test_unanswerable_question_abstains(container):
    r = ask(container, "How often is the purified water system sampled for TOC?", "qa_analyst", persist=False)
    assert r["answer"] == ABSTAIN and r["citations"] == []


class FakeLLM(LLMClient):
    provider, model = "fake", "fake-1"

    def __init__(self, replies):
        self.replies = list(replies)

    @property
    def available(self):
        return True

    def chat(self, system, user, *, json_mode=False, usage=None, max_tokens=700):
        if usage:
            usage.calls += 1
        return self.replies.pop(0)


def _with_llm(container, replies, q="How long do we have to complete a Phase I OOS laboratory investigation?"):
    old = container.answerer.llm
    container.answerer.llm = FakeLLM(replies)
    try:
        return ask(container, q, "qa_analyst", persist=False)
    finally:
        container.answerer.llm = old


def test_llm_answer_accepted_when_citations_and_numbers_verify(container):
    r = _with_llm(container, ["Phase I must be completed within 3 working days [SOP-QA-001@4.0#5.1]."])
    assert r["mode"] == "llm"


def test_llm_hallucinated_number_is_corrected_or_rejected(container):
    r = _with_llm(container, ["Phase I must be completed within 7 working days [SOP-QA-001@4.0#5.1].",
                              "Phase I must be completed within 7 days [SOP-QA-001@4.0#5.1]."])
    assert r["mode"] == "extractive_fallback" and "3 working days" in r["answer"]


def test_llm_invented_citation_triggers_retry(container):
    r = _with_llm(container, ["Within 3 working days [SOP-X@1.0#1].", "Within 3 working days [SOP-QA-001@4.0#5.1]."])
    assert r["mode"] == "llm_corrected"


def test_llm_not_called_when_abstaining(container):
    r = _with_llm(container, [], q="What are the canteen opening hours at the Baddi site?")
    assert r["abstained"] and r["llm"]["calls"] == 0
