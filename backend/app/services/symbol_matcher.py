import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from uuid import UUID

from app.parsers.models import ParsedSymbol


def normalized_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", "", value).casefold()


def digest(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8", "replace")).hexdigest()


def signature_shape(value: str | None, name: str) -> str:
    normalized = normalized_text(value)
    return normalized.replace(name.casefold(), "<name>", 1)


@dataclass(frozen=True)
class HistoricalSymbol:
    symbol: ParsedSymbol
    source: str
    file_path: str
    file_lineage_id: UUID
    lineage_id: UUID | None = None
    version_id: UUID | None = None
    parent_lineage_id: UUID | None = None

    @property
    def normalized_source(self) -> str:
        value = self.source
        if self.symbol.documentation:
            value = value.replace(self.symbol.documentation, "", 1)
        if self.symbol.signature:
            value = value.replace(self.symbol.signature, "", 1)
        return normalized_text(value)

    @property
    def body_hash(self) -> str:
        return digest(self.source)

    @property
    def normalized_body_hash(self) -> str:
        return digest(self.normalized_source)

    @property
    def signature_hash(self) -> str:
        return digest(normalized_text(self.symbol.signature))

    @property
    def structure_hash(self) -> str:
        parent = self.symbol.qualified_name.rpartition(".")[0]
        shape = signature_shape(self.symbol.signature, self.symbol.name)
        return digest(f"{self.symbol.kind}:{parent}:{shape}")


@dataclass(frozen=True)
class SymbolMatch:
    previous_index: int
    current_index: int
    match_type: str
    confidence: float
    evidence: dict[str, object]


@dataclass(frozen=True)
class MatchResult:
    matches: list[SymbolMatch]
    unmatched_previous: list[int]
    unmatched_current: list[int]


class SymbolMatcher:
    """Conservative, deterministic matcher for normalized parser symbols."""

    def __init__(self, threshold: float = 0.86, rename_threshold: float = 0.9) -> None:
        self.threshold = threshold
        self.rename_threshold = rename_threshold

    @staticmethod
    def _parent_name(item: HistoricalSymbol) -> str:
        return item.symbol.qualified_name.rpartition(".")[0]

    @staticmethod
    def _compatible_kind(previous: str, current: str) -> bool:
        return previous == current or {previous, current} == {"function", "method"}

    def _score(
        self, previous: HistoricalSymbol, current: HistoricalSymbol
    ) -> tuple[float, str, dict[str, object]] | None:
        old, new = previous.symbol, current.symbol
        if not self._compatible_kind(old.kind, new.kind):
            return None
        same_file = previous.file_lineage_id == current.file_lineage_id
        same_path = previous.file_path == current.file_path
        same_parent = self._parent_name(previous) == self._parent_name(current)
        body_similarity = SequenceMatcher(
            None, previous.normalized_source, current.normalized_source, autojunk=False
        ).ratio()
        signature_similarity = SequenceMatcher(
            None,
            signature_shape(old.signature, old.name),
            signature_shape(new.signature, new.name),
            autojunk=False,
        ).ratio()
        evidence: dict[str, object] = {
            "same_file_lineage": same_file,
            "same_parent": same_parent,
            "body_similarity": round(body_similarity, 4),
            "signature_similarity": round(signature_similarity, 4),
            "file_rename_detected": same_file and not same_path,
            "name_changed": old.name != new.name,
        }
        if same_file and old.qualified_name == new.qualified_name:
            return (1.0 if same_path else 0.99), ("exact" if same_path else "file_rename"), evidence
        if same_file and old.name == new.name and same_parent:
            return 0.97, "same_name_modified", evidence
        if previous.normalized_body_hash == current.normalized_body_hash and same_parent:
            return (
                (0.95 if same_file else 0.91),
                ("symbol_rename" if same_file else "symbol_move"),
                evidence,
            )
        if (
            same_file
            and same_parent
            and old.name != new.name
            and body_similarity >= self.rename_threshold
        ):
            confidence = min(0.94, 0.6 * body_similarity + 0.4 * signature_similarity)
            return confidence, "symbol_rename", evidence
        if not same_file and old.name == new.name and body_similarity >= self.rename_threshold:
            confidence = min(0.9, 0.58 * body_similarity + 0.32 * signature_similarity)
            return confidence, "symbol_move", evidence
        if same_file and old.name == new.name:
            confidence = 0.58 + 0.34 * body_similarity + 0.08 * signature_similarity
            if confidence >= self.threshold:
                return confidence, "same_name_modified", evidence
        return None

    def match(
        self, previous: list[HistoricalSymbol], current: list[HistoricalSymbol]
    ) -> MatchResult:
        candidates: list[tuple[float, int, int, str, dict[str, object]]] = []
        by_current: dict[int, list[float]] = {}
        by_previous: dict[int, list[float]] = {}
        for old_index, old in enumerate(previous):
            for new_index, new in enumerate(current):
                scored = self._score(old, new)
                if scored is None:
                    continue
                confidence, match_type, evidence = scored
                required = (
                    self.rename_threshold
                    if match_type in {"symbol_rename", "symbol_move"}
                    else self.threshold
                )
                if confidence < required:
                    continue
                candidates.append((confidence, old_index, new_index, match_type, evidence))
                by_current.setdefault(new_index, []).append(confidence)
                by_previous.setdefault(old_index, []).append(confidence)

        ambiguous: set[tuple[int, int]] = set()
        for confidence, old_index, new_index, _, _ in candidates:
            old_scores = sorted(by_previous[old_index], reverse=True)
            new_scores = sorted(by_current[new_index], reverse=True)
            if (
                len(old_scores) > 1
                and abs(confidence - old_scores[1]) < 0.03
                or len(new_scores) > 1
                and abs(confidence - new_scores[1]) < 0.03
            ):
                ambiguous.add((old_index, new_index))

        matches: list[SymbolMatch] = []
        used_previous: set[int] = set()
        used_current: set[int] = set()
        for confidence, old_index, new_index, match_type, evidence in sorted(
            candidates, key=lambda value: (-value[0], value[1], value[2])
        ):
            if (
                (old_index, new_index) in ambiguous
                or old_index in used_previous
                or new_index in used_current
            ):
                continue
            matches.append(
                SymbolMatch(old_index, new_index, match_type, round(confidence, 4), evidence)
            )
            used_previous.add(old_index)
            used_current.add(new_index)
        return MatchResult(
            matches,
            [index for index in range(len(previous)) if index not in used_previous],
            [index for index in range(len(current)) if index not in used_current],
        )
