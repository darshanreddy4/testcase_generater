from app.export.markdown_exporter import export_markdown
from tests.factories import build_sample_deliverable


def test_export_markdown_contains_all_required_sections():
    deliverable = build_sample_deliverable()
    report = export_markdown(deliverable)

    required_sections = [
        "## Executive Summary",
        "## Requirement Understanding",
        "## Feature Classification",
        "## Existing Feature Impact Analysis",
        "## Requirement Gap Analysis",
        "## Assumptions",
        "## Risks",
        "## Test Strategy",
        "## Test Scenarios",
        "## Detailed Test Cases",
        "## Negative Scenarios",
        "## Edge Cases",
        "## Regression Coverage",
        "## Automation Recommendations",
        "## Test Data Requirements",
        "## Production Validation Checklist",
        "## Defect Prevention Suggestions",
        "## Questions for Product Owner",
        "## Traceability Matrix",
    ]
    for section in required_sections:
        assert section in report, f"Missing section: {section}"

    assert "TC-001" in report
    assert "TC-002" in report
    assert "What should happen if the license is expired?" in report
