import re

from app.parsers.base import TreeSitterParser
from app.parsers.models import ParsedImport


class CParser(TreeSitterParser):
    language = "C"
    grammar = "c"
    symbol_nodes = {
        "function_definition": "function",
        "struct_specifier": "struct",
        "enum_specifier": "enum",
    }

    def _imports(self, source: str) -> list[ParsedImport]:
        return [
            ParsedImport(value, import_type="include")
            for value in re.findall(r"(?m)^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]", source)
        ]
