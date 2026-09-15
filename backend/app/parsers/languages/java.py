import re

from app.parsers.base import TreeSitterParser
from app.parsers.models import ParsedImport


class JavaParser(TreeSitterParser):
    language = "Java"
    grammar = "java"
    symbol_nodes = {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "method_declaration": "function",
        "constructor_declaration": "constructor",
    }

    def _imports(self, source: str) -> list[ParsedImport]:
        return [
            ParsedImport(value, import_type="import")
            for value in re.findall(r"(?m)^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", source)
        ]
