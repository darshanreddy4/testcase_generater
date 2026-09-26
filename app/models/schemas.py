"""Pydantic data models for every deliverable the QA Agent produces.

These schemas are the contract between the LLM (structured JSON output),
the pipeline orchestrator, and the exporters (Markdown / Excel / traceability).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class FeatureCategory(str, Enum):
    NEW_FEATURE = "New Feature"
    ENHANCEMENT = "Existing Feature Enhancement"
    BUG_FIX = "Bug Fix"
    CONFIG_CHANGE = "Configuration Change"
    UI_CHANGE = "UI Change"
    API_CHANGE = "API Change"
    WORKFLOW_CHANGE = "Workflow Change"
    MIGRATION = "Migration"


class RiskCategory(str, Enum):
    BUSINESS = "Business Risk"
    TECHNICAL = "Technical Risk"
    SECURITY = "Security Risk"
    PRODUCTION = "Production Risk"


class RiskLevel(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Priority(str, Enum):
    P1_CRITICAL = "P1-Critical"
    P2_HIGH = "P2-High"
    P3_MEDIUM = "P3-Medium"
    P4_LOW = "P4-Low"


class Severity(str, Enum):
    BLOCKER = "Blocker"
    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"
    TRIVIAL = "Trivial"


class TestCoverageCategory(str, Enum):
    FUNCTIONAL = "Functional"
    UI = "UI"
    API = "API"
    DATABASE = "Database"
    SECURITY = "Security"
    ACCESSIBILITY = "Accessibility"
    PERFORMANCE = "Performance"
    REGRESSION = "Regression"
    INTEGRATION = "Integration"


class CaseType(str, Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    ALTERNATE_FLOW = "Alternate Flow"
    BOUNDARY = "Boundary"
    EDGE_CASE = "Edge Case"
    SECURITY = "Security"
    ACCESSIBILITY = "Accessibility"
    PERFORMANCE = "Performance"
    REGRESSION = "Regression"
    INTEGRATION = "Integration"


class AutomationTool(str, Enum):
    CYPRESS = "Cypress"
    PLAYWRIGHT = "Playwright"
    SELENIUM = "Selenium"
    POSTMAN = "Postman"
    REST_ASSURED = "Rest Assured"
    KARATE = "Karate"
    NONE = "Not Applicable"


class AutomationPriority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


# ---------------------------------------------------------------------------
# Step 1: Requirement Understanding
# ---------------------------------------------------------------------------
class RequirementUnderstanding(BaseModel):
    business_goal: str = ""
    user_goal: str = ""
    functional_requirements: List[str] = Field(default_factory=list)
    non_functional_requirements: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    integrations: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Step 2: Feature Classification
# ---------------------------------------------------------------------------
class FeatureClassification(BaseModel):
    category: FeatureCategory
    rationale: str = ""


# ---------------------------------------------------------------------------
# Step 3: Existing Feature Impact Analysis
# ---------------------------------------------------------------------------
class ImpactedModule(BaseModel):
    module: str
    impacted: bool
    impact_description: str = ""
    related_existing_test_cases: List[str] = Field(default_factory=list)
    related_existing_defects: List[str] = Field(default_factory=list)


class ImpactAnalysis(BaseModel):
    modules: List[ImpactedModule] = Field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Step 4: Requirement Gap Analysis
# ---------------------------------------------------------------------------
class GapItem(BaseModel):
    category: str  # e.g. Missing Acceptance Criteria, Ambiguous Behavior, ...
    description: str
    question_for_product_owner: Optional[str] = None


class GapAnalysis(BaseModel):
    items: List[GapItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------
class Risk(BaseModel):
    category: RiskCategory
    level: RiskLevel
    description: str


# ---------------------------------------------------------------------------
# Test Strategy / Plan
# ---------------------------------------------------------------------------
class TestStrategy(BaseModel):
    scope: str = ""
    approach: str = ""
    test_levels: List[str] = Field(default_factory=list)
    test_design_techniques_applied: List[str] = Field(default_factory=list)
    entry_criteria: List[str] = Field(default_factory=list)
    exit_criteria: List[str] = Field(default_factory=list)
    environments: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Test Scenarios
# ---------------------------------------------------------------------------
class TestScenario(BaseModel):
    scenario_id: str
    title: str
    category: TestCoverageCategory
    description: str = ""
    priority: Priority = Priority.P3_MEDIUM
    requirement_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------
class TestCase(BaseModel):
    test_case_id: str
    title: str
    scenario_ref: Optional[str] = None
    case_type: CaseType = CaseType.POSITIVE
    coverage_category: TestCoverageCategory = TestCoverageCategory.FUNCTIONAL
    preconditions: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    priority: Priority = Priority.P3_MEDIUM
    severity: Severity = Severity.MAJOR
    module: str = ""
    requirement_ref: Optional[str] = None
    test_data: str = ""
    steps: List[str] = Field(default_factory=list)
    expected_results: str = ""
    automation_candidate: bool = False
    tags: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Automation Recommendations
# ---------------------------------------------------------------------------
class AutomationRecommendation(BaseModel):
    test_case_ref: str
    tool: AutomationTool
    priority: AutomationPriority
    rationale: str = ""


# ---------------------------------------------------------------------------
# Test Data Requirements
# ---------------------------------------------------------------------------
class TestDataRequirement(BaseModel):
    field: str
    description: str
    example_values: List[str] = Field(default_factory=list)
    source: str = ""


# ---------------------------------------------------------------------------
# Defect Prevention
# ---------------------------------------------------------------------------
class DefectPreventionItem(BaseModel):
    area: str
    potential_bug_or_edge_case: str
    prevention_recommendation: str


# ---------------------------------------------------------------------------
# Traceability
# ---------------------------------------------------------------------------
class TraceabilityLink(BaseModel):
    requirement_ref: str
    scenario_ref: Optional[str] = None
    test_case_ref: Optional[str] = None
    automation_script_ref: Optional[str] = None
    defect_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Questions for Product Owner
# ---------------------------------------------------------------------------
class ProductOwnerQuestion(BaseModel):
    question: str
    context: str = ""


# ---------------------------------------------------------------------------
# Production Validation Checklist
# ---------------------------------------------------------------------------
class ProductionValidationItem(BaseModel):
    check: str
    category: str = ""


# ---------------------------------------------------------------------------
# Top level container returned by the pipeline
# ---------------------------------------------------------------------------
class QADeliverable(BaseModel):
    title: str
    source_type: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    executive_summary: str = ""
    requirement_understanding: RequirementUnderstanding = Field(default_factory=RequirementUnderstanding)
    feature_classification: FeatureClassification = Field(
        default_factory=lambda: FeatureClassification(category=FeatureCategory.NEW_FEATURE)
    )
    impact_analysis: ImpactAnalysis = Field(default_factory=ImpactAnalysis)
    gap_analysis: GapAnalysis = Field(default_factory=GapAnalysis)
    assumptions: List[str] = Field(default_factory=list)
    risks: List[Risk] = Field(default_factory=list)
    test_strategy: TestStrategy = Field(default_factory=TestStrategy)
    test_scenarios: List[TestScenario] = Field(default_factory=list)
    test_cases: List[TestCase] = Field(default_factory=list)
    regression_coverage: List[str] = Field(default_factory=list)
    automation_recommendations: List[AutomationRecommendation] = Field(default_factory=list)
    test_data_requirements: List[TestDataRequirement] = Field(default_factory=list)
    production_validation_checklist: List[ProductionValidationItem] = Field(default_factory=list)
    defect_prevention_suggestions: List[DefectPreventionItem] = Field(default_factory=list)
    questions_for_product_owner: List[ProductOwnerQuestion] = Field(default_factory=list)
    traceability_matrix: List[TraceabilityLink] = Field(default_factory=list)

    def test_cases_by_type(self, case_type: CaseType) -> List[TestCase]:
        return [tc for tc in self.test_cases if tc.case_type == case_type]


# ---------------------------------------------------------------------------
# Wrapper models — used only as LLM structured-output targets for list-shaped
# stages (a bare JSON array is harder to constrain/validate reliably than an
# object with a named field).
# ---------------------------------------------------------------------------
class RisksWrapper(BaseModel):
    risks: List[Risk] = Field(default_factory=list)


class TestScenariosWrapper(BaseModel):
    scenarios: List[TestScenario] = Field(default_factory=list)


class TestCasesWrapper(BaseModel):
    test_cases: List[TestCase] = Field(default_factory=list)


class AutomationRecommendationsWrapper(BaseModel):
    recommendations: List[AutomationRecommendation] = Field(default_factory=list)


class TestDataRequirementsWrapper(BaseModel):
    requirements: List[TestDataRequirement] = Field(default_factory=list)


class DefectPreventionWrapper(BaseModel):
    items: List[DefectPreventionItem] = Field(default_factory=list)


class ProductionValidationWrapper(BaseModel):
    items: List[ProductionValidationItem] = Field(default_factory=list)


class RegressionCoverageWrapper(BaseModel):
    impacted_scenarios: List[str] = Field(default_factory=list)
