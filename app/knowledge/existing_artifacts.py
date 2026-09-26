"""Loads the local knowledge base of existing test cases / defects used for
impact analysis and regression coverage. Backed by simple CSV files so any
team can export their test management / defect tracking tool into this shape
without needing a live integration.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Dict

from app.config import settings


def _load_csv(path_str: str) -> List[Dict[str, str]]:
    path = Path(path_str)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_existing_test_cases() -> List[Dict[str, str]]:
    return _load_csv(settings.existing_test_cases_csv)


def load_existing_defects() -> List[Dict[str, str]]:
    return _load_csv(settings.existing_defects_csv)
