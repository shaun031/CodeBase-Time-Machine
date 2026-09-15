from app.parsers.languages.c import CParser


class CppParser(CParser):
    language = "C++"
    grammar = "cpp"
    symbol_nodes = {
        **CParser.symbol_nodes,
        "class_specifier": "class",
        "namespace_definition": "module",
    }
