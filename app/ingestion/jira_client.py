"""Jira integration: pulls story/epic/task/bug context (summary, description,
acceptance criteria, linked issues, comments) via the Jira Cloud REST API v3.

Requires JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN to be configured.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests

from app.config import settings
from app.models.schemas import TestCase


class JiraNotConfiguredError(RuntimeError):
    pass


class JiraRequestError(RuntimeError):
    pass


@dataclass
class LinkedIssue:
    key: str
    relationship: str
    summary: str = ""


@dataclass
class JiraContext:
    key: str
    issue_type: str
    status: str
    summary: str
    description: str
    labels: List[str] = field(default_factory=list)
    acceptance_criteria: str = ""
    linked_issues: List[LinkedIssue] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)

    def to_requirement_text(self) -> str:
        lines = [
            f"Jira {self.issue_type} {self.key}: {self.summary}",
            f"Status: {self.status}",
            f"Labels: {', '.join(self.labels) if self.labels else 'None'}",
            "",
            "Description:",
            self.description or "(no description provided)",
        ]
        if self.acceptance_criteria:
            lines += ["", "Acceptance Criteria:", self.acceptance_criteria]
        if self.linked_issues:
            lines += ["", "Linked Issues:"]
            lines += [f"- {li.relationship} {li.key}: {li.summary}" for li in self.linked_issues]
        if self.comments:
            lines += ["", "Relevant Comments:"]
            lines += [f"- {c}" for c in self.comments[:10]]
        return "\n".join(lines)


def _adf_to_text(node) -> str:
    """Best-effort flatten of Atlassian Document Format (ADF) to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        children = node.get("content", [])
        text = "".join(_adf_to_text(child) for child in children)
        if node.get("type") in {"paragraph", "heading", "listItem"}:
            return text + "\n"
        return text
    if isinstance(node, list):
        return "".join(_adf_to_text(child) for child in node)
    return ""


def _session() -> requests.Session:
    if not settings.jira_configured:
        raise JiraNotConfiguredError(
            "Jira is not configured. Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN in your .env file."
        )
    s = requests.Session()
    s.auth = (settings.jira_email, settings.jira_api_token)
    s.headers.update({"Accept": "application/json"})
    return s


def fetch_jira_context(issue_key: str) -> JiraContext:
    session = _session()
    url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{issue_key}"
    resp = session.get(url, params={"expand": "renderedFields,names"})
    if resp.status_code != 200:
        raise JiraRequestError(f"Jira request for {issue_key} failed: {resp.status_code} {resp.text[:300]}")
    data = resp.json()
    fields = data.get("fields", {})

    description_raw = fields.get("description")
    description = _adf_to_text(description_raw).strip() if description_raw else ""

    acceptance_criteria = ""
    for field_name, value in fields.items():
        if field_name.startswith("customfield_") and isinstance(value, (dict, list)):
            text = _adf_to_text(value).strip()
            if text and "acceptance" in field_name.lower():
                acceptance_criteria = text
    if not acceptance_criteria and "acceptance criteria" in description.lower():
        idx = description.lower().index("acceptance criteria")
        acceptance_criteria = description[idx:]

    linked_issues = []
    for link in fields.get("issuelinks", []):
        rel_type = link.get("type", {})
        if "outwardIssue" in link:
            issue = link["outwardIssue"]
            relationship = rel_type.get("outward", "relates to")
        elif "inwardIssue" in link:
            issue = link["inwardIssue"]
            relationship = rel_type.get("inward", "relates to")
        else:
            continue
        linked_issues.append(
            LinkedIssue(
                key=issue.get("key", ""),
                relationship=relationship,
                summary=issue.get("fields", {}).get("summary", ""),
            )
        )

    comments = []
    comment_url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{issue_key}/comment"
    comment_resp = session.get(comment_url, params={"maxResults": 10})
    if comment_resp.status_code == 200:
        for c in comment_resp.json().get("comments", []):
            text = _adf_to_text(c.get("body")).strip()
            if text:
                comments.append(text)

    return JiraContext(
        key=data.get("key", issue_key),
        issue_type=fields.get("issuetype", {}).get("name", "Story"),
        status=fields.get("status", {}).get("name", ""),
        summary=fields.get("summary", ""),
        description=description,
        labels=fields.get("labels", []),
        acceptance_criteria=acceptance_criteria,
        linked_issues=linked_issues,
        comments=comments,
    )


def _adf_paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _test_case_description_adf(test_case: TestCase) -> dict:
    content = []
    if test_case.preconditions:
        content.append(_adf_paragraph("Preconditions: " + "; ".join(test_case.preconditions)))
    if test_case.test_data:
        content.append(_adf_paragraph(f"Test Data: {test_case.test_data}"))
    content.append(_adf_paragraph("Steps:"))
    content.append(
        {
            "type": "orderedList",
            "content": [
                {"type": "listItem", "content": [_adf_paragraph(step)]} for step in (test_case.steps or ["Not specified"])
            ],
        }
    )
    content.append(_adf_paragraph(f"Expected Results: {test_case.expected_results or '-'}"))
    return {"type": "doc", "version": 1, "content": content}


def create_test_case_issue(
    project_key: str,
    test_case: TestCase,
    issue_type_name: str = "Task",
    parent_issue_key: Optional[str] = None,
) -> str:
    """Creates a Jira issue for a single generated test case and returns its key.

    `issue_type_name` should match a real issue type in the target project (e.g. "Test"
    if Xray/Zephyr is installed, otherwise a standard type like "Task"/"Sub-task").
    """
    session = _session()
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": f"[{test_case.test_case_id}] {test_case.title}",
            "issuetype": {"name": issue_type_name},
            "description": _test_case_description_adf(test_case),
            "labels": [t.replace(" ", "-") for t in test_case.tags],
        }
    }
    url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue"
    resp = session.post(url, json=payload)
    if resp.status_code not in (200, 201):
        raise JiraRequestError(f"Failed to create issue for {test_case.test_case_id}: {resp.status_code} {resp.text[:300]}")
    new_key = resp.json()["key"]

    if parent_issue_key:
        link_payload = {
            "type": {"name": "Relates"},
            "inwardIssue": {"key": new_key},
            "outwardIssue": {"key": parent_issue_key},
        }
        link_url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issueLink"
        link_resp = session.post(link_url, json=link_payload)
        if link_resp.status_code not in (200, 201):
            raise JiraRequestError(
                f"Created {new_key} but failed to link it to {parent_issue_key}: "
                f"{link_resp.status_code} {link_resp.text[:300]}"
            )

    return new_key


def write_back_test_cases(
    project_key: str,
    test_cases: List[TestCase],
    issue_type_name: str = "Task",
    parent_issue_key: Optional[str] = None,
) -> "tuple[Dict[str, str], List[str]]":
    """Creates a Jira issue per test case. Best-effort: a failure on one test case is
    recorded in `errors` and does not stop the rest from being created.

    Returns (created, errors): a mapping of test_case_id -> created Jira issue key for
    every test case that succeeded, and a list of error messages for any that failed.
    """
    created: Dict[str, str] = {}
    errors: List[str] = []
    for test_case in test_cases:
        try:
            created[test_case.test_case_id] = create_test_case_issue(
                project_key, test_case, issue_type_name=issue_type_name, parent_issue_key=parent_issue_key
            )
        except JiraRequestError as exc:
            errors.append(str(exc))
    return created, errors
