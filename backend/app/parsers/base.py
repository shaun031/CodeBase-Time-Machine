import re
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any, cast

from tree_sitter import Node, Parser
from tree_sitter_language_pack import get_language

from app.parsers.models import ParsedImport, ParsedSymbol, ParseResult


class LanguageParser(ABC):
    language: str

    @abstractmethod
    def parse(self, source: bytes, timeout_seconds: float = 2.0) -> ParseResult: ...


class TreeSitterParser(LanguageParser):
    grammar: str
    symbol_nodes: dict[str, str] = {}

    def __init__(self) -> None:
        self._language = get_language(cast(Any, self.grammar))

    @staticmethod
    def _text(source: bytes, node: Node | None) -> str:
        if node is None:
            return ""
        return source[node.start_byte : node.end_byte].decode("utf-8", "replace")

    @classmethod
    def _walk(cls, node: Node) -> Iterator[Node]:
        yield node
        for child in node.children:
            yield from cls._walk(child)

    def _name_node(self, node: Node) -> Node | None:
        direct = node.child_by_field_name("name")
        if direct is not None:
            return direct
        declarator = node.child_by_field_name("declarator")
        if declarator is not None:
            for child in self._walk(declarator):
                if child.type in {"identifier", "field_identifier", "type_identifier"}:
                    return child
        for child in node.named_children:
            if child.type in {"identifier", "name", "type_identifier"}:
                return child
        return None

    def _signature(self, source: bytes, node: Node) -> str | None:
        body = node.child_by_field_name("body")
        end = body.start_byte if body is not None else node.end_byte
        value = self._text(source, node)[: max(0, end - node.start_byte)]
        value = re.sub(r"\s+", " ", value).strip().rstrip("{:;").strip()
        return value[:1000] or None

    def _documentation(self, source: bytes, node: Node) -> str | None:
        previous = node.prev_named_sibling
        if previous is not None and previous.type in {"comment", "line_comment", "block_comment"}:
            return self._text(source, previous)[:4000]
        body = node.child_by_field_name("body")
        if self.language == "Python" and body is not None and body.named_children:
            first = body.named_children[0]
            value = (
                first.named_children[0]
                if first.type == "expression_statement" and first.named_children
                else first
            )
            if value.type == "string":
                return self._text(source, value).strip("\"'")[:4000]
        return None

    def _imports(self, source: str) -> list[ParsedImport]:
        return []

    def _symbol_kind(self, node: Node, configured_kind: str) -> str | None:
        return configured_kind

    def parse(self, source: bytes, timeout_seconds: float = 2.0) -> ParseResult:
        parser = Parser(self._language)
        started = time.monotonic()
        # tree-sitter's Python progress callback can cause a native access violation on
        # Windows for valid source files. Input size is bounded before this method runs,
        # so parse bytes directly and reject results that exceed the configured budget.
        tree = parser.parse(source)
        if time.monotonic() - started >= max(timeout_seconds, 0.000_001):
            return ParseResult(parse_success=False, error_message="Parser timed out.")
        symbols: list[ParsedSymbol] = []

        def visit(node: Node, parent_index: int | None = None) -> None:
            current_parent = parent_index
            configured_kind = self.symbol_nodes.get(node.type)
            if configured_kind:
                configured_kind = self._symbol_kind(node, configured_kind)
            if configured_kind:
                name_node = self._name_node(node)
                name = self._text(source, name_node).strip()
                if name:
                    parent = symbols[parent_index] if parent_index is not None else None
                    kind = configured_kind
                    if (
                        kind == "function"
                        and parent
                        and parent.kind in {"class", "interface", "trait", "struct"}
                    ):
                        kind = "constructor" if name in {"__init__", "constructor"} else "method"
                    qualified = f"{parent.qualified_name}.{name}" if parent else name
                    prefix = self._text(source, node)[:200]
                    current_parent = len(symbols)
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            qualified_name=qualified,
                            kind=kind,
                            signature=self._signature(source, node),
                            start_line=node.start_point.row + 1,
                            end_line=node.end_point.row + 1,
                            start_column=node.start_point.column + 1,
                            end_column=node.end_point.column + 1,
                            parent_index=parent_index,
                            visibility=self._visibility(prefix),
                            is_async=bool(re.search(r"\basync\b", prefix)),
                            is_static=bool(re.search(r"\bstatic\b|@staticmethod", prefix)),
                            documentation=self._documentation(source, node),
                            metadata={"node_type": node.type},
                        )
                    )
            for child in node.named_children:
                visit(child, current_parent)

        visit(tree.root_node)
        syntax_errors = sum(
            1 for node in self._walk(tree.root_node) if node.is_error or node.is_missing
        )
        decoded = source.decode("utf-8", "replace")
        return ParseResult(
            symbols=symbols,
            imports=self._imports(decoded),
            syntax_error_count=syntax_errors,
            parse_success=True,
        )

    @staticmethod
    def _visibility(prefix: str) -> str | None:
        match = re.search(r"\b(public|private|protected|internal)\b", prefix)
        return match.group(1) if match else None
