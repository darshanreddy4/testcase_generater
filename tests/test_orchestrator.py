from app.models.schemas import (
    CaseType,
    FeatureCategory,
    FeatureClassification,
    Priority,
    TestCase,
    TestCasesWrapper,
    TestCoverageCategory,
    TestScenario,
    TestScenariosWrapper,
)
from app.pipeline.context import RequirementInput
from app.pipeline import orchestrator


def fake_generate_structured(system_prompt, user_prompt, schema):
    if schema is FeatureClassification:
        return FeatureClassification(category=FeatureCategory.NEW_FEATURE, rationale="Introduces a brand-new flow.")
    if schema is TestScenariosWrapper:
        return TestScenariosWrapper(
            scenarios=[
                TestScenario(
                    scenario_id="SC-001",
                    title="Upload valid license",
                    category=TestCoverageCategory.FUNCTIONAL,
                    priority=Priority.P1_CRITICAL,
                    requirement_ref="Upload a driver's license",
                )
            ]
        )
    if schema is TestCasesWrapper:
        return TestCasesWrapper(
            test_cases=[
                TestCase(
                    test_case_id="TC-001",
                    title="Upload valid license image",
                    scenario_ref="SC-001",
                    case_type=CaseType.POSITIVE,
                    module="KYC",
                    requirement_ref="Upload a driver's license",
                    steps=["Go to upload page", "Select file", "Submit"],
                    expected_results="Upload succeeds.",
                    automation_candidate=True,
                ),
                TestCase(
                    test_case_id="TC-002",
                    title="Reject oversized file",
                    scenario_ref="SC-001",
                    case_type=CaseType.NEGATIVE,
                    module="KYC",
                    steps=["Attempt upload of 20MB file"],
                    expected_results="Rejected with clear error.",
                ),
            ]
        )
    return schema()


def fake_generate_text(system_prompt, user_prompt):
    return "This is a generated executive summary."


def test_run_pipeline_wires_all_stages_together(monkeypatch):
    monkeypatch.setattr(orchestrator.llm_client, "generate_structured", fake_generate_structured)
    monkeypatch.setattr(orchestrator.llm_client, "generate_text", fake_generate_text)

    requirement = RequirementInput(text="Users should upload a driver's license.", source_type="Text")
    deliverable = orchestrator.run_pipeline(requirement)

    assert deliverable.feature_classification.category == FeatureCategory.NEW_FEATURE
    assert len(deliverable.test_scenarios) == 1
    assert len(deliverable.test_cases) == 2
    assert deliverable.executive_summary == "This is a generated executive summary."

    # Traceability matrix should have one entry per test case.
    assert len(deliverable.traceability_matrix) == 2
    tc1_link = next(link for link in deliverable.traceability_matrix if link.test_case_ref == "TC-001")
    assert tc1_link.scenario_ref == "SC-001"
