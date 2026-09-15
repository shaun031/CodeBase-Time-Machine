from collections import defaultdict
from pathlib import PurePosixPath
from uuid import UUID

from app.db.models import CodeImport, CodeSymbol, RepositoryFile
from app.services.graph.models import ReferenceCandidate, ResolvedReference


class DependencyResolver:
    """Resolve only deterministic local symbol references; ambiguity produces no edge."""

    def __init__(
        self,
        symbols: list[CodeSymbol],
        files: dict[UUID, RepositoryFile],
        imports: list[CodeImport],
        max_candidates: int,
    ) -> None:
        self.symbols = symbols
        self.files = files
        self.max_candidates = max_candidates
        self.by_name: dict[str, list[CodeSymbol]] = defaultdict(list)
        self.by_qualified: dict[str, list[CodeSymbol]] = defaultdict(list)
        self.by_file_name: dict[tuple[UUID, str], list[CodeSymbol]] = defaultdict(list)
        self.import_targets: dict[UUID, set[UUID]] = defaultdict(set)
        for symbol in symbols:
            self.by_name[symbol.name].append(symbol)
            self.by_qualified[symbol.qualified_name].append(symbol)
            self.by_file_name[(symbol.file_id, symbol.name)].append(symbol)
        for item in imports:
            if item.target_file_id:
                self.import_targets[item.source_file_id].add(item.target_file_id)

    @staticmethod
    def _one(
        values: list[CodeSymbol], resolution: str, confidence: float
    ) -> ResolvedReference | None:
        unique = {item.id: item for item in values}
        if len(unique) != 1:
            return None
        return ResolvedReference(next(iter(unique)), resolution, confidence)

    def resolve(
        self, source: CodeSymbol, reference: ReferenceCandidate
    ) -> ResolvedReference | None:
        qualified = reference.qualified_name
        if qualified:
            exact = self.by_qualified.get(qualified, [])
            result = self._one(exact, "qualified_name", 0.98)
            if result:
                return result

        same_file = self.by_file_name.get((source.file_id, reference.name), [])
        result = self._one(same_file, "same_file", 0.95)
        if result:
            return result

        imported = [
            item
            for item in self.by_name.get(reference.name, [])[: self.max_candidates + 1]
            if item.file_id in self.import_targets.get(source.file_id, set())
        ]
        result = self._one(imported, "imported_symbol", 0.9)
        if result:
            return result

        source_path = PurePosixPath(self.files[source.file_id].path)
        same_module = [
            item
            for item in self.by_name.get(reference.name, [])[: self.max_candidates + 1]
            if PurePosixPath(self.files[item.file_id].path).parent == source_path.parent
        ]
        result = self._one(same_module, "same_module", 0.82)
        if result:
            return result

        repository = self.by_name.get(reference.name, [])
        if len(repository) > self.max_candidates:
            return None
        return self._one(repository, "unique_repository", 0.72)
