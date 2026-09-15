import re

from app.parsers.base import TreeSitterParser
from app.parsers.models import ParsedImport


class PhpParser(TreeSitterParser):
    language = "PHP"
    grammar = "php"
    symbol_nodes = {
        "function_definition": "function",
        "class_declaration": "class",
        "method_declaration": "function",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "trait_declaration": "trait",
    }

    def _imports(self, source: str) -> list[ParsedImport]:
        return [
            ParsedImport(value.strip("\\"), import_type="use")
            for value in re.findall(r"(?m)^\s*use\s+([^;]+);", source)
        ]
