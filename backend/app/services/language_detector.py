from dataclasses import dataclass
from pathlib import PurePosixPath

EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        "node_modules",
        "vendor",
        "dist",
        "build",
        ".next",
        "coverage",
        "target",
        "bin",
        "obj",
        "__pycache__",
        ".venv",
        "venv",
    }
)
BINARY_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".tar",
        ".7z",
        ".rar",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".class",
        ".jar",
        ".pyc",
        ".wasm",
        ".mp3",
        ".mp4",
        ".mov",
        ".avi",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
    }
)
LANGUAGES = {
    ".py": "Python",
    ".pyw": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".tsx": "TSX",
    ".java": "Java",
    ".c": "C",
    ".h": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".hxx": "C++",
    ".go": "Go",
    ".php": "PHP",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".sql": "SQL",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".cs": "C#",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".dart": "Dart",
    ".scala": "Scala",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".lua": "Lua",
    ".r": "R",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".psm1": "PowerShell",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".hs": "Haskell",
    ".pl": "Perl",
    ".pm": "Perl",
    ".groovy": "Groovy",
    ".sol": "Solidity",
    ".tf": "HCL",
}
LANGUAGE_FILENAMES = {"dockerfile": "Dockerfile", "makefile": "Makefile"}


@dataclass(frozen=True)
class Detection:
    language: str | None
    excluded: bool
    binary_by_extension: bool


class LanguageDetector:
    def detect(self, path: str) -> Detection:
        value = PurePosixPath(path)
        excluded = any(part.lower() in EXCLUDED_DIRECTORIES for part in value.parts[:-1])
        extension = value.suffix.lower()
        language = LANGUAGE_FILENAMES.get(value.name.lower(), LANGUAGES.get(extension))
        return Detection(language, excluded, extension in BINARY_EXTENSIONS)

    @staticmethod
    def is_binary(content: bytes) -> bool:
        sample = content[:8192]
        if b"\0" in sample:
            return True
        if not sample:
            return False
        control = sum(byte < 9 or 13 < byte < 32 for byte in sample)
        return control / len(sample) > 0.1
