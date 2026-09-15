import re
from difflib import SequenceMatcher

_COMMENT = re.compile(r"(?m)(//[^\n]*|#[^\n]*|/\*.*?\*/)", re.DOTALL)
_TOKEN = re.compile(r"[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|[^\s]", re.UNICODE)


def normalized_tokens(source: str | None) -> list[str]:
    """Remove comments/formatting while preserving identifiers and operators."""
    if not source:
        return []
    return _TOKEN.findall(_COMMENT.sub(" ", source))


def code_similarity(left: str | None, right: str | None) -> float:
    a, b = normalized_tokens(left), normalized_tokens(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b, autojunk=False).ratio(), 6)


def changed_lines(left: str | None, right: str | None) -> tuple[int, int]:
    old = (left or "").splitlines()
    new = (right or "").splitlines()
    matcher = SequenceMatcher(None, old, new, autojunk=False)
    deleted = added = 0
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in {"delete", "replace"}:
            deleted += old_end - old_start
        if tag in {"insert", "replace"}:
            added += new_end - new_start
    return added, deleted
