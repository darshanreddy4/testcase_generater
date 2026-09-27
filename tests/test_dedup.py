from app.models.schemas import CaseType, TestCase
from app.pipeline.dedup import filter_net_new_test_cases


def _tc(test_case_id: str, title: str) -> TestCase:
    return TestCase(test_case_id=test_case_id, title=title, case_type=CaseType.POSITIVE)


def test_filter_net_new_test_cases_drops_near_duplicates():
    existing = [{"test_case_id": "TC-EXIST-004", "title": "Verify KYC document upload accepts JPG/PNG/PDF under 10MB", "module": "KYC"}]
    generated = [
        _tc("TC-001", "Verify KYC document upload accepts JPG, PNG or PDF files under 10MB"),  # near-duplicate
        _tc("TC-002", "Verify KYC upload rejects files larger than 10MB"),  # genuinely net-new
    ]

    kept, skipped = filter_net_new_test_cases(generated, existing, threshold=0.75)

    assert [tc.test_case_id for tc in kept] == ["TC-002"]
    assert len(skipped) == 1
    assert "TC-001" in skipped[0]
    assert "TC-EXIST-004" in skipped[0]


def test_filter_net_new_test_cases_keeps_all_when_no_existing_cases():
    generated = [_tc("TC-001", "Some new case")]
    kept, skipped = filter_net_new_test_cases(generated, [])
    assert kept == generated
    assert skipped == []


def test_filter_net_new_test_cases_keeps_dissimilar_titles():
    existing = [{"test_case_id": "TC-EXIST-001", "title": "Verify login with valid username and password"}]
    generated = [_tc("TC-001", "Verify payment is declined for an expired card")]
    kept, skipped = filter_net_new_test_cases(generated, existing)
    assert kept == generated
    assert skipped == []
