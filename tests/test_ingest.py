import pytest

from ragp.ingest import IngestError, chunk_document, ingest_directory, parse_front_matter
from ragp.store import Store, make_engine

DOC = """---
doc_id: SOP-T-001
title: Test
version: "1.0"
status: effective
effective_date: 2026-01-01
access: internal
---
# SOP-T-001 — Test
## 1. Purpose
To test chunking of controlled documents properly.
## 5. Procedure
### 5.1 Step one
The first step shall be done within 2 days of receipt.
## 4. Definitions
- Not applicable.
"""


def test_front_matter_validation():
    meta, _ = parse_front_matter(DOC)
    assert meta["doc_id"] == "SOP-T-001" and meta["version"] == "1.0"
    with pytest.raises(IngestError):
        parse_front_matter("no front matter")
    with pytest.raises(IngestError):
        parse_front_matter(DOC.replace("access: internal", "access: secret"))


def test_chunks_follow_headings_and_skip_trivial_sections():
    meta, body = parse_front_matter(DOC)
    chunks = chunk_document(meta, body)
    assert [c["chunk_id"] for c in chunks] == ["SOP-T-001@1.0#1", "SOP-T-001@1.0#5.1"]
    assert chunks[1]["heading"].startswith("SOP-T-001 v1.0 — Test › 5.1")


def test_incremental_ingestion(tmp_path):
    (tmp_path / "a.md").write_text(DOC)
    store = Store(make_engine(f"sqlite:///{tmp_path}/s.db"))
    assert ingest_directory(store, tmp_path)["added"] == 1
    assert ingest_directory(store, tmp_path)["unchanged"] == 1
    (tmp_path / "a.md").write_text(DOC.replace("2 days", "3 days"))
    assert ingest_directory(store, tmp_path)["updated"] == 1
    (tmp_path / "a.md").unlink()
    assert ingest_directory(store, tmp_path)["removed"] == 1
    assert store.documents() == []
