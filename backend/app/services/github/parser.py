import re
from typing import Literal

from app.services.github.models import ParsedIssueReference

REFERENCE = re.compile(
    r"(?:(?P<verb>fix(?:e[sd])?|clos(?:e[sd])?|resolv(?:e[sd])?|refs?|see)\s*:?\s*)?"
    r"(?:(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+))?"
    r"#(?P<number>[1-9][0-9]*)",
    re.IGNORECASE,
)


def extract_issue_references(text: str | None) -> list[ParsedIssueReference]:
    if not text:
        return []
    found: list[ParsedIssueReference] = []
    seen: set[tuple[str | None, str | None, int, str]] = set()
    for match in REFERENCE.finditer(text):
        verb = (match.group("verb") or "").lower()
        kind: Literal["fixes", "closes", "resolves", "mentions"]
        if verb.startswith("fix"):
            kind = "fixes"
        elif verb.startswith("clos"):
            kind = "closes"
        elif verb.startswith("resolv"):
            kind = "resolves"
        else:
            kind = "mentions"
        owner = match.group("owner")
        repository = match.group("repo")
        number = int(match.group("number"))
        key = (
            owner.lower() if owner else None,
            repository.lower() if repository else None,
            number,
            kind,
        )
        if key in seen:
            continue
        seen.add(key)
        found.append(
            ParsedIssueReference(
                owner=owner,
                repository=repository,
                number=number,
                reference_type=kind,
                raw_reference=match.group(0),
                confidence=0.98 if kind != "mentions" else 0.55,
            )
        )
    return found
