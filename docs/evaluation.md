# Evaluation notes

## Golden set (75 questions)
| Scenario | Count | What it tests |
|---|---|---|
| current | 49 | effective-version facts, paraphrases, acronyms |
| history | 4 | "in version X" questions must use the superseded version and label it |
| site / site_fallback | 4 | annex overrides at its site; global SOP elsewhere |
| comparison | 2 | decomposition and one cited answer per site |
| follow_up | 2 | "And at Baddi?" resolved from the previous question |
| confidential | 4 | qa_head can read restricted records |
| acl_denied | 4 | qa_analyst asking about restricted records must get an abstention |
| unanswerable | 6 | plausible questions the corpus does not cover |

## Known failure
`Q048` "What do we do with material after a temperature excursion?" — the answer cites the reporting requirement
(30 minutes) rather than the quarantine requirement. Both sentences have similar concept support; the extractive
scorer has no notion of the question asking for an *action*. The LLM writer answers it correctly when enabled because it
sees both chunks. Fixing it with a keyword rule would overfit the golden set, so it is left visible.

## Running with an LLM
`GROQ_API_KEY=... python -m ragp.eval.run` evaluates the LLM writer. Expect lower `citation_validity` to be impossible
(guarded) but occasional `extractive_fallback` modes when the free tier rate-limits; the report lists answer modes.
