from fastapi.testclient import TestClient

from ragp.api import app

client = TestClient(app)


def test_health_and_ready():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json()["chunks"] > 50


def test_auth_required():
    assert client.post("/v1/ask", json={"question": "How often is LIMS audit trail reviewed?"}).status_code == 401


def test_ask_feedback_and_audit_trace():
    r = client.post("/v1/ask", headers={"X-API-Key": "an"}, json={"question": "How often is the LIMS audit trail reviewed?"})
    assert r.status_code == 200 and "monthly" in r.json()["answer"]
    run_id = r.json()["run_id"]
    assert client.post("/v1/feedback", headers={"X-API-Key": "an"}, json={"run_id": run_id, "rating": 1}).status_code == 200
    trace = client.get(f"/v1/runs/{run_id}", headers={"X-API-Key": "an"}).json()
    assert trace["feedback"] == 1 and trace["trace"][0]["step"] == "query_understanding"
    assert client.get(f"/v1/runs/{run_id}", headers={"X-API-Key": "op"}).status_code == 404   # other roles cannot read it


def test_document_library_respects_role():
    ops = client.get("/v1/documents", headers={"X-API-Key": "op"}).json()
    head = client.get("/v1/documents", headers={"X-API-Key": "hd"}).json()
    assert {d["access"] for d in ops} == {"public"} and any(d["access"] == "confidential" for d in head)


def test_ingest_requires_qa_head():
    assert client.post("/v1/ingest", headers={"X-API-Key": "an"}).status_code == 403
    assert client.post("/v1/ingest", headers={"X-API-Key": "hd"}).json()["unchanged"] >= 20
