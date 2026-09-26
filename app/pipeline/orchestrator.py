"""Runs the full multi-stage QA analysis & test design pipeline end-to-end,
turning a raw requirement (+ optional existing-artifact context) into a
complete `QADeliverable`.
"""
from __future__ import annotations

import json
from typing import Callable, Optional

from app.knowledge.existing_artifacts import load_existing_defects, load_existing_test_cases
from app.llm.llm_client import llm_client
from app.models.schemas import (
    AutomationRecommendationsWrapper,
    DefectPreventionWrapper,
    FeatureClassification,
    GapAnalysis,
    ImpactAnalysis,
    ProductOwnerQuestion,
    ProductionValidationWrapper,
    QADeliverable,
    RequirementUnderstanding,
    RisksWrapper,
    TestCasesWrapper,
    TestDataRequirementsWrapper,
    TestScenariosWrapper,
    TestStrategy,
    TraceabilityLink,
)
from app.pipeline.context import RequirementInput
from app.prompts import stage_prompts as sp
from app.prompts.system_prompt import SYSTEM_PROMPT

StageCallback = Optional[Callable[[str], None]]


def _notify(callback: StageCallback, message: str) -> None:
    if callback:
        callback(message)


def run_pipeline(requirement: RequirementInput, on_stage: StageCallback = None) -> QADeliverable:
    existing_test_cases = load_existing_test_cases()
    existing_defects = load_existing_defects()

    _notify(on_stage, "Analyzing requirement understanding...")
    requirement_understanding = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.requirement_understanding_prompt(requirement.text, requirement.source_type),
        RequirementUnderstanding,
    )

    _notify(on_stage, "Classifying feature type...")
    feature_classification = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.feature_classification_prompt(requirement.text, requirement_understanding.summary),
        FeatureClassification,
    )

    _notify(on_stage, "Running existing-feature impact analysis...")
    impact_analysis = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.impact_analysis_prompt(
            requirement.text, requirement_understanding.summary, existing_test_cases, existing_defects
        ),
        ImpactAnalysis,
    )

    _notify(on_stage, "Identifying requirement gaps...")
    gap_analysis = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.gap_analysis_prompt(requirement.text, requirement_understanding.summary),
        GapAnalysis,
    )

    _notify(on_stage, "Performing risk analysis...")
    risks_wrapper = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.risk_analysis_prompt(
            requirement.text, requirement_understanding.summary, feature_classification.category.value
        ),
        RisksWrapper,
    )

    _notify(on_stage, "Defining test strategy...")
    risks_summary = "; ".join(f"[{r.level.value}] {r.description}" for r in risks_wrapper.risks[:8])
    test_strategy = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.test_strategy_prompt(
            requirement.text, requirement_understanding.summary, feature_classification.category.value, risks_summary
        ),
        TestStrategy,
    )

    _notify(on_stage, "Generating test scenarios...")
    scenarios_wrapper = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.test_scenarios_prompt(requirement.text, requirement_understanding.summary, impact_analysis.summary),
        TestScenariosWrapper,
    )

    _notify(on_stage, "Generating detailed test cases...")
    impacted_modules = [m.module for m in impact_analysis.modules if m.impacted]
    module_hint = impacted_modules[0] if impacted_modules else "General"
    scenarios_json = json.dumps([s.model_dump(mode="json") for s in scenarios_wrapper.scenarios], indent=2)
    test_cases_wrapper = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.test_cases_prompt(requirement.text, requirement_understanding.summary, scenarios_json, module_hint),
        TestCasesWrapper,
    )

    _notify(on_stage, "Analyzing automation candidates...")
    test_cases_json = json.dumps([tc.model_dump(mode="json") for tc in test_cases_wrapper.test_cases], indent=2)
    automation_wrapper = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.automation_recommendations_prompt(test_cases_json),
        AutomationRecommendationsWrapper,
    )

    _notify(on_stage, "Defining test data requirements...")
    test_data_wrapper = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.test_data_requirements_prompt(requirement.text, test_cases_json),
        TestDataRequirementsWrapper,
    )

    _notify(on_stage, "Running defect prevention analysis...")
    defect_prevention_wrapper = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.defect_prevention_prompt(requirement.text, requirement_understanding.summary, risks_summary),
        DefectPreventionWrapper,
    )

    _notify(on_stage, "Building production validation checklist...")
    production_validation_wrapper = llm_client.generate_structured(
        SYSTEM_PROMPT,
        sp.production_validation_prompt(requirement.text, requirement_understanding.summary),
        ProductionValidationWrapper,
    )

    _notify(on_stage, "Writing executive summary...")
    gap_questions = [
        ProductOwnerQuestion(question=item.question_for_product_owner, context=item.description)
        for item in gap_analysis.items
        if item.question_for_product_owner
    ]
    executive_summary = llm_client.generate_text(
        SYSTEM_PROMPT,
        sp.executive_summary_prompt(
            requirement_understanding.summary,
            feature_classification.category.value,
            impact_analysis.summary,
            risks_summary,
            len(scenarios_wrapper.scenarios),
            len(test_cases_wrapper.test_cases),
            len(gap_analysis.items),
        ),
    )

    _notify(on_stage, "Assembling traceability matrix and final report...")
    regression_coverage = sorted(
        {tc_id for m in impact_analysis.modules if m.impacted for tc_id in m.related_existing_test_cases}
    )

    automation_by_case = {rec.test_case_ref: rec for rec in automation_wrapper.recommendations}
    traceability_matrix = []
    for tc in test_cases_wrapper.test_cases:
        rec = automation_by_case.get(tc.test_case_id)
        traceability_matrix.append(
            TraceabilityLink(
                requirement_ref=tc.requirement_ref or requirement_understanding.summary[:80],
                scenario_ref=tc.scenario_ref,
                test_case_ref=tc.test_case_id,
                automation_script_ref=f"{rec.tool.value}:{tc.test_case_id}" if rec else None,
                defect_ref=None,
            )
        )

    title = requirement.title or requirement_understanding.summary[:80] or "Untitled Requirement"

    return QADeliverable(
        title=title,
        source_type=requirement.source_type,
        executive_summary=executive_summary.strip(),
        requirement_understanding=requirement_understanding,
        feature_classification=feature_classification,
        impact_analysis=impact_analysis,
        gap_analysis=gap_analysis,
        assumptions=requirement_understanding.assumptions,
        risks=risks_wrapper.risks,
        test_strategy=test_strategy,
        test_scenarios=scenarios_wrapper.scenarios,
        test_cases=test_cases_wrapper.test_cases,
        regression_coverage=regression_coverage,
        automation_recommendations=automation_wrapper.recommendations,
        test_data_requirements=test_data_wrapper.requirements,
        production_validation_checklist=production_validation_wrapper.items,
        defect_prevention_suggestions=defect_prevention_wrapper.items,
        questions_for_product_owner=gap_questions,
        traceability_matrix=traceability_matrix,
    )
