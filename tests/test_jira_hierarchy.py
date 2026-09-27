from __future__ import annotations

from types import SimpleNamespace

from app.ingestion import jira_client


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, issues: dict, search_results: dict):
        self.issues = issues
        self.search_results = search_results

    def get(self, url, params=None):
        if url.endswith("/comment"):
            return FakeResponse(200, {"comments": []})
        key = url.rsplit("/", 1)[-1]
        if key in self.issues:
            return FakeResponse(200, self.issues[key])
        return FakeResponse(404, {}, text="not found")

    def post(self, url, json=None):
        jql = (json or {}).get("jql", "")
        if jql in self.search_results:
            return FakeResponse(200, {"issues": self.search_results[jql]})
        return FakeResponse(200, {"issues": []})


def _doc(text: str) -> dict:
    return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def make_issue(key: str, issue_type: str, summary: str, parent_key: str | None = None, names: dict | None = None) -> dict:
    fields = {
        "issuetype": {"name": issue_type},
        "status": {"name": "In Progress"},
        "summary": summary,
        "description": _doc(f"{summary} description"),
        "labels": [],
        "issuelinks": [],
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}
    return {"key": key, "fields": fields, "names": names or {}}


def make_search_issue(key: str, issue_type: str, summary: str) -> dict:
    return {
        "key": key,
        "fields": {
            "issuetype": {"name": issue_type},
            "status": {"name": "To Do"},
            "summary": summary,
            "description": _doc(f"{summary} description"),
            "labels": [],
        },
    }


def _patch(monkeypatch, fake_session, max_siblings=20):
    monkeypatch.setattr(
        jira_client, "settings", SimpleNamespace(jira_base_url="https://fake.atlassian.net", jira_max_siblings=max_siblings)
    )
    monkeypatch.setattr(jira_client, "_session", lambda: fake_session)


def test_extract_parent_key_from_standard_parent_field():
    data = make_issue("TASK-1", "Task", "Do the thing", parent_key="STORY-1")
    assert jira_client._extract_parent_key(data) == "STORY-1"


def test_extract_parent_key_from_classic_epic_link_field():
    data = make_issue("STORY-1", "Story", "Some story")
    data["fields"]["customfield_10014"] = "EPIC-1"
    data["names"] = {"customfield_10014": "Epic Link"}
    assert jira_client._extract_parent_key(data) == "EPIC-1"


def test_extract_parent_key_returns_none_when_no_parent():
    data = make_issue("EPIC-1", "Epic", "Top of the chain")
    assert jira_client._extract_parent_key(data) is None


def test_fetch_jira_hierarchy_walks_parent_chain_and_fetches_siblings(monkeypatch):
    issues = {
        "TASK-1": make_issue("TASK-1", "Task", "Add new validation rule", parent_key="STORY-1"),
        "STORY-1": make_issue("STORY-1", "Story", "KYC document upload", parent_key="EPIC-1"),
        "EPIC-1": make_issue("EPIC-1", "Epic", "Identity Verification Platform"),
    }
    search_results = {
        'parent = "STORY-1"': [
            make_search_issue("TASK-1", "Task", "Add new validation rule"),
            make_search_issue("TASK-2", "Task", "Add OCR fallback"),
        ]
    }
    fake_session = FakeSession(issues, search_results)
    _patch(monkeypatch, fake_session)

    hierarchy = jira_client.fetch_jira_hierarchy("TASK-1")

    assert hierarchy.primary.key == "TASK-1"
    assert [a.key for a in hierarchy.ancestors] == ["STORY-1", "EPIC-1"]
    assert [s.key for s in hierarchy.siblings] == ["TASK-2"]  # primary excluded from its own siblings
    assert hierarchy.all_keys == ["TASK-1", "STORY-1", "EPIC-1", "TASK-2"]

    text = hierarchy.to_requirement_text()
    assert "TARGET ISSUE" in text
    assert "STORY-1" in text and "EPIC-1" in text
    assert "TASK-2" in text


def test_fetch_jira_hierarchy_respects_max_siblings_cap(monkeypatch):
    issues = {
        "TASK-1": make_issue("TASK-1", "Task", "T", parent_key="STORY-1"),
        "STORY-1": make_issue("STORY-1", "Story", "S"),
    }
    many_siblings = [make_search_issue(f"SIB-{i}", "Task", f"Sibling {i}") for i in range(5)]
    search_results = {'parent = "STORY-1"': [make_search_issue("TASK-1", "Task", "T")] + many_siblings}
    fake_session = FakeSession(issues, search_results)
    _patch(monkeypatch, fake_session, max_siblings=3)

    hierarchy = jira_client.fetch_jira_hierarchy("TASK-1", max_siblings=3)

    assert len(hierarchy.siblings) == 3
    assert hierarchy.siblings_truncated_count == 2


def test_fetch_jira_hierarchy_falls_back_to_epic_link_jql_for_classic_projects(monkeypatch):
    issues = {
        "TASK-1": make_issue("TASK-1", "Task", "T", parent_key="EPIC-1"),
        "EPIC-1": make_issue("EPIC-1", "Epic", "E"),
    }
    search_results = {
        'parent = "EPIC-1"': [],
        '"Epic Link" = "EPIC-1"': [make_search_issue("STORY-9", "Story", "Some story")],
    }
    fake_session = FakeSession(issues, search_results)
    _patch(monkeypatch, fake_session)

    hierarchy = jira_client.fetch_jira_hierarchy("TASK-1")

    assert [s.key for s in hierarchy.siblings] == ["STORY-9"]


def test_fetch_jira_hierarchy_stops_when_no_parent(monkeypatch):
    issues = {"EPIC-1": make_issue("EPIC-1", "Epic", "Top level, no parent")}
    fake_session = FakeSession(issues, {})
    _patch(monkeypatch, fake_session)

    hierarchy = jira_client.fetch_jira_hierarchy("EPIC-1")

    assert hierarchy.ancestors == []
    assert hierarchy.siblings == []
    assert hierarchy.all_keys == ["EPIC-1"]
