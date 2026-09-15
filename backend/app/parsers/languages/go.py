import re

from app.parsers.base import TreeSitterParser
from app.parsers.models import ParsedImport


class GoParser(TreeSitterParser):
    language = "Go"
    grammar = "go"
    symbol_nodes = {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_spec": "struct",
    }

    def _imports(self, source: str) -> list[ParsedImport]:
        return [
            ParsedImport(value, import_type="import")
            for value in re.findall(
                r"['\"]([^'\"]+)['\"]",
                "\n".join(
                    line
                    for line in source.splitlines()
                    if "import" in line or line.lstrip().startswith(('"', "'"))
                ),
            )
        ]
