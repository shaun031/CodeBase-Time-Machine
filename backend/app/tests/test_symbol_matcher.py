from uuid import UUID, uuid4

from app.parsers.models import ParsedSymbol
from app.services.symbol_matcher import HistoricalSymbol, SymbolMatcher, digest, normalized_text


def historical_symbol(
    name: str,
    source: str,
    *,
    path: str = "calculator.py",
    file_lineage_id: UUID | None = None,
    qualified_name: str | None = None,
    signature: str | None = None,
    documentation: str | None = None,
    kind: str = "function",
) -> HistoricalSymbol:
    return HistoricalSymbol(
        symbol=ParsedSymbol(
            name=name,
            qualified_name=qualified_name or name,
            kind=kind,
            signature=signature or f"def {name}(values)",
            start_line=1,
            end_line=max(1, len(source.splitlines())),
            start_column=1,
            end_column=1,
            documentation=documentation,
        ),
        source=source,
        file_path=path,
        file_lineage_id=file_lineage_id or uuid4(),
    )


def test_hashing_is_stable_and_whitespace_normalized():
    assert normalized_text(" A  B\n") == "ab"
    assert digest("café") == digest("café")
    assert digest("café") != digest("cafe")


def test_exact_and_same_name_modified_matching():
    lineage = uuid4()
    before = historical_symbol(
        "total", "def total(values):\n    return sum(values)\n", file_lineage_id=lineage
    )
    exact = historical_symbol(
        "total", "def total(values):\n    return sum(values)\n", file_lineage_id=lineage
    )
    changed = historical_symbol(
        "total", "def total(values):\n    return round(sum(values), 2)\n", file_lineage_id=lineage
    )
    exact_result = SymbolMatcher().match([before], [exact])
    changed_result = SymbolMatcher().match([before], [changed])
    assert exact_result.matches[0].match_type == "exact"
    assert exact_result.matches[0].confidence == 1
    assert changed_result.matches[0].match_type == "exact"


def test_symbol_rename_and_file_move_have_confidence_evidence():
    old_file = uuid4()
    renamed = SymbolMatcher().match(
        [
            historical_symbol(
                "calculate_total",
                "def calculate_total(values):\n    return sum(values)\n",
                file_lineage_id=old_file,
            )
        ],
        [
            historical_symbol(
                "total",
                "def total(values):\n    return sum(values)\n",
                file_lineage_id=old_file,
            )
        ],
    )
    moved = SymbolMatcher().match(
        [
            historical_symbol(
                "total",
                "def total(values):\n    return sum(values)\n",
                file_lineage_id=old_file,
            )
        ],
        [
            historical_symbol(
                "total",
                "def total(values):\n    return sum(values)\n",
                path="domain/math.py",
                file_lineage_id=uuid4(),
            )
        ],
    )
    assert renamed.matches[0].match_type == "symbol_rename"
    assert renamed.matches[0].confidence >= 0.9
    assert renamed.matches[0].evidence["name_changed"] is True
    assert moved.matches[0].match_type == "symbol_move"
    assert moved.matches[0].confidence >= 0.9


def test_documentation_is_excluded_from_normalized_body_hash():
    lineage = uuid4()
    before = historical_symbol(
        "total",
        'def total(values):\n    """Old docs."""\n    return sum(values)\n',
        documentation="Old docs.",
        file_lineage_id=lineage,
    )
    after = historical_symbol(
        "total",
        'def total(values):\n    """Clearer docs."""\n    return sum(values)\n',
        documentation="Clearer docs.",
        file_lineage_id=lineage,
    )
    assert before.normalized_body_hash == after.normalized_body_hash
    assert before.body_hash != after.body_hash


def test_ambiguous_candidates_are_rejected_instead_of_forced():
    lineage = uuid4()
    source = "def load(value):\n    return value\n"
    previous = [
        historical_symbol("load", source, file_lineage_id=lineage),
        historical_symbol("load", source, file_lineage_id=lineage),
    ]
    current = [historical_symbol("load", source, file_lineage_id=lineage)]
    result = SymbolMatcher().match(previous, current)
    assert result.matches == []
    assert result.unmatched_previous == [0, 1]
    assert result.unmatched_current == [0]


def test_different_symbol_kinds_do_not_match():
    lineage = uuid4()
    before = historical_symbol(
        "Thing", "class Thing:\n    pass\n", file_lineage_id=lineage, kind="class"
    )
    after = historical_symbol(
        "Thing",
        "def Thing():\n    pass\n",
        file_lineage_id=lineage,
        kind="method",
    )
    assert SymbolMatcher().match([before], [after]).matches == []


def test_function_moved_into_class_matches_as_a_method():
    lineage = uuid4()
    before = historical_symbol(
        "total",
        "def total(values):\n    return sum(values)\n",
        file_lineage_id=lineage,
    )
    after = historical_symbol(
        "total",
        "    def total(self, values):\n        return sum(values)\n",
        file_lineage_id=lineage,
        qualified_name="Calculator.total",
        signature="def total(self, values)",
        kind="method",
    )
    result = SymbolMatcher().match([before], [after])
    assert result.matches[0].match_type == "same_name_modified"
    assert result.matches[0].confidence >= 0.86
