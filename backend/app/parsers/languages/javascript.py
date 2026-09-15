import re

from tree_sitter import Node

from app.parsers.base import TreeSitterParser
from app.parsers.models import ParsedImport


class JavaScriptParser(TreeSitterParser):
    language = "JavaScript"
    grammar = "javascript"
    symbol_nodes = {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "function",
        "variable_declarator": "function",
    }

    def _symbol_kind(self, node: Node, configured_kind: str) -> str | None:
        if node.type == "variable_declarator":
            value = node.child_by_field_name("value")
            if value is None or value.type not in {"arrow_function", "function_expression"}:
                return None
        return configured_kind

    def _imports(self, source: str) -> list[ParsedImport]:
        result: list[ParsedImport] = []
        pattern = r"(?m)^\s*import\s+(?:(.*?)\s+from\s+)?['\"]([^'\"]+)['\"]"
        for match in re.finditer(pattern, source):
            names, module = match.groups()
            result.append(
                ParsedImport(module, names.strip() if names else None, import_type="import")
            )
        for match in re.finditer(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)", source):
            result.append(ParsedImport(match.group(1), import_type="require"))
        return result
