"""Exports the full deliverable (or just the traceability matrix) as JSON,
for ingestion by other tools (Jira sync scripts, dashboards, CI gates, etc.).
"""
from __future__ import annotations

import json

from app.models.schemas import QADeliverable


def export_deliverable_json(deliverable: QADeliverable) -> str:
    return deliverable.model_dump_json(indent=2)


def export_traceability_json(deliverable: QADeliverable) -> str:
    payload = {
        "requirement": deliverable.title,
        "traceability": [link.model_dump(mode="json") for link in deliverable.traceability_matrix],
    }
    return json.dumps(payload, indent=2)
