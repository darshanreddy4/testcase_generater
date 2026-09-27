from __future__ import annotations

from types import SimpleNamespace

from app.ingestion import jira_client
from app.models.schemas import CaseType, TestCase


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, post_handler):
        self._post_handler = post_handler

    def post(self, url, json=None):
        return self._post_handler(url, json)


def _test_case(test_case_id: str = "TC-001") -> TestCase:
    return TestCase(
        test_case_id=test_case_id,
        title="Upload valid license",
        case_type=CaseType.POSITIVE,
        preconditions=["User logged in"],
        steps=["Go to upload page", "Upload file"],
        expected_results="Upload succeeds.",
        tags=["kyc", "upload"],
    )


def test_create_test_case_issue_success(monkeypatch):
    monkeypatch.setattr(jira_client, "settings", SimpleNamespace(jira_base_url="https://fake.atlassian.net"))

    def post_handler(url, json):
        assert url.endswith("/rest/api/3/issue")
        assert json["fields"]["project"] == {"key": "QA"}
        assert json["fields"]["issuetype"] == {"name": "Task"}
        return FakeResponse(201, {"key": "QA-101"})

    monkeypatch.setattr(jira_client, "_session", lambda: FakeSession(post_handler))

    key = jira_client.create_test_case_issue("QA", _test_case())
    assert key == "QA-101"


def test_create_test_case_issue_links_to_parent(monkeypatch):
    monkeypatch.setattr(jira_client, "settings", SimpleNamespace(jira_base_url="https://fake.atlassian.net"))
    calls = []

    def post_handler(url, json):
        calls.append((url, json))
        if url.endswith("/rest/api/3/issue"):
            return FakeResponse(201, {"key": "QA-102"})
        assert url.endswith("/rest/api/3/issueLink")
        assert json["inwardIssue"] == {"key": "QA-102"}
        assert json["outwardIssue"] == {"key": "QA-1"}
        return FakeResponse(201, {})

    monkeypatch.setattr(jira_client, "_session", lambda: FakeSession(post_handler))

    key = jira_client.create_test_case_issue("QA", _test_case(), parent_issue_key="QA-1")
    assert key == "QA-102"
    assert len(calls) == 2


def test_create_test_case_issue_raises_on_failure(monkeypatch):
    monkeypatch.setattr(jira_client, "settings", SimpleNamespace(jira_base_url="https://fake.atlassian.net"))
    monkeypatch.setattr(
        jira_client, "_session", lambda: FakeSession(lambda url, json: FakeResponse(400, text="Bad project key"))
    )

    try:
        jira_client.create_test_case_issue("BAD", _test_case())
        assert False, "expected JiraRequestError"
    except jira_client.JiraRequestError as exc:
        assert "TC-001" in str(exc)


def test_write_back_test_cases_reports_partial_success(monkeypatch):
    monkeypatch.setattr(jira_client, "settings", SimpleNamespace(jira_base_url="https://fake.atlassian.net"))

    def post_handler(url, json):
        if "TC-001" in json["fields"]["summary"]:
            return FakeResponse(201, {"key": "QA-201"})
        return FakeResponse(500, text="server error")

    monkeypatch.setattr(jira_client, "_session", lambda: FakeSession(post_handler))

    created, errors = jira_client.write_back_test_cases("QA", [_test_case("TC-001"), _test_case("TC-002")])
    assert created == {"TC-001": "QA-201"}
    assert len(errors) == 1
    assert "TC-002" in errors[0]
