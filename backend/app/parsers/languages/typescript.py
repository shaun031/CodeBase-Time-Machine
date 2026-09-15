from app.parsers.languages.javascript import JavaScriptParser


class TypeScriptParser(JavaScriptParser):
    language = "TypeScript"
    grammar = "typescript"
    symbol_nodes = {
        **JavaScriptParser.symbol_nodes,
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "method_signature": "function",
    }


class TsxParser(TypeScriptParser):
    language = "TSX"
    grammar = "tsx"
