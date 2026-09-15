"""Generate a disposable repository with deterministic symbol history."""

import argparse
import os
import subprocess
from pathlib import Path


def create_history_repository(destination: Path) -> dict[str, str]:
    if destination.exists():
        raise ValueError("Fixture destination must not exist")
    destination.mkdir(parents=True)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "History Fixture",
            "GIT_AUTHOR_EMAIL": "history@example.test",
            "GIT_COMMITTER_NAME": "History Fixture",
            "GIT_COMMITTER_EMAIL": "history@example.test",
        }
    )
    counter = 0

    def git(*args: str) -> str:
        return (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    "core.hooksPath=" + str(destination / "no-hooks"),
                    "-c",
                    "commit.gpgsign=false",
                    "-c",
                    "core.autocrlf=false",
                    *args,
                ],
                cwd=destination,
                env=environment,
                stderr=subprocess.PIPE,
            )
            .decode("utf-8")
            .strip()
        )

    def commit(key: str, message: str) -> tuple[str, str]:
        nonlocal counter
        counter += 1
        date = f"2021-02-{counter:02d}T12:00:00+00:00"
        environment.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        git("add", "--all")
        git("commit", "-m", message)
        return key, git("rev-parse", "HEAD")

    commits: dict[str, str] = {}
    git("init", "--initial-branch=main")

    (destination / "calculator.py").write_text(
        "def calculate_total(values):\n"
        '    """Add the supplied values."""\n'
        "    return sum(values)\n\n"
        "def unrelated(value):\n    return value * 2\n",
        encoding="utf-8",
    )
    key, sha = commit("introduced", "Add calculator")
    commits[key] = sha

    (destination / "calculator.py").write_text(
        'def calculate_total(values):\n    """Add the supplied values."""\n'
        "    total = sum(values)\n    return round(total, 2)\n\n"
        "def unrelated(value):\n    return value * 2\n",
        encoding="utf-8",
    )
    key, sha = commit("body", "Round calculated totals")
    commits[key] = sha

    (destination / "calculator.py").write_text(
        'def calculate_total(values, tax=0):\n    """Add values and optional tax."""\n'
        "    total = sum(values) + tax\n    return round(total, 2)\n\n"
        "def unrelated(value):\n    return value * 2\n",
        encoding="utf-8",
    )
    key, sha = commit("signature", "Support tax in totals")
    commits[key] = sha

    (destination / "calculator.py").write_text(
        "class Calculator:\n"
        "    def format_value(self, value):\n"
        '        return f"{value:.2f}"\n\n'
        'def calculate_total(values, tax=0):\n    """Add values and optional tax."""\n'
        "    total = sum(values) + tax\n    return round(total, 2)\n\n"
        "def unrelated(value):\n    return value * 2\n",
        encoding="utf-8",
    )
    key, sha = commit("class", "Add Calculator class")
    commits[key] = sha

    (destination / "calculator.py").write_text(
        "class Calculator:\n"
        "    def format_value(self, value):\n"
        '        return f"{value:.2f}"\n\n'
        "    def calculate_total(self, values, tax=0):\n"
        '        """Add values and optional tax."""\n'
        "        total = sum(values) + tax\n"
        "        return round(total, 2)\n\n"
        "def unrelated(value):\n    return value * 2\n",
        encoding="utf-8",
    )
    key, sha = commit("nested", "Move total calculation into Calculator")
    commits[key] = sha

    (destination / "calculator.py").write_text(
        "class Calculator:\n"
        "    def format_value(self, value):\n"
        '        return f"{value:.2f}"\n\n'
        "    def total(self, values, tax=0):\n"
        '        """Add values and optional tax."""\n'
        "        total = sum(values) + tax\n"
        "        return round(total, 2)\n\n"
        "def unrelated(value):\n    return value * 2\n",
        encoding="utf-8",
    )
    key, sha = commit("renamed_symbol", "Rename calculation method")
    commits[key] = sha

    git("mv", "calculator.py", "math_utils.py")
    key, sha = commit("renamed_file", "Rename calculator module")
    commits[key] = sha

    path = destination / "math_utils.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "Add values and optional tax.", "Return a rounded total including optional tax."
        ),
        encoding="utf-8",
    )
    key, sha = commit("documentation", "Clarify total documentation café")
    commits[key] = sha

    path.write_text(
        "class Calculator:\n"
        "    def format_value(self, value):\n"
        '        return f"{value:.2f}"\n\n'
        "def unrelated(value):\n    return value * 2\n",
        encoding="utf-8",
    )
    key, sha = commit("deleted", "Remove total calculation")
    commits[key] = sha

    path.write_text(
        "class Calculator:\n"
        "    def format_value(self, value):\n"
        '        return f"{value:.2f}"\n\n'
        "    def total(self, values, tax=0):\n"
        '        """Return a rounded total including optional tax."""\n'
        "        total = sum(values) + tax\n"
        "        return round(total, 2)\n\n"
        "def unrelated(value):\n    return value * 2\n",
        encoding="utf-8",
    )
    key, sha = commit("reintroduced", "Reintroduce total calculation")
    commits[key] = sha

    (destination / "README.md").write_text("# History fixture\n", encoding="utf-8")
    key, sha = commit("file_only", "Update documentation outside symbols")
    commits[key] = sha
    commits["head"] = sha
    return commits


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    print(create_history_repository(arguments.destination.resolve()))
