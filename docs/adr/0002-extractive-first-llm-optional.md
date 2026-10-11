# ADR-0002: Extractive answers by default; the LLM is a writer, not a source of facts

**Status:** Accepted · 2026-10-11

## Context
In GxP documentation a wrong number (a timeline, a limit) is worse than no answer. Free open-weight LLMs write fluent
answers but can alter numbers or cite sources they were not given.

## Decision
1. An extractive answerer always runs. It scores sentences with IDF-weighted concept support and abstains below `MIN_SUPPORT`.
2. If an LLM is configured, it rewrites the answer from the same chunks. The output is accepted only when every
   citation is a retrieved chunk ID and every number in the answer appears in the cited text. One corrective retry
   with explicit feedback is allowed; otherwise the extractive answer is returned.
3. Abstention is decided deterministically, so the LLM is never asked to answer unsupported questions.

## Consequences
+ The system works with no LLM at all (CI, air-gapped sites) and degrades gracefully when the LLM fails or is rate-limited.
+ Hallucinated numbers and citations are caught mechanically, not by prompt wording.
− Extractive answers are less fluent and cannot combine facts spread across sections.
