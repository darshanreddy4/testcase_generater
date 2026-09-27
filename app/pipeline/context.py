"""Lightweight container describing a single requirement analysis request,
independent of where the raw text came from (typed text, uploaded document,
or Jira).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class RequirementInput:
    text: str
    source_type: str = "Text"
    title: str = ""
    # Jira keys (primary issue + parent chain + siblings) this requirement is derived
    # from, if any — used to correlate existing test cases tagged with a jira_key.
    related_jira_keys: List[str] = field(default_factory=list)
