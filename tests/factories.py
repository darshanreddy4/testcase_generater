"""Shared test fixtures for building a representative QADeliverable without
calling any LLM."""
from __future__ import annotations

from app.models.schemas import (
    AutomationPriority,
    AutomationRecommendation,
    AutomationTool,
    CaseType,
    FeatureCategory,
    FeatureClassification,
    GapAnalysis,
    GapItem,
    ImpactAnalysis,
    ImpactedModule,
    Priority,
    ProductOwnerQuestion,
    QADeliverable,
    RequirementUnderstanding,
    Risk,
    RiskCategory,
    RiskLevel,
    Severity,
    TestCase,
    TestCoverageCategory,
    TestScenario,
    TestStrategy,
    TraceabilityLink,
)


def build_sample_deliverable() -> QADeliverable:
    return QADeliverable(
        title="Driver's License Upload & Identity Verification",
        source_type="Text",
        executive_summary="This feature lets users upload a driver's license for identity verification.",
        requirement_understanding=RequirementUnderstanding(
            business_goal="Reduce fraud during onboarding.",
            user_goal="Verify identity quickly.",
            functional_requirements=["Upload a driver's license image", "Run OCR + liveness check"],
            non_functional_requirements=["Response within 5 seconds"],
            dependencies=["Third-party KYC vendor"],
            integrations=["KYC provider API"],
            constraints=["Max file size 10MB"],
            assumptions=["Users have a valid physical license"],
            summary="Users upload a driver's license to complete identity verification.",
        ),
        feature_classification=FeatureClassification(category=FeatureCategory.NEW_FEATURE, rationale="New KYC flow."),
        impact_analysis=ImpactAnalysis(
            modules=[
                ImpactedModule(
                    module="KYC",
                    impacted=True,
                    impact_description="New document upload path.",
                    related_existing_test_cases=["TC-EXIST-004"],
                    related_existing_defects=["DEF-1001"],
                ),
                ImpactedModule(module="Payments", impacted=False),
            ],
            summary="Primarily impacts the KYC module.",
        ),
        gap_analysis=GapAnalysis(
            items=[
                GapItem(
                    category="Missing Error Handling",
                    description="No defined behavior for expired licenses.",
                    question_for_product_owner="What should happen if the license is expired?",
                )
            ]
        ),
        assumptions=["Users have a valid physical license"],
        risks=[Risk(category=RiskCategory.BUSINESS, level=RiskLevel.HIGH, description="Verification failure blocks onboarding.")],
        test_strategy=TestStrategy(
            scope="KYC document upload flow",
            approach="Risk-based testing with boundary and security focus.",
            test_levels=["System", "Regression"],
            test_design_techniques_applied=["Boundary Value Analysis", "Error Guessing"],
            entry_criteria=["Feature deployed to QA"],
            exit_criteria=["No P1/P2 defects open"],
            environments=["QA", "Staging"],
            tools=["Playwright", "Postman"],
        ),
        test_scenarios=[
            TestScenario(
                scenario_id="SC-001",
                title="Upload valid driver's license",
                category=TestCoverageCategory.FUNCTIONAL,
                priority=Priority.P1_CRITICAL,
                requirement_ref="Upload a driver's license image",
            )
        ],
        test_cases=[
            TestCase(
                test_case_id="TC-001",
                title="Upload valid JPG license under 10MB",
                scenario_ref="SC-001",
                case_type=CaseType.POSITIVE,
                coverage_category=TestCoverageCategory.FUNCTIONAL,
                preconditions=["User is logged in"],
                priority=Priority.P1_CRITICAL,
                severity=Severity.CRITICAL,
                module="KYC",
                requirement_ref="Upload a driver's license image",
                test_data="license_valid.jpg (2MB)",
                steps=["Navigate to KYC upload screen", "Select valid license image", "Submit"],
                expected_results="Upload succeeds and verification starts.",
                automation_candidate=True,
                tags=["kyc", "upload"],
            ),
            TestCase(
                test_case_id="TC-002",
                title="Reject file over 10MB",
                scenario_ref="SC-001",
                case_type=CaseType.NEGATIVE,
                coverage_category=TestCoverageCategory.FUNCTIONAL,
                priority=Priority.P2_HIGH,
                severity=Severity.MAJOR,
                module="KYC",
                steps=["Attempt to upload 15MB file"],
                expected_results="System rejects file with a clear error.",
                automation_candidate=True,
                tags=["kyc", "negative"],
            ),
        ],
        regression_coverage=["TC-EXIST-004"],
        automation_recommendations=[
            AutomationRecommendation(test_case_ref="TC-001", tool=AutomationTool.PLAYWRIGHT, priority=AutomationPriority.HIGH, rationale="Core E2E path.")
        ],
        questions_for_product_owner=[ProductOwnerQuestion(question="What should happen if the license is expired?", context="Missing error handling.")],
        traceability_matrix=[
            TraceabilityLink(requirement_ref="Upload a driver's license image", scenario_ref="SC-001", test_case_ref="TC-001", automation_script_ref="Playwright:TC-001")
        ],
    )
