import os
import subprocess
from pathlib import Path


def _git(path: Path, *args: str, date: str | None = None) -> str:
    environment = os.environ.copy()
    if date:
        environment["GIT_AUTHOR_DATE"] = date
        environment["GIT_COMMITTER_DATE"] = date
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )
    return result.stdout.strip()


def _write(path: Path, name: str, content: str) -> None:
    target = path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _commit(path: Path, message: str, date: str) -> str:
    _git(path, "add", "-A")
    _git(path, "commit", "-m", message, date=date)
    return _git(path, "rev-parse", "HEAD")


CONTROLLER = """from service import execute

def handle():
    return execute()
"""
REPOSITORY = """from model import Entity

def load():
    return Entity()
"""


def create_architecture_history_repository(path: Path) -> dict[str, str]:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--initial-branch=main")
    _git(path, "config", "user.name", "Architecture Fixture")
    _git(path, "config", "user.email", "architecture@example.test")
    _write(path, "controller.py", CONTROLLER)
    _write(path, "service.py", "from repository import load\n\ndef execute():\n    return load()\n")
    _write(path, "repository.py", REPOSITORY)
    _write(path, "model.py", "class Entity:\n    pass\n")
    commits = {"c1": _commit(path, "C1 layered architecture", "2024-01-01T12:00:00Z")}
    _git(path, "tag", "v1.0")
    _write(path, "payment.py", "from service import execute\n\ndef pay():\n    return execute()\n")
    commits["c2"] = _commit(path, "C2 add payment", "2024-02-01T12:00:00Z")
    _write(
        path,
        "controller.py",
        "from service import execute\nfrom repository import load\n\ndef handle():\n"
        "    return execute() or load()\n",
    )
    commits["c3"] = _commit(path, "C3 controller bypass", "2024-03-01T12:00:00Z")
    _write(
        path,
        "repository.py",
        "from model import Entity\nfrom controller import handle\n\ndef load():\n"
        "    return Entity()\n",
    )
    commits["c4"] = _commit(path, "C4 introduce cycle", "2024-04-01T12:00:00Z")
    _write(path, "repository.py", REPOSITORY)
    commits["c5"] = _commit(path, "C5 resolve cycle", "2024-05-01T12:00:00Z")
    _write(path, "controller.py", CONTROLLER)
    commits["c6"] = _commit(path, "C6 resolve layer violation", "2024-06-01T12:00:00Z")
    _git(path, "tag", "v2.0")
    return commits


if __name__ == "__main__":
    import sys

    print(create_architecture_history_repository(Path(sys.argv[1])))
