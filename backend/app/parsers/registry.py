from app.parsers.base import LanguageParser
from app.parsers.languages import (
    CParser,
    CppParser,
    GoParser,
    JavaParser,
    JavaScriptParser,
    PhpParser,
    PythonParser,
    TsxParser,
    TypeScriptParser,
)


class ParserRegistry:
    def __init__(self) -> None:
        parsers = [
            PythonParser(),
            JavaScriptParser(),
            TypeScriptParser(),
            TsxParser(),
            JavaParser(),
            CParser(),
            CppParser(),
            GoParser(),
            PhpParser(),
        ]
        self._parsers = {parser.language: parser for parser in parsers}

    def get(self, language: str | None) -> LanguageParser | None:
        return self._parsers.get(language or "")

    @property
    def languages(self) -> frozenset[str]:
        return frozenset(self._parsers)
