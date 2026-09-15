from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Commit, FileChange


@dataclass(frozen=True)
class CouplingDiagnostics:
    commits_examined: int
    commits_used: int
    commits_excluded_large: int
    candidate_pairs: int


@dataclass(frozen=True)
class CouplingAnalysis:
    pairs: list[tuple[UUID, UUID, int, float]]
    diagnostics: CouplingDiagnostics


class ChangeCouplingService:
    @staticmethod
    def calculate(
        session: Session,
        repository_id: UUID,
        paths: dict[str, UUID],
        max_files_per_commit: int,
    ) -> CouplingAnalysis:
        rows = session.execute(
            select(
                FileChange.commit_id,
                FileChange.old_path,
                FileChange.new_path,
                Commit.files_changed,
            )
            .join(Commit, Commit.id == FileChange.commit_id)
            .where(FileChange.repository_id == repository_id)
            .order_by(FileChange.commit_id)
        )
        by_commit: dict[UUID, set[UUID]] = defaultdict(set)
        commit_sizes: dict[UUID, int] = {}
        for commit_id, old_path, new_path, files_changed in rows:
            commit_sizes[commit_id] = int(files_changed)
            for path in (new_path, old_path):
                if path in paths:
                    by_commit[commit_id].add(paths[path])
        changes: Counter[UUID] = Counter()
        pairs: Counter[tuple[UUID, UUID]] = Counter()
        used = 0
        excluded = 0
        for commit_id, file_ids in by_commit.items():
            if commit_sizes[commit_id] > max_files_per_commit:
                excluded += 1
                continue
            used += 1
            ordered = sorted(file_ids, key=str)
            changes.update(ordered)
            pairs.update(combinations(ordered, 2))
        result = [
            (source, target, count, count / min(changes[source], changes[target]))
            for (source, target), count in pairs.items()
            if changes[source] and changes[target]
        ]
        return CouplingAnalysis(
            pairs=result,
            diagnostics=CouplingDiagnostics(
                commits_examined=len(by_commit),
                commits_used=used,
                commits_excluded_large=excluded,
                candidate_pairs=len(result),
            ),
        )
