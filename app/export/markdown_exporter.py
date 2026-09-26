"""Renders a `QADeliverable` into the full enterprise QA report as Markdown,
following the exact "Final Deliverables" section order the agent is required
to produce.
"""
from __future__ import annotations

from app.models.schemas import CaseType, QADeliverable, TestCase


def _bullets(items) -> str:
    if not items:
        return "_None identified._\n"
    return "\n".join(f"- {item}" for item in items) + "\n"


def _test_case_table(cases: list[TestCase]) -> str:
    if not cases:
        return "_None._\n"
    lines = [
        "| ID | Title | Priority | Severity | Module | Automation | Tags |",
        "|---|---|---|---|---|---|---|",
    ]
    for tc in cases:
        lines.append(
            f"| {tc.test_case_id} | {tc.title} | {tc.priority.value} | {tc.severity.value} | "
            f"{tc.module} | {'Yes' if tc.automation_candidate else 'No'} | {', '.join(tc.tags)} |"
        )
    return "\n".join(lines) + "\n"


def _detailed_test_case(tc: TestCase) -> str:
    steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(tc.steps)) or "_Not specified_"
    return (
        f"#### {tc.test_case_id} — {tc.title}\n\n"
        f"- **Scenario Ref:** {tc.scenario_ref or '-'}\n"
        f"- **Case Type:** {tc.case_type.value}\n"
        f"- **Coverage Category:** {tc.coverage_category.value}\n"
        f"- **Module:** {tc.module or '-'}\n"
        f"- **Requirement Ref:** {tc.requirement_ref or '-'}\n"
        f"- **Priority / Severity:** {tc.priority.value} / {tc.severity.value}\n"
        f"- **Preconditions:** {'; '.join(tc.preconditions) or '-'}\n"
        f"- **Dependencies:** {'; '.join(tc.dependencies) or '-'}\n"
        f"- **Test Data:** {tc.test_data or '-'}\n"
        f"- **Automation Candidate:** {'Yes' if tc.automation_candidate else 'No'}\n"
        f"- **Tags:** {', '.join(tc.tags) or '-'}\n\n"
        f"**Steps:**\n\n{steps}\n\n"
        f"**Expected Results:** {tc.expected_results or '-'}\n"
    )


def export_markdown(deliverable: QADeliverable) -> str:
    d = deliverable
    parts: list[str] = []
    parts.append(f"# QA Test Design Report — {d.title}\n")
    parts.append(f"_Source: {d.source_type} | Generated: {d.generated_at.isoformat()}Z_\n")

    parts.append("## Executive Summary\n")
    parts.append((d.executive_summary or "_Not generated._") + "\n")

    ru = d.requirement_understanding
    parts.append("## Requirement Understanding\n")
    parts.append(f"**Business Goal:** {ru.business_goal or '-'}\n")
    parts.append(f"**User Goal:** {ru.user_goal or '-'}\n")
    parts.append("**Functional Requirements:**\n" + _bullets(ru.functional_requirements))
    parts.append("**Non-Functional Requirements:**\n" + _bullets(ru.non_functional_requirements))
    parts.append("**Dependencies:**\n" + _bullets(ru.dependencies))
    parts.append("**Integrations:**\n" + _bullets(ru.integrations))
    parts.append("**Constraints:**\n" + _bullets(ru.constraints))
    parts.append(f"**Summary:** {ru.summary or '-'}\n")

    parts.append("## Feature Classification\n")
    parts.append(f"**Category:** {d.feature_classification.category.value}\n")
    parts.append(f"**Rationale:** {d.feature_classification.rationale or '-'}\n")

    parts.append("## Existing Feature Impact Analysis\n")
    if d.impact_analysis.modules:
        parts.append("| Module | Impacted | Description | Related Test Cases | Related Defects |")
        parts.append("|---|---|---|---|---|")
        for m in d.impact_analysis.modules:
            parts.append(
                f"| {m.module} | {'Yes' if m.impacted else 'No'} | {m.impact_description or '-'} | "
                f"{', '.join(m.related_existing_test_cases) or '-'} | {', '.join(m.related_existing_defects) or '-'} |"
            )
        parts.append("")
    parts.append(f"**Summary:** {d.impact_analysis.summary or '-'}\n")

    parts.append("## Requirement Gap Analysis\n")
    if d.gap_analysis.items:
        for item in d.gap_analysis.items:
            q = f" — *Question for PO: {item.question_for_product_owner}*" if item.question_for_product_owner else ""
            parts.append(f"- **[{item.category}]** {item.description}{q}")
        parts.append("")
    else:
        parts.append("_No gaps identified._\n")

    parts.append("## Assumptions\n")
    parts.append(_bullets(d.assumptions))

    parts.append("## Risks\n")
    if d.risks:
        parts.append("| Category | Level | Description |")
        parts.append("|---|---|---|")
        for r in d.risks:
            parts.append(f"| {r.category.value} | {r.level.value} | {r.description} |")
        parts.append("")
    else:
        parts.append("_No risks identified._\n")

    ts = d.test_strategy
    parts.append("## Test Strategy\n")
    parts.append(f"**Scope:** {ts.scope or '-'}\n")
    parts.append(f"**Approach:** {ts.approach or '-'}\n")
    parts.append("**Test Levels:**\n" + _bullets(ts.test_levels))
    parts.append("**Test Design Techniques Applied:**\n" + _bullets(ts.test_design_techniques_applied))
    parts.append("**Entry Criteria:**\n" + _bullets(ts.entry_criteria))
    parts.append("**Exit Criteria:**\n" + _bullets(ts.exit_criteria))
    parts.append("**Environments:**\n" + _bullets(ts.environments))
    parts.append("**Tools:**\n" + _bullets(ts.tools))

    parts.append("## Test Scenarios\n")
    if d.test_scenarios:
        parts.append("| ID | Title | Category | Priority | Requirement Ref |")
        parts.append("|---|---|---|---|---|")
        for s in d.test_scenarios:
            parts.append(f"| {s.scenario_id} | {s.title} | {s.category.value} | {s.priority.value} | {s.requirement_ref or '-'} |")
        parts.append("")
    else:
        parts.append("_No scenarios generated._\n")

    parts.append("## Detailed Test Cases\n")
    for tc in d.test_cases:
        parts.append(_detailed_test_case(tc))

    parts.append("## Negative Scenarios\n")
    parts.append(_test_case_table([tc for tc in d.test_cases if tc.case_type == CaseType.NEGATIVE]))

    parts.append("## Edge Cases\n")
    parts.append(
        _test_case_table(
            [tc for tc in d.test_cases if tc.case_type in (CaseType.EDGE_CASE, CaseType.BOUNDARY)]
        )
    )

    parts.append("## Regression Coverage\n")
    parts.append(_bullets(d.regression_coverage))
    parts.append(
        _test_case_table([tc for tc in d.test_cases if tc.case_type == CaseType.REGRESSION])
    )

    parts.append("## Automation Recommendations\n")
    if d.automation_recommendations:
        parts.append("| Test Case | Tool | Priority | Rationale |")
        parts.append("|---|---|---|---|")
        for rec in d.automation_recommendations:
            parts.append(f"| {rec.test_case_ref} | {rec.tool.value} | {rec.priority.value} | {rec.rationale} |")
        parts.append("")
    else:
        parts.append("_No automation recommendations generated._\n")

    parts.append("## Test Data Requirements\n")
    if d.test_data_requirements:
        parts.append("| Field | Description | Example Values | Source |")
        parts.append("|---|---|---|---|")
        for req in d.test_data_requirements:
            parts.append(f"| {req.field} | {req.description} | {', '.join(req.example_values)} | {req.source} |")
        parts.append("")
    else:
        parts.append("_None identified._\n")

    parts.append("## Production Validation Checklist\n")
    parts.append(_bullets([f"[{i.category}] {i.check}" if i.category else i.check for i in d.production_validation_checklist]))

    parts.append("## Defect Prevention Suggestions\n")
    if d.defect_prevention_suggestions:
        for item in d.defect_prevention_suggestions:
            parts.append(f"- **[{item.area}]** {item.potential_bug_or_edge_case} → _Prevention:_ {item.prevention_recommendation}")
        parts.append("")
    else:
        parts.append("_None identified._\n")

    parts.append("## Questions for Product Owner\n")
    if d.questions_for_product_owner:
        for q in d.questions_for_product_owner:
            parts.append(f"- {q.question} _(context: {q.context})_")
        parts.append("")
    else:
        parts.append("_No open questions._\n")

    parts.append("## Traceability Matrix\n")
    if d.traceability_matrix:
        parts.append("| Requirement | Scenario | Test Case | Automation Script | Defect |")
        parts.append("|---|---|---|---|---|")
        for link in d.traceability_matrix:
            parts.append(
                f"| {link.requirement_ref} | {link.scenario_ref or '-'} | {link.test_case_ref or '-'} | "
                f"{link.automation_script_ref or '-'} | {link.defect_ref or '-'} |"
            )
        parts.append("")

    return "\n".join(parts)
