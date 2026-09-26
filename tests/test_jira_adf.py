from app.ingestion.jira_client import _adf_to_text


def test_adf_to_text_flattens_paragraphs_and_lists():
    adf = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Users upload a license."}]},
            {
                "type": "bulletList",
                "content": [
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Must support JPG"}]}]},
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Must support PNG"}]}]},
                ],
            },
        ],
    }
    text = _adf_to_text(adf)
    assert "Users upload a license." in text
    assert "Must support JPG" in text
    assert "Must support PNG" in text


def test_adf_to_text_handles_none_and_empty():
    assert _adf_to_text(None) == ""
    assert _adf_to_text({}) == ""
