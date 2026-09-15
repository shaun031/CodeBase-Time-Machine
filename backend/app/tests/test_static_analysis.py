from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.ingestion_errors import IngestionError
from app.parsers.registry import ParserRegistry
from app.services.files import FileService
from app.services.import_resolver import ImportResolver
from app.services.language_detector import LanguageDetector
from app.services.task_executor import TaskExecutor


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("app.py", "Python"),
        ("src/app.js", "JavaScript"),
        ("src/app.ts", "TypeScript"),
        ("src/app.tsx", "TSX"),
        ("App.java", "Java"),
        ("main.c", "C"),
        ("main.cpp", "C++"),
        ("main.go", "Go"),
        ("index.php", "PHP"),
        ("templates/index.html", "HTML"),
        ("styles/site.css", "CSS"),
        ("database/schema.sql", "SQL"),
        ("Dockerfile", "Dockerfile"),
        ("scripts/deploy.ps1", "PowerShell"),
        ("README.md", None),
    ],
)
def test_language_detection(path, language):
    assert LanguageDetector().detect(path).language == language


def test_file_filtering_and_binary_detection():
    detector = LanguageDetector()
    assert detector.detect("node_modules/pkg/index.js").excluded
    assert detector.detect("src/logo.png").binary_by_extension
    assert detector.is_binary(b"text\0binary")
    assert not detector.is_binary(b"plain text\n")


@pytest.mark.parametrize(
    ("language", "source", "expected"),
    [
        (
            "Python",
            b"class User:\n    async def load(self, value: int):\n        return value\n",
            ("class", "method", "User.load"),
        ),
        (
            "JavaScript",
            b"class User { static load() {} }\nfunction make() {}",
            ("class", "method", "User.load"),
        ),
        (
            "TypeScript",
            b"interface User { name: string }\nfunction make(): User { return {name: 'x'} }",
            ("interface", "function", "make"),
        ),
        ("TSX", b"export function App(){ return <main /> }", ("function", "function", "App")),
        (
            "Java",
            b"class User { User() {} public void load() {} }",
            ("class", "constructor", "User.User"),
        ),
        (
            "C",
            b"struct User { int id; }; int load(void) { return 1; }",
            ("struct", "function", "load"),
        ),
        ("C++", b"class User { public: void load() {} };", ("class", "method", "User.load")),
        ("Go", b"package main\nfunc Load() {}", ("function", "function", "Load")),
        (
            "PHP",
            b"<?php\nclass User { public function load() {} }",
            ("class", "method", "User.load"),
        ),
    ],
)
def test_tree_sitter_symbol_extraction(language, source, expected):
    result = ParserRegistry().get(language).parse(source)
    kinds = [symbol.kind for symbol in result.symbols]
    names = [symbol.qualified_name for symbol in result.symbols]
    assert result.parse_success
    assert expected[0] in kinds and expected[1] in kinds
    assert expected[2] in names


@pytest.mark.parametrize(
    ("language", "source", "module"),
    [
        ("Python", b"from app.services import UserService\n", "app.services"),
        ("JavaScript", b"import {x} from './utils'\n", "./utils"),
        ("TypeScript", b"const x = require('./x')\n", "./x"),
        ("Java", b"import com.example.UserService;\nclass A {}", "com.example.UserService"),
        ("C", b'#include "local.h"\n', "local.h"),
        ("Go", b'package p\nimport "example/pkg"\n', "example/pkg"),
        ("PHP", b"<?php\nuse App\\Services\\UserService;\n", "App\\Services\\UserService"),
    ],
)
def test_import_extraction(language, source, module):
    assert module in [item.module for item in ParserRegistry().get(language).parse(source).imports]


def test_syntax_error_recovery_and_unsupported_language():
    result = ParserRegistry().get("Python").parse(b"def broken(:\n")
    assert result.parse_success and result.syntax_error_count > 0
    assert ParserRegistry().get("Ruby") is None


def test_javascript_arrow_function_extraction():
    result = ParserRegistry().get("JavaScript").parse(b"const loadUser = async (id) => id\n")
    symbol = result.symbols[0]
    assert symbol.name == "loadUser" and symbol.kind == "function" and symbol.is_async


def test_python_function_and_method_docstrings_are_extracted():
    result = (
        ParserRegistry()
        .get("Python")
        .parse(
            b"class Calculator:\n"
            b"    def total(self):\n"
            b'        """Return the total."""\n'
            b"        return 1\n"
        )
    )
    method = next(item for item in result.symbols if item.name == "total")
    assert method.documentation == "Return the total."


@pytest.mark.parametrize(
    "path",
    [
        "../../etc/passwd",
        "C:\\Windows\\System32\\drivers\\etc\\hosts",
        "/etc/passwd",
        "src/../secret",
    ],
)
def test_repository_path_validation_rejects_traversal(path):
    with pytest.raises(IngestionError) as error:
        FileService.validate_repository_path(path)
    assert error.value.code == "INVALID_FILE_PATH"


def test_empty_text_file_has_a_valid_display_range(monkeypatch):
    repository_id = uuid4()
    repository = SimpleNamespace(id=repository_id)
    item = SimpleNamespace(
        path="empty.js",
        blob_sha="e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
        size_bytes=0,
        is_binary=False,
    )
    git = SimpleNamespace(
        storage=SimpleNamespace(path=lambda _repository_id: None),
        get_blob=lambda *_args: b"",
    )
    service = FileService(None)
    monkeypatch.setattr(service, "_ready", lambda _repository_id: repository)
    monkeypatch.setattr(service, "get_file", lambda _repository_id, _path: item)
    monkeypatch.setattr("app.services.files.GitService", lambda _settings: git)

    result = service.get_content(repository_id, "empty.js", None, None)

    assert result.content == ""
    assert result.start_line == result.end_line == 1
    assert result.total_lines == 0
    assert not result.truncated


def test_simple_local_import_resolution():
    ids = {"src/utils.ts": uuid4(), "app/services.py": uuid4()}
    resolver = ImportResolver()
    assert resolver.resolve("src/main.ts", "./utils", "TypeScript", ids) == ids["src/utils.ts"]
    assert resolver.resolve("main.py", "app.services", "Python", ids) == ids["app/services.py"]
    assert resolver.resolve("src/main.ts", "react", "TypeScript", ids) is None


def test_oversized_source_is_not_read():
    from app.core.config import Settings
    from app.services.code_index import CodeIndexService
    from app.services.git import GitTreeEntry

    class NoReadGit:
        def get_blob(self, *args):
            raise AssertionError("oversized source must not be read")

    service = CodeIndexService(Settings(_env_file=None, max_source_file_size_bytes=10))
    result = service._analyze(
        NoReadGit(),
        None,
        GitTreeEntry("large.py", "100644", "blob", "a" * 40, 11),
        "Python",
    )
    assert result[1] == "too_large"


def test_local_task_executor_does_not_use_celery(monkeypatch):
    from app.core.config import Settings
    from app.services import task_executor as module

    started = []

    class ImmediateThread:
        def __init__(self, **kwargs):
            started.append(kwargs)

        def start(self):
            return None

    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: Settings(_env_file=None, task_execution_mode="local"),
    )
    monkeypatch.setattr(module.threading, "Thread", ImmediateThread)
    TaskExecutor().submit("index_code", uuid4(), uuid4())
    assert started and started[0]["daemon"] is True
