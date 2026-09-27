"""Net-new de-duplication: avoid regenerating test cases that already exist,
per the "generate net-new test scenarios only where required" requirement.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Dict, List, Tuple

from app.config import settings
from app.models.schemas import TestCase


def _normalize(title: str) -> str:
    return " ".join(title.lower().split())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def filter_net_new_test_cases(
    test_cases: List[TestCase],
    existing_test_cases: List[Dict[str, str]],
    threshold: float | None = None,
) -> Tuple[List[TestCase], List[str]]:
    """Drop generated test cases whose title closely matches an existing one.

    Returns (net_new_test_cases, skipped_descriptions) where each skipped
    description names the generated case and the existing case it duplicates.
    """
    threshold = threshold if threshold is not None else settings.dedup_similarity_threshold
    if not existing_test_cases:
        return test_cases, []

    kept: List[TestCase] = []
    skipped: List[str] = []
    for tc in test_cases:
        best_ratio = 0.0
        best_match = None
        for existing in existing_test_cases:
            existing_title = existing.get("title", "")
            if not existing_title:
                continue
            ratio = _similarity(tc.title, existing_title)
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = existing
        if best_match is not None and best_ratio >= threshold:
            existing_id = best_match.get("test_case_id", "unknown")
            skipped.append(
                f"{tc.test_case_id} '{tc.title}' skipped — already covered by existing "
                f"{existing_id} '{best_match.get('title', '')}' ({best_ratio:.0%} match)"
            )
        else:
            kept.append(tc)
    return kept, skipped
