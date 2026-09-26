"""Lightweight container describing a single requirement analysis request,
independent of where the raw text came from (typed text, uploaded document,
or Jira).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RequirementInput:
    text: str
    source_type: str = "Text"
    title: str = ""
