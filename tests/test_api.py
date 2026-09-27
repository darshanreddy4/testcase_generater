import time

from fastapi.testclient import TestClient

from app import api as api_module
from tests.factories import build_sample_deliverable


def test_generate_start_and_result_flow(monkeypatch):
    fake_deliverable = build_sample_deliverable()

    def fake_run_pipeline(requirement, on_stage=None, run_id=None, fresh=False):
        if on_stage:
            on_stage("Analyzing requirement understanding...")
            on_stage("Generating detailed test cases...")
        return fake_deliverable

    monkeypatch.setattr(api_module, "run_pipeline", fake_run_pipeline)

    client = TestClient(api_module.app)

    start_resp = client.post("/api/generate/start", data={"text": "Users should upload a license."})
    assert start_resp.status_code == 200
    job_id = start_resp.json()["job_id"]

    result_resp = None
    for _ in range(50):
        result_resp = client.get(f"/api/jobs/{job_id}/result")
        if result_resp.status_code == 200:
            break
        time.sleep(0.05)
    assert result_resp is not None and result_resp.status_code == 200

    data = result_resp.json()
    assert data["title"] == fake_deliverable.title
    assert data["counts"]["test_cases"] == len(fake_deliverable.test_cases)
    assert "report_markdown" in data
    assert set(data["downloads"].keys()) == {"report_md", "test_cases_xlsx", "deliverable_json", "traceability_json"}


def test_generate_start_requires_a_source():
    client = TestClient(api_module.app)
    resp = client.post("/api/generate/start", data={})
    assert resp.status_code == 400


def test_download_unknown_job_returns_404():
    client = TestClient(api_module.app)
    resp = client.get("/api/jobs/does-not-exist/report.md")
    assert resp.status_code == 404


def test_index_page_loads():
    client = TestClient(api_module.app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "AI QA Test Design Agent" in resp.text
