from app.services.github.parser import extract_issue_references


def test_extracts_closing_and_mention_references_with_provenance():
    result = extract_issue_references(
        "Fixes #123, closed #456, resolves #789. See #10 and owner/other#44."
    )
    assert [(item.number, item.reference_type) for item in result] == [
        (123, "fixes"),
        (456, "closes"),
        (789, "resolves"),
        (10, "mentions"),
        (44, "mentions"),
    ]
    assert result[-1].owner == "owner"
    assert result[-1].repository == "other"
    assert result[0].confidence > result[3].confidence


def test_simple_reference_never_becomes_a_closing_claim():
    [reference] = extract_issue_references("See #10")
    assert reference.reference_type == "mentions"
    assert reference.raw_reference == "See #10"


def test_reference_extraction_is_empty_safe_and_deduplicated():
    assert extract_issue_references(None) == []
    assert len(extract_issue_references("Fix #3 and fix #3")) == 1
