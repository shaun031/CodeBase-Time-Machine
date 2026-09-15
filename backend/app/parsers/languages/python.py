import re

from app.parsers.base import TreeSitterParser
from app.parsers.models import ParsedImport


class PythonParser(TreeSitterParser):
    language = "Python"
    grammar = "python"
    symbol_nodes = {"function_definition": "function", "class_definition": "class"}

    def _imports(self, source: str) -> list[ParsedImport]:
        result: list[ParsedImport] = []
        for match in re.finditer(r"(?m)^\s*import\s+([^#\n]+)", source):
            for item in match.group(1).split(","):
                parts = re.split(r"\s+as\s+", item.strip(), maxsplit=1)
                if parts[0]:
                    result.append(
                        ParsedImport(parts[0], alias=parts[1] if len(parts) > 1 else None)
                    )
        for match in re.finditer(r"(?m)^\s*from\s+([\w.]+)\s+import\s+([^#\n]+)", source):
            module = match.group(1)
            for item in match.group(2).strip("() ").split(","):
                parts = re.split(r"\s+as\s+", item.strip(), maxsplit=1)
                if parts[0]:
                    result.append(
                        ParsedImport(module, parts[0], parts[1] if len(parts) > 1 else None, "from")
                    )
        return result
