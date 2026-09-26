from app.models.schemas import CaseType
from tests.factories import build_sample_deliverable


def test_test_cases_by_type_filters_correctly():
    deliverable = build_sample_deliverable()
    positives = deliverable.test_cases_by_type(CaseType.POSITIVE)
    negatives = deliverable.test_cases_by_type(CaseType.NEGATIVE)

    assert [tc.test_case_id for tc in positives] == ["TC-001"]
    assert [tc.test_case_id for tc in negatives] == ["TC-002"]


def test_deliverable_round_trips_through_json():
    deliverable = build_sample_deliverable()
    dumped = deliverable.model_dump_json()
    restored = deliverable.model_validate_json(dumped)
    assert restored.title == deliverable.title
    assert len(restored.test_cases) == len(deliverable.test_cases)
