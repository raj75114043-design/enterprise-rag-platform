# ADR-0003: Generate documents and golden questions from one specification

**Status:** Accepted · 2026-10-11

## Context
Hand-written evaluation sets drift from the documents they test, and real SOPs cannot be published.

## Decision
`ragp/corpus/spec.py` defines document families, versions, site annexes, access levels and the facts each contains
(with per-version values). `generator.py` renders the Markdown documents and derives the golden questions — current,
historical, site-specific, comparison, follow-up, restricted and unanswerable — from the same facts. CI regenerates
both and fails on any difference from the committed files.

## Consequences
+ Expected answers are always consistent with the documents; adding a fact adds its evaluation cases automatically.
+ Version changes are reflected in each document's revision-history table, which is itself a retrieval challenge.
− Template-generated text is more regular than real SOP prose; results on this corpus overstate real-world accuracy.
