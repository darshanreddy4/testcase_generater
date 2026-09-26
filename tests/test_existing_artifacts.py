from app.knowledge.existing_artifacts import load_existing_defects, load_existing_test_cases


def test_load_existing_test_cases_reads_sample_csv():
    rows = load_existing_test_cases()
    assert rows, "Expected sample existing test cases to load"
    assert any(r["test_case_id"] == "TC-EXIST-004" for r in rows)


def test_load_existing_defects_reads_sample_csv():
    rows = load_existing_defects()
    assert rows, "Expected sample defects to load"
    assert any(r["defect_id"] == "DEF-1001" for r in rows)
