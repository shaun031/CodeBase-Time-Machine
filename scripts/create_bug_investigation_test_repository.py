"""Create a deterministic Git fixture for Phase 9 tests.

The fixture is source text only. Tests inspect its Git objects and never execute its code.
"""

import subprocess
from pathlib import Path


def run(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def write(path: Path, relative: str, content: str) -> None:
    target = path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def commit(path: Path, message: str) -> str:
    run(path, "add", "--all")
    run(path, "commit", "-m", message)
    return run(path, "rev-parse", "HEAD")


def create_bug_investigation_repository(path: Path) -> dict[str, str]:
    path.mkdir(parents=True)
    run(path, "init", "-b", "main")
    run(path, "config", "user.name", "Phase Nine Fixture")
    run(path, "config", "user.email", "phase9@example.invalid")

    write(
        path,
        "src/calc.py",
        "def reciprocal(value):\n    if value == 0:\n        return None\n    return 1 / value\n",
    )
    commits = {"A": commit(path, "A: add safe reciprocal")}

    write(path, "README.md", "# Calculator\n\nA small fixture.\n")
    commits["B"] = commit(path, "B: document calculator")

    write(
        path,
        "src/calc.py",
        "def reciprocal(value):\n    if value < 0:\n        return None\n    return 1 / value\n",
    )
    commits["C"] = commit(path, "C: allow zero values")

    run(path, "mv", "src/calc.py", "src/math_utils.py")
    write(path, "docs/usage.md", "Call `reciprocal` with a nonzero value.\n")
    commits["D"] = commit(path, "D: rename math module and format docs")

    write(path, "vendor/generated.min.js", "var generated=1;\n")
    commit(path, "generated bundle update")

    write(
        path,
        "src/math_utils.py",
        "def reciprocal(value):\n    if value == 0:\n        return None\n    return 1 / value\n",
    )
    commits["E"] = commit(path, "E: fix zero reciprocal regression")
    return commits


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    arguments = parser.parse_args()
    print(create_bug_investigation_repository(arguments.path))
