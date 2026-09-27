"""Runs the full multi-stage QA analysis & test design pipeline end-to-end,
turning a raw requirement (+ optional existing-artifact context) into a
complete `QADeliverable`.

Two enterprise-grade behaviors on top of the basic linear pipeline:

- **Resumable**: every stage's result is checkpointed to disk keyed by a
  content-derived `run_id`. If a run is interrupted (network drop, crash,
  Ctrl-C), re-running the same requirement picks up from the last completed
  stage instead of re-calling the LLM for everything.
- **Parallel waves**: stages that don't depend on each other's output run
  concurrently, cutting wall-clock time and reducing exposure to any single
  dropped call.

Dependency graph:
    requirement_understanding
        -> [feature_classification, impact_analysis, gap_analysis]  (parallel)
        -> [risk_analysis -> test_strategy]  and  [test_scenarios]  (parallel)
        -> test_cases (needs test_scenarios)
        -> net-new dedup against existing test cases
        -> [automation, test_data, defect_prevention, production_validation]  (parallel)
        -> executive_summary -> traceability matrix
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, Optional, Type, TypeVar

from pydantic import BaseModel

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
from app.pipeline.checkpoint import CheckpointStore, make_run_id
from app.pipeline.context import RequirementInput
from app.pipeline.dedup import filter_net_new_test_cases
from app.prompts import stage_prompts as sp
from app.prompts.system_prompt import SYSTEM_PROMPT

StageCallback = Optional[Callable[[str], None]]
T = TypeVar("T", bound=BaseModel)


def _run_parallel(tasks: Dict[str, Callable[[], object]]) -> Dict[str, object]:
    """Runs independent stage callables concurrently and returns their results by name."""
    results: Dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=max(len(tasks), 1)) as executor:
        future_map = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(future_map):
            name = future_map[future]
            results[name] = future.result()
    return results


class _StageRunner:
    """Wraps LLM stage calls with checkpoint-aware caching and progress notifications."""

    def __init__(self, checkpoint: CheckpointStore, on_stage: StageCallback) -> None:
        self.checkpoint = checkpoint
        self.on_stage = on_stage
        self._lock = threading.Lock()

    def notify(self, message: str) -> None:
        if self.on_stage:
            with self._lock:
                self.on_stage(message)

    def run(self, name: str, label: str, schema: Type[T], compute_fn: Callable[[], T]) -> T:
        cached = self.checkpoint.load(name, schema)
        if cached is not None:
            self.notify(f"[resumed] {label}")
            return cached
        self.notify(label)
        result = compute_fn()
        self.checkpoint.save(name, result)
        return result

    def run_text(self, name: str, label: str, compute_fn: Callable[[], str]) -> str:
        cached = self.checkpoint.load_text(name)
        if cached is not None:
            self.notify(f"[resumed] {label}")
            return cached
        self.notify(label)
        result = compute_fn()
        self.checkpoint.save_text(name, result)
        return result


def run_pipeline(
    requirement: RequirementInput,
    on_stage: StageCallback = None,
    run_id: Optional[str] = None,
    fresh: bool = False,
) -> QADeliverable:
    resolved_run_id = run_id or make_run_id(requirement.text, requirement.source_type)
    checkpoint = CheckpointStore(resolved_run_id)
    if fresh:
        checkpoint.clear()

    stage = _StageRunner(checkpoint, on_stage)
    stage.notify(f"Run ID: {resolved_run_id} (checkpoints: {checkpoint.dir})")

    existing_test_cases = load_existing_test_cases()
    existing_defects = load_existing_defects()

    requirement_understanding = stage.run(
        "requirement_understanding",
        "Analyzing requirement understanding...",
        RequirementUnderstanding,
        lambda: llm_client.generate_structured(
            SYSTEM_PROMPT,
            sp.requirement_understanding_prompt(requirement.text, requirement.source_type),
            RequirementUnderstanding,
        ),
    )

    stage.notify("Running feature classification, impact analysis & gap analysis in parallel...")
    wave1 = _run_parallel(
        {
            "feature_classification": lambda: stage.run(
                "feature_classification",
                "Classifying feature type...",
                FeatureClassification,
                lambda: llm_client.generate_structured(
                    SYSTEM_PROMPT,
                    sp.feature_classification_prompt(requirement.text, requirement_understanding.summary),
                    FeatureClassification,
                ),
            ),
            "impact_analysis": lambda: stage.run(
                "impact_analysis",
                "Running existing-feature impact analysis...",
                ImpactAnalysis,
                lambda: llm_client.generate_structured(
                    SYSTEM_PROMPT,
                    sp.impact_analysis_prompt(
                        requirement.text, requirement_understanding.summary, existing_test_cases, existing_defects
                    ),
                    ImpactAnalysis,
                ),
            ),
            "gap_analysis": lambda: stage.run(
                "gap_analysis",
                "Identifying requirement gaps...",
                GapAnalysis,
                lambda: llm_client.generate_structured(
                    SYSTEM_PROMPT,
                    sp.gap_analysis_prompt(requirement.text, requirement_understanding.summary),
                    GapAnalysis,
                ),
            ),
        }
    )
    feature_classification: FeatureClassification = wave1["feature_classification"]
    impact_analysis: ImpactAnalysis = wave1["impact_analysis"]
    gap_analysis: GapAnalysis = wave1["gap_analysis"]

    def _risk_and_strategy():
        risks_wrapper = stage.run(
            "risks",
            "Performing risk analysis...",
            RisksWrapper,
            lambda: llm_client.generate_structured(
                SYSTEM_PROMPT,
                sp.risk_analysis_prompt(
                    requirement.text, requirement_understanding.summary, feature_classification.category.value
                ),
                RisksWrapper,
            ),
        )
        risks_summary = "; ".join(f"[{r.level.value}] {r.description}" for r in risks_wrapper.risks[:8])
        test_strategy = stage.run(
            "test_strategy",
            "Defining test strategy...",
            TestStrategy,
            lambda: llm_client.generate_structured(
                SYSTEM_PROMPT,
                sp.test_strategy_prompt(
                    requirement.text,
                    requirement_understanding.summary,
                    feature_classification.category.value,
                    risks_summary,
                ),
                TestStrategy,
            ),
        )
        return risks_wrapper, risks_summary, test_strategy

    def _scenarios():
        return stage.run(
            "test_scenarios",
            "Generating test scenarios...",
            TestScenariosWrapper,
            lambda: llm_client.generate_structured(
                SYSTEM_PROMPT,
                sp.test_scenarios_prompt(requirement.text, requirement_understanding.summary, impact_analysis.summary),
                TestScenariosWrapper,
            ),
        )

    wave2 = _run_parallel({"risk_strategy": _risk_and_strategy, "scenarios": _scenarios})
    risks_wrapper, risks_summary, test_strategy = wave2["risk_strategy"]
    scenarios_wrapper: TestScenariosWrapper = wave2["scenarios"]

    impacted_modules = [m.module for m in impact_analysis.modules if m.impacted]
    module_hint = impacted_modules[0] if impacted_modules else "General"
    existing_titles_for_module = [
        tc["title"] for tc in existing_test_cases if tc.get("module") == module_hint and tc.get("title")
    ] or [tc["title"] for tc in existing_test_cases if tc.get("title")]
    scenarios_json = json.dumps([s.model_dump(mode="json") for s in scenarios_wrapper.scenarios], indent=2)

    test_cases_wrapper = stage.run(
        "test_cases",
        "Generating detailed test cases...",
        TestCasesWrapper,
        lambda: llm_client.generate_structured(
            SYSTEM_PROMPT,
            sp.test_cases_prompt(
                requirement.text, requirement_understanding.summary, scenarios_json, module_hint, existing_titles_for_module
            ),
            TestCasesWrapper,
        ),
    )

    net_new_test_cases, skipped_duplicates = filter_net_new_test_cases(
        test_cases_wrapper.test_cases, existing_test_cases
    )
    if skipped_duplicates:
        stage.notify(f"Skipped {len(skipped_duplicates)} duplicate test case(s) already covered by existing suite.")

    test_cases_json = json.dumps([tc.model_dump(mode="json") for tc in net_new_test_cases], indent=2)

    stage.notify("Running automation, test data, defect prevention & production checklist analysis in parallel...")
    wave4 = _run_parallel(
        {
            "automation": lambda: stage.run(
                "automation",
                "Analyzing automation candidates...",
                AutomationRecommendationsWrapper,
                lambda: llm_client.generate_structured(
                    SYSTEM_PROMPT, sp.automation_recommendations_prompt(test_cases_json), AutomationRecommendationsWrapper
                ),
            ),
            "test_data": lambda: stage.run(
                "test_data",
                "Defining test data requirements...",
                TestDataRequirementsWrapper,
                lambda: llm_client.generate_structured(
                    SYSTEM_PROMPT,
                    sp.test_data_requirements_prompt(requirement.text, test_cases_json),
                    TestDataRequirementsWrapper,
                ),
            ),
            "defect_prevention": lambda: stage.run(
                "defect_prevention",
                "Running defect prevention analysis...",
                DefectPreventionWrapper,
                lambda: llm_client.generate_structured(
                    SYSTEM_PROMPT,
                    sp.defect_prevention_prompt(requirement.text, requirement_understanding.summary, risks_summary),
                    DefectPreventionWrapper,
                ),
            ),
            "production_validation": lambda: stage.run(
                "production_validation",
                "Building production validation checklist...",
                ProductionValidationWrapper,
                lambda: llm_client.generate_structured(
                    SYSTEM_PROMPT,
                    sp.production_validation_prompt(requirement.text, requirement_understanding.summary),
                    ProductionValidationWrapper,
                ),
            ),
        }
    )
    automation_wrapper: AutomationRecommendationsWrapper = wave4["automation"]
    test_data_wrapper: TestDataRequirementsWrapper = wave4["test_data"]
    defect_prevention_wrapper: DefectPreventionWrapper = wave4["defect_prevention"]
    production_validation_wrapper: ProductionValidationWrapper = wave4["production_validation"]

    gap_questions = [
        ProductOwnerQuestion(question=item.question_for_product_owner, context=item.description)
        for item in gap_analysis.items
        if item.question_for_product_owner
    ]

    executive_summary = stage.run_text(
        "executive_summary",
        "Writing executive summary...",
        lambda: llm_client.generate_text(
            SYSTEM_PROMPT,
            sp.executive_summary_prompt(
                requirement_understanding.summary,
                feature_classification.category.value,
                impact_analysis.summary,
                risks_summary,
                len(scenarios_wrapper.scenarios),
                len(net_new_test_cases),
                len(gap_analysis.items),
            ),
        ),
    )

    stage.notify("Assembling traceability matrix and final report...")
    regression_coverage = sorted(
        {tc_id for m in impact_analysis.modules if m.impacted for tc_id in m.related_existing_test_cases}
    )

    automation_by_case = {rec.test_case_ref: rec for rec in automation_wrapper.recommendations}
    traceability_matrix = []
    for tc in net_new_test_cases:
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
        test_cases=net_new_test_cases,
        regression_coverage=regression_coverage,
        automation_recommendations=automation_wrapper.recommendations,
        test_data_requirements=test_data_wrapper.requirements,
        production_validation_checklist=production_validation_wrapper.items,
        defect_prevention_suggestions=defect_prevention_wrapper.items,
        questions_for_product_owner=gap_questions,
        traceability_matrix=traceability_matrix,
        duplicate_test_cases_skipped=skipped_duplicates,
    )
