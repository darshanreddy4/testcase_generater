"""Renders a `QADeliverable` into a multi-sheet Excel workbook suitable for
import into test management tools (Zephyr, Xray, TestRail, qTest, etc.).
"""
from __future__ import annotations

from io import BytesIO

import pandas as pd

from app.models.schemas import QADeliverable


def _test_cases_df(deliverable: QADeliverable) -> pd.DataFrame:
    rows = []
    for tc in deliverable.test_cases:
        rows.append(
            {
                "Test Case ID": tc.test_case_id,
                "Title": tc.title,
                "Scenario Ref": tc.scenario_ref,
                "Case Type": tc.case_type.value,
                "Coverage Category": tc.coverage_category.value,
                "Preconditions": "; ".join(tc.preconditions),
                "Dependencies": "; ".join(tc.dependencies),
                "Priority": tc.priority.value,
                "Severity": tc.severity.value,
                "Module": tc.module,
                "Requirement Reference": tc.requirement_ref,
                "Test Data": tc.test_data,
                "Steps": "\n".join(f"{i+1}. {s}" for i, s in enumerate(tc.steps)),
                "Expected Results": tc.expected_results,
                "Automation Candidate": "Yes" if tc.automation_candidate else "No",
                "Tags": ", ".join(tc.tags),
            }
        )
    return pd.DataFrame(rows)


def _scenarios_df(deliverable: QADeliverable) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Scenario ID": s.scenario_id,
                "Title": s.title,
                "Category": s.category.value,
                "Priority": s.priority.value,
                "Requirement Ref": s.requirement_ref,
                "Description": s.description,
            }
            for s in deliverable.test_scenarios
        ]
    )


def _risks_df(deliverable: QADeliverable) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Category": r.category.value, "Level": r.level.value, "Description": r.description} for r in deliverable.risks]
    )


def _automation_df(deliverable: QADeliverable) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Test Case Ref": rec.test_case_ref,
                "Tool": rec.tool.value,
                "Priority": rec.priority.value,
                "Rationale": rec.rationale,
            }
            for rec in deliverable.automation_recommendations
        ]
    )


def _traceability_df(deliverable: QADeliverable) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Requirement": link.requirement_ref,
                "Scenario": link.scenario_ref,
                "Test Case": link.test_case_ref,
                "Automation Script": link.automation_script_ref,
                "Defect": link.defect_ref,
            }
            for link in deliverable.traceability_matrix
        ]
    )


def _impact_df(deliverable: QADeliverable) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Module": m.module,
                "Impacted": "Yes" if m.impacted else "No",
                "Description": m.impact_description,
                "Related Test Cases": ", ".join(m.related_existing_test_cases),
                "Related Defects": ", ".join(m.related_existing_defects),
            }
            for m in deliverable.impact_analysis.modules
        ]
    )


def export_excel(deliverable: QADeliverable) -> bytes:
    """Returns the workbook as raw bytes (write directly to a .xlsx file)."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        _test_cases_df(deliverable).to_excel(writer, sheet_name="Test Cases", index=False)
        _scenarios_df(deliverable).to_excel(writer, sheet_name="Test Scenarios", index=False)
        _impact_df(deliverable).to_excel(writer, sheet_name="Impact Analysis", index=False)
        _risks_df(deliverable).to_excel(writer, sheet_name="Risks", index=False)
        _automation_df(deliverable).to_excel(writer, sheet_name="Automation", index=False)
        _traceability_df(deliverable).to_excel(writer, sheet_name="Traceability", index=False)

        for sheet_name, sheet in writer.sheets.items():
            sheet.column_dimensions["A"].width = 16
            for col_letter in "BCDEFGHIJKLMNOP":
                sheet.column_dimensions[col_letter].width = 32

    return buffer.getvalue()
