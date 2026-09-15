from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReferenceCandidate:
    source_symbol_id: UUID
    name: str
    qualified_name: str | None
    line: int
    reference_type: str


@dataclass(frozen=True)
class ResolvedReference:
    target_symbol_id: UUID
    resolution_type: str
    confidence: float
