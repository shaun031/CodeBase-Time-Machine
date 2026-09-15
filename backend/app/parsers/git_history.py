from dataclasses import dataclass
from datetime import datetime

from app.core.ingestion_errors import IngestionError


def text(value: bytes) -> str:
    return value.decode("utf-8", errors="backslashreplace").replace("\x00", "\ufffd")


@dataclass
class GitCommit:
    sha: str
    parents: list[str]
    author_name: str
    author_email: str
    committer_name: str
    committer_email: str
    authored_at: datetime
    committed_at: datetime
    message: str


@dataclass
class GitFileChange:
    old_path: str | None
    new_path: str | None
    change_type: str
    additions: int | None
    deletions: int | None
    similarity_score: int | None


def parse_commit(raw: bytes) -> GitCommit:
    fields = raw.rstrip(b"\n").split(b"\0", 8)
    if len(fields) != 9:
        raise IngestionError("INVALID_GIT_DATA", "Commit metadata could not be decoded.")
    return GitCommit(
        text(fields[0]),
        text(fields[1]).split(),
        text(fields[2]),
        text(fields[3]),
        text(fields[4]),
        text(fields[5]),
        datetime.fromisoformat(text(fields[6])),
        datetime.fromisoformat(text(fields[7])),
        text(fields[8]),
    )


def parse_changes(raw: bytes, numstat: bytes) -> list[GitFileChange]:
    stats: dict[tuple[bytes, bytes], tuple[int | None, int | None]] = {}
    tokens = iter(numstat.split(b"\0"))
    for token in tokens:
        if not token:
            continue
        added, deleted, path = token.split(b"\t", 2)
        old, new = (path, path) if path else (next(tokens), next(tokens))
        stats[old, new] = (
            None if added == b"-" else int(added),
            None if deleted == b"-" else int(deleted),
        )
    changes = []
    tokens = iter(raw.split(b"\0"))
    for header in tokens:
        if not header:
            continue
        status = header.split()[-1].decode("ascii")
        path = next(tokens)
        old, new = (path, next(tokens)) if status[0] in "RC" else (path, path)
        additions, deletions = stats[old, new]
        kind = {
            "A": "added",
            "D": "deleted",
            "R": "renamed",
            "C": "copied",
            "M": "modified",
            "T": "modified",
        }.get(status[0])
        if kind is None:
            raise IngestionError("INVALID_GIT_DATA", "Unsupported Git change record.")
        changes.append(
            GitFileChange(
                None if kind == "added" else text(old),
                None if kind == "deleted" else text(new),
                kind,
                additions,
                deletions,
                int(status[1:]) if status[0] in "RC" else None,
            )
        )
    return changes
