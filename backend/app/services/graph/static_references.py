import posixpath
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import urlsplit


@dataclass(frozen=True)
class StaticReference:
    target_path: str
    edge_type: str
    reference_kind: str
    raw_reference: str
    line: int


class _HTMLReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value for name, value in attrs if value is not None}
        if tag.lower() == "script" and values.get("src"):
            self.references.append((values["src"], "script", self.getpos()[0]))
        if tag.lower() == "link" and values.get("href"):
            relations = {value.lower() for value in values.get("rel", "").split()}
            if "stylesheet" in relations:
                self.references.append((values["href"], "stylesheet", self.getpos()[0]))


CSS_IMPORT = re.compile(
    r"@import\s+(?:url\(\s*)?[\"']?([^\"')\s;]+)[\"']?\s*\)?",
    re.IGNORECASE,
)


def resolve_local_reference(source_path: str, raw_reference: str) -> str | None:
    value = raw_reference.strip()
    if not value or value.startswith(("//", "#")) or "\\" in value:
        return None
    split = urlsplit(value)
    if split.scheme or split.netloc:
        return None
    path = split.path
    if not path:
        return None
    base = "" if path.startswith("/") else PurePosixPath(source_path).parent.as_posix()
    candidate = posixpath.normpath(posixpath.join(base, path.lstrip("/")))
    if candidate == ".." or candidate.startswith("../") or candidate.startswith("/"):
        return None
    return candidate


def extract_static_references(
    source_path: str, source_text: str, repository_paths: set[str]
) -> list[StaticReference]:
    suffix = PurePosixPath(source_path).suffix.lower()
    found: list[tuple[str, str, str, int]] = []
    if suffix in {".html", ".htm"}:
        parser = _HTMLReferenceParser()
        parser.feed(source_text)
        found.extend((raw, "REFERENCES", kind, line) for raw, kind, line in parser.references)
    elif suffix == ".css":
        for match in CSS_IMPORT.finditer(source_text):
            found.append(
                (
                    match.group(1),
                    "IMPORTS",
                    "css_import",
                    source_text.count("\n", 0, match.start()) + 1,
                )
            )
    result: list[StaticReference] = []
    seen: set[tuple[str, str, str]] = set()
    for raw, edge_type, kind, line in found:
        target = resolve_local_reference(source_path, raw)
        key = (target or "", edge_type, kind)
        if target not in repository_paths or key in seen:
            continue
        seen.add(key)
        result.append(StaticReference(target, edge_type, kind, raw, line))
    return result
