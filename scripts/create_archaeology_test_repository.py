"""Generate a disposable repository with deterministic archaeology evidence."""

import argparse
import os
import subprocess
from pathlib import Path


def create_archaeology_repository(destination: Path) -> dict[str, str]:
    if destination.exists():
        raise ValueError("Fixture destination must not exist")
    destination.mkdir(parents=True)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
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

    def commit(key: str, message: str, author: str, email: str) -> None:
        nonlocal counter
        counter += 1
        date = f"2021-03-{counter:02d}T12:00:00+00:00"
        environment.update(
            GIT_AUTHOR_NAME=author,
            GIT_AUTHOR_EMAIL=email,
            GIT_COMMITTER_NAME=author,
            GIT_COMMITTER_EMAIL=email,
            GIT_AUTHOR_DATE=date,
            GIT_COMMITTER_DATE=date,
        )
        git("add", "--all")
        git("commit", "-m", message)
        commits[key] = git("rev-parse", "HEAD")

    def update_volatile(revision: int, author: str) -> None:
        (destination / "src" / "volatile_service.py").write_text(
            "def current_signal(value):\n"
            f"    # deterministic revision {revision}\n"
            f"    return (value * {revision}) + {revision}\n"
            f"\nLAST_EDITOR = {author!r}\n",
            encoding="utf-8",
        )

    commits: dict[str, str] = {}
    git("init", "--initial-branch=main")
    (destination / "src").mkdir()
    (destination / "src" / "users.py").write_text(
        "def get_user(user_id):\n"
        "    record = database.get(user_id)\n"
        "    return record\n",
        encoding="utf-8",
    )
    (destination / "src" / "stable_util.py").write_text(
        "def stable_slug(value):\n"
        "    return value.strip().lower().replace(' ', '-')\n",
        encoding="utf-8",
    )
    update_volatile(1, "Alice")
    commit("introduced", "Introduce user lookup and utilities", "Alice", "alice@example.test")

    (destination / "src" / "users.py").write_text(
        "def get_user(user_id):\n"
        "    record = database.get(user_id)\n"
        "    if record is None:\n"
        "        return None\n"
        "    return record\n",
        encoding="utf-8",
    )
    update_volatile(2, "Bob")
    commit("modified", "Handle missing users", "Bob", "bob@example.test")

    users = destination / "src" / "users.py"
    users.write_text(
        users.read_text(encoding="utf-8").replace("get_user", "find_user"),
        encoding="utf-8",
    )
    update_volatile(3, "Alice")
    commit("renamed", "Rename user lookup", "Alice", "alice@example.test")

    (destination / "src" / "services").mkdir()
    git("mv", "src/users.py", "src/services/user_service.py")
    update_volatile(4, "Bob")
    commit("moved", "Move lookup into the service package", "Bob", "bob@example.test")

    rewritten = (
        "def find_user(user_id, include_inactive=False):\n"
        "    query = users.where(id=user_id)\n"
        "    if not include_inactive:\n"
        "        query = query.where(active=True)\n"
        "    records = query.limit(1).all()\n"
        "    return records[0] if records else None\n"
    )
    service = destination / "src" / "services" / "user_service.py"
    service.write_text(rewritten, encoding="utf-8")
    update_volatile(5, "Bob")
    commit("rewritten", "Rewrite user lookup around query objects", "Bob", "bob@example.test")

    (destination / "src" / "admin").mkdir()
    (destination / "src" / "admin" / "admin_user_service.py").write_text(
        rewritten,
        encoding="utf-8",
    )
    update_volatile(6, "Bob")
    commit("copied", "Reuse lookup in the admin service", "Bob", "bob@example.test")

    (destination / "src" / "admin" / "admin_user_service.py").unlink()
    update_volatile(7, "Charlie")
    commit("deleted_copy", "Remove the copied admin lookup", "Charlie", "charlie@example.test")
    commits["head"] = commits["deleted_copy"]
    return commits


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    print(create_archaeology_repository(arguments.destination.resolve()))
