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


def test_run_pipeline_wires_all_stages_together(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator.llm_client, "generate_structured", fake_generate_structured)
    monkeypatch.setattr(orchestrator.llm_client, "generate_text", fake_generate_text)

    requirement = RequirementInput(text="Users should upload a driver's license.", source_type="Text")
    # fresh=True + a unique run_id avoids leftover checkpoints from other test runs masking
    # the mocked calls below.
    deliverable = orchestrator.run_pipeline(requirement, run_id=f"pytest-{tmp_path.name}", fresh=True)

    assert deliverable.feature_classification.category == FeatureCategory.NEW_FEATURE
    assert len(deliverable.test_scenarios) == 1
    assert len(deliverable.test_cases) == 2
    assert deliverable.executive_summary == "This is a generated executive summary."

    # Traceability matrix should have one entry per test case.
    assert len(deliverable.traceability_matrix) == 2
    tc1_link = next(link for link in deliverable.traceability_matrix if link.test_case_ref == "TC-001")
    assert tc1_link.scenario_ref == "SC-001"


def test_run_pipeline_resumes_from_checkpoint(monkeypatch, tmp_path):
    """A second run with the same run_id should reuse checkpointed stages instead of
    re-invoking the (mocked) LLM for them."""
    call_count = {"n": 0}

    def counting_generate_structured(system_prompt, user_prompt, schema):
        call_count["n"] += 1
        return fake_generate_structured(system_prompt, user_prompt, schema)

    monkeypatch.setattr(orchestrator.llm_client, "generate_structured", counting_generate_structured)
    monkeypatch.setattr(orchestrator.llm_client, "generate_text", fake_generate_text)

    requirement = RequirementInput(text="Users should upload a driver's license.", source_type="Text")
    run_id = f"pytest-resume-{tmp_path.name}"

    orchestrator.run_pipeline(requirement, run_id=run_id, fresh=True)
    first_call_count = call_count["n"]
    assert first_call_count > 0

    # Second run with the same run_id (not fresh) should hit checkpoints, not the LLM.
    orchestrator.run_pipeline(requirement, run_id=run_id, fresh=False)
    assert call_count["n"] == first_call_count


def test_select_existing_titles_prefers_jira_key_correlation():
    existing = [
        {"title": "Verify KYC document upload accepts JPG/PNG/PDF", "module": "KYC", "jira_key": "PROJ-200"},
        {"title": "Verify login with valid credentials", "module": "Login", "jira_key": "PROJ-100"},
    ]
    titles = orchestrator._select_existing_titles(existing, ["PROJ-200", "PROJ-201"], module_hint="Login")
    assert titles == ["Verify KYC document upload accepts JPG/PNG/PDF"]


def test_select_existing_titles_falls_back_to_module_when_no_jira_match():
    existing = [
        {"title": "Verify KYC document upload accepts JPG/PNG/PDF", "module": "KYC", "jira_key": "PROJ-200"},
        {"title": "Verify login with valid credentials", "module": "Login", "jira_key": "PROJ-100"},
    ]
    titles = orchestrator._select_existing_titles(existing, ["PROJ-999"], module_hint="Login")
    assert titles == ["Verify login with valid credentials"]


def test_select_existing_titles_falls_back_to_all_when_no_module_match():
    existing = [{"title": "Verify login with valid credentials", "module": "Login"}]
    titles = orchestrator._select_existing_titles(existing, [], module_hint="KYC")
    assert titles == ["Verify login with valid credentials"]
