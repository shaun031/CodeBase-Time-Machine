"""Create ONLY a new disposable test fixture; never called by the application."""

import argparse
import os
import subprocess
from pathlib import Path


def create_repository(destination: Path) -> dict[str, str]:
    if destination.exists():
        raise ValueError("Fixture destination must not exist")
    destination.mkdir(parents=True)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Fixture Author",
            "GIT_AUTHOR_EMAIL": "fixture@example.test",
            "GIT_COMMITTER_NAME": "Fixture Author",
            "GIT_COMMITTER_EMAIL": "fixture@example.test",
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
                    "tag.gpgsign=false",
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

    def commit(message: str) -> str:
        nonlocal counter
        counter += 1
        date = f"2020-01-{counter:02d}T12:00:00+00:00"
        environment.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        git("add", "--all")
        git("commit", "-m", message)
        return git("rev-parse", "HEAD")

    git("init", "--initial-branch=main")
    (destination / "README.md").write_text("# Fixture\n", encoding="utf-8")
    root = commit("Initial README")
    (destination / "app.py").write_text("print('hello')\n", encoding="utf-8")
    commit("Add application")
    (destination / "app.py").write_text("print('hello')\nprint('world')\n", encoding="utf-8")
    unicode = commit("Unicode café 日本語\n\nMultiline body with | and tabs\tand punctuation.")
    (destination / "test.py").write_text("# metadata only, never execute\n", encoding="utf-8")
    commit("Add test text")
    git("mv", "app.py", "main.py")
    rename = commit("Rename application")
    git("tag", "v0.1", rename)
    git("checkout", "-b", "feature")
    (destination / "feature.txt").write_text("feature\n", encoding="utf-8")
    feature = commit("Feature branch")
    git("checkout", "main")
    (destination / "space café.txt").write_text("spaced path\n", encoding="utf-8")
    main = commit("Main branch change")
    environment.update(
        GIT_AUTHOR_DATE="2020-01-08T12:00:00+00:00", GIT_COMMITTER_DATE="2020-01-08T12:00:00+00:00"
    )
    git("merge", "--no-ff", "feature", "-m", "Merge feature")
    merge = git("rev-parse", "HEAD")
    counter = 8
    (destination / "image.bin").write_bytes(b"\0\1\2\xff\n")
    binary = commit("Add binary")
    (destination / "test.py").unlink()
    head = commit("Delete test text")
    git("tag", "-a", "v1.0", "-m", "Annotated fixture tag")
    return {
        "root": root,
        "unicode": unicode,
        "rename": rename,
        "feature": feature,
        "main": main,
        "merge": merge,
        "binary": binary,
        "head": head,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(create_repository(args.destination.resolve()))
