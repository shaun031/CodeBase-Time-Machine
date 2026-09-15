from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParsedSymbol:
    name: str
    qualified_name: str
    kind: str
    signature: str | None
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    parent_index: int | None = None
    visibility: str | None = None
    is_async: bool = False
    is_static: bool = False
    documentation: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ParsedImport:
    module: str
    imported_name: str | None = None
    alias: str | None = None
    import_type: str = "import"


@dataclass(frozen=True)
class ParseResult:
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    syntax_error_count: int = 0
    parse_success: bool = True
    error_message: str | None = None
