"""Per-stage prompt builders for the QA pipeline.

Each function returns the *user* prompt text for one pipeline stage. The
master persona (`SYSTEM_PROMPT`) plus the target Pydantic schema are combined
with this text by `LLMClient.generate_structured`.
"""
from __future__ import annotations

import json
from typing import List, Optional

STANDARD_IMPACT_MODULES: List[str] = [
    "Login",
    "Registration",
    "KYC",
    "Fraud",
    "Payments",
    "Documents",
    "Profile",
    "Notifications",
    "Reporting",
    "Admin Portal",
]


def _existing_artifacts_block(existing_test_cases: list, existing_defects: list) -> str:
    tc_preview = json.dumps(existing_test_cases[:50], indent=2) if existing_test_cases else "[]"
    defect_preview = json.dumps(existing_defects[:50], indent=2) if existing_defects else "[]"
    return (
        f"\nExisting test cases (sample, for regression/impact reference):\n{tc_preview}\n"
        f"\nPreviously closed/known defects (sample, for regression/impact reference):\n{defect_preview}\n"
    )


def requirement_understanding_prompt(requirement_text: str, source_type: str, extra_context: str = "") -> str:
    return (
        "STEP 1 — Requirement Understanding.\n"
        f"Source type: {source_type}\n"
        f"Requirement / input content:\n\"\"\"\n{requirement_text}\n\"\"\"\n"
        f"{extra_context}\n"
        "Identify the Business Goal, User Goal, Functional Requirements, Non-Functional "
        "Requirements, Dependencies, Integrations, Constraints, and Assumptions. Then write a "
        "concise Requirement Summary. Be specific — extract concrete statements from the input, "
        "do not paraphrase generically."
    )


def feature_classification_prompt(requirement_text: str, requirement_summary: str) -> str:
    return (
        "STEP 2 — Feature Classification.\n"
        f"Requirement:\n\"\"\"\n{requirement_text}\n\"\"\"\n"
        f"Requirement summary so far:\n{requirement_summary}\n\n"
        "Classify this requirement as exactly one of: New Feature, Existing Feature Enhancement, "
        "Bug Fix, Configuration Change, UI Change, API Change, Workflow Change, Migration. "
        "Provide a short rationale citing evidence from the requirement text."
    )


def impact_analysis_prompt(
    requirement_text: str,
    requirement_summary: str,
    existing_test_cases: list,
    existing_defects: list,
) -> str:
    modules_list = ", ".join(STANDARD_IMPACT_MODULES)
    return (
        "STEP 3 — Existing Feature Impact Analysis.\n"
        f"Requirement:\n\"\"\"\n{requirement_text}\n\"\"\"\n"
        f"Requirement summary:\n{requirement_summary}\n"
        f"{_existing_artifacts_block(existing_test_cases, existing_defects)}\n"
        f"Evaluate impact against EACH of these standard enterprise modules, even if the answer is "
        f"'not impacted': {modules_list}. Also add any other clearly relevant module you infer from the "
        "requirement or existing artifacts. For every impacted module, list related existing test case "
        "IDs and defect IDs (from the samples above) if any match, and describe the nature of the impact. "
        "Produce an overall impact summary."
    )


def gap_analysis_prompt(requirement_text: str, requirement_summary: str) -> str:
    return (
        "STEP 4 — Requirement Gap Analysis.\n"
        f"Requirement:\n\"\"\"\n{requirement_text}\n\"\"\"\n"
        f"Requirement summary:\n{requirement_summary}\n\n"
        "Identify: Missing Acceptance Criteria, Ambiguous Behaviors, Missing Error Handling, "
        "Undefined Business Rules, Missing API Contracts, and Missing Validation Rules. For each "
        "gap that is genuinely ambiguous (not something you can safely assume), craft a precise "
        "question for the Product Owner. Do not fabricate gaps that don't exist — be honest if "
        "coverage is already clear for a category."
    )


def risk_analysis_prompt(requirement_text: str, requirement_summary: str, feature_category: str) -> str:
    return (
        "STEP 5 — Risk Analysis.\n"
        f"Requirement:\n\"\"\"\n{requirement_text}\n\"\"\"\n"
        f"Summary: {requirement_summary}\nFeature classification: {feature_category}\n\n"
        "Identify Business Risk, Technical Risk, Security Risk, and Production Risk items. For each, "
        "assign a level (High/Medium/Low) and describe the concrete consequence "
        "(e.g. 'Identity Verification Failure may prevent customer onboarding'). Prioritize risks that "
        "matter in a regulated, high-availability, customer-facing enterprise system."
    )


def test_strategy_prompt(requirement_text: str, requirement_summary: str, feature_category: str, risks_summary: str) -> str:
    return (
        "STEP 6 — Test Strategy.\n"
        f"Requirement:\n\"\"\"\n{requirement_text}\n\"\"\"\n"
        f"Summary: {requirement_summary}\nFeature classification: {feature_category}\nKey risks: {risks_summary}\n\n"
        "Define scope, test approach, applicable test levels (unit/integration/system/UAT/regression/"
        "performance/security as relevant), which test design techniques apply and why "
        "(Equivalence Partitioning, Boundary Value Analysis, Decision Table, State Transition, Pairwise, "
        "Error Guessing, Cause-Effect Graph, User Journey, Risk-Based, Exploratory, Use Case, CRUD, "
        "Workflow), entry/exit criteria, target environments, and recommended tools."
    )


def test_scenarios_prompt(requirement_text: str, requirement_summary: str, impact_summary: str) -> str:
    return (
        "STEP 7 — Test Scenarios.\n"
        f"Requirement:\n\"\"\"\n{requirement_text}\n\"\"\"\n"
        f"Summary: {requirement_summary}\nImpact analysis summary: {impact_summary}\n\n"
        "Generate a comprehensive, de-duplicated list of test scenarios covering Functional "
        "(positive/negative/alternate flow), UI, API, Database, Security, Accessibility, Performance, "
        "Regression, and Integration categories — only include categories that are genuinely "
        "applicable to this requirement, but Functional and Security must always be considered. "
        "Assign each scenario a unique scenario_id like 'SC-001', 'SC-002', ... and a priority. "
        "Reference the specific functional/non-functional requirement it traces to in requirement_ref "
        "when possible (short phrase is fine)."
    )


def test_cases_prompt(
    requirement_text: str,
    requirement_summary: str,
    scenarios_json: str,
    module_hint: str,
    existing_test_case_titles: Optional[List[str]] = None,
) -> str:
    existing_block = ""
    if existing_test_case_titles:
        titles = "\n".join(f"- {t}" for t in existing_test_case_titles[:100])
        existing_block = (
            "\nThese test cases ALREADY EXIST for this module — do NOT regenerate equivalent "
            f"coverage for them; only produce net-new test cases:\n{titles}\n"
        )
    return (
        "STEP 8 — Detailed Test Cases.\n"
        f"Requirement:\n\"\"\"\n{requirement_text}\n\"\"\"\n"
        f"Summary: {requirement_summary}\n"
        f"Primary module: {module_hint}\n"
        f"Approved test scenarios to cover:\n{scenarios_json}\n"
        f"{existing_block}\n"
        "For EACH scenario, produce one or more detailed test cases. Every test case must include: "
        "test_case_id (e.g. 'TC-001', unique, sequential), title, scenario_ref (the scenario_id it "
        "covers), case_type (Positive/Negative/Alternate Flow/Boundary/Edge Case/Security/"
        "Accessibility/Performance/Regression/Integration), coverage_category, preconditions, "
        "dependencies, priority, severity, module, requirement_ref, test_data (concrete example "
        "values, not placeholders), steps (numbered, actionable, specific), expected_results "
        "(precise and verifiable), automation_candidate (true/false), and tags. "
        "You MUST include a healthy mix of case_type values — never only Positive. Include boundary "
        "values, invalid/negative inputs, security abuse cases (auth bypass, injection, session, "
        "sensitive data exposure) where relevant, and accessibility checks for any UI. Avoid "
        "duplicate or overlapping test cases, and avoid duplicating anything already covered by "
        "the existing test cases listed above."
    )


def automation_recommendations_prompt(test_cases_json: str) -> str:
    return (
        "STEP 9 — Automation Analysis.\n"
        f"Test cases:\n{test_cases_json}\n\n"
        "For each test case where automation_candidate is true (and any additional ones you judge "
        "worth automating), recommend exactly one tool (Cypress, Playwright, Selenium, Postman, "
        "Rest Assured, or Karate) best suited to it, an automation priority (High/Medium/Low), and a "
        "short rationale. Prefer Postman/Rest Assured/Karate for API test cases, Cypress/Playwright/"
        "Selenium for UI/E2E test cases."
    )


def test_data_requirements_prompt(requirement_text: str, test_cases_json: str) -> str:
    return (
        "STEP 10 — Test Data Requirements.\n"
        f"Requirement:\n\"\"\"\n{requirement_text}\n\"\"\"\n"
        f"Test cases needing data:\n{test_cases_json}\n\n"
        "Enumerate the distinct test data fields/entities required to execute the test suite "
        "(e.g. valid driver's license image, expired ID, mismatched name, duplicate SSN, locked "
        "account, etc.). For each, give a description, example values, and a likely data source "
        "(synthetic, masked production copy, stub service, etc.)."
    )


def defect_prevention_prompt(requirement_text: str, requirement_summary: str, risks_summary: str) -> str:
    return (
        "STEP 11 — Defect Prevention Analysis.\n"
        f"Requirement:\n\"\"\"\n{requirement_text}\n\"\"\"\n"
        f"Summary: {requirement_summary}\nRisks: {risks_summary}\n\n"
        "Think like a Production Support Engineer reviewing this BEFORE release. Identify potential "
        "bugs, edge cases, and production failure modes that are easy to miss, and a concrete "
        "prevention recommendation for each (code review focus, monitoring/alerting, feature flag, "
        "input validation, contract test, chaos test, etc.)."
    )


def production_validation_prompt(requirement_text: str, requirement_summary: str) -> str:
    return (
        "STEP 12 — Production Validation Checklist.\n"
        f"Requirement:\n\"\"\"\n{requirement_text}\n\"\"\"\n"
        f"Summary: {requirement_summary}\n\n"
        "Produce a post-deployment production validation / smoke-test checklist: the minimal set of "
        "real-environment checks needed to confirm this feature is healthy right after release "
        "(synthetic transactions, monitoring dashboards to watch, feature flag state, rollback "
        "triggers, etc.)."
    )


def executive_summary_prompt(
    requirement_summary: str,
    feature_category: str,
    impact_summary: str,
    risks_summary: str,
    scenario_count: int,
    test_case_count: int,
    gap_count: int,
) -> str:
    return (
        "Write a crisp Executive Summary (4-8 sentences, plain prose, no bullet points, no JSON) for "
        "engineering leadership and the Product Owner. Cover: what the requirement is, how it was "
        "classified, which existing modules are impacted, the top risks, and the overall test "
        f"coverage produced ({scenario_count} scenarios, {test_case_count} test cases, {gap_count} "
        "open requirement gaps). Be direct and decision-oriented — call out anything that should "
        "block release.\n\n"
        f"Requirement summary: {requirement_summary}\n"
        f"Feature classification: {feature_category}\n"
        f"Impact summary: {impact_summary}\n"
        f"Risk summary: {risks_summary}\n"
    )
