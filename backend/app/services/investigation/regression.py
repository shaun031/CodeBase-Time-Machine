from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.ingestion_errors import IngestionError
from app.db.models import BisectSession, Commit, FileChange, Repository
from app.services.git import GitService


class RegressionAnalysisService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.git = GitService(settings)

    def _repository(self, repository_id: UUID) -> tuple[Repository, Path]:
        repository = self.session.get(Repository, repository_id)
        if repository is None or not repository.local_path:
            raise IngestionError("REPOSITORY_NOT_FOUND", "Repository is not available.", 404)
        return repository, self.git.storage.path(repository_id)

    def range(
        self,
        repository_id: UUID,
        good: str,
        bad: str,
        max_commits: int | None = None,
    ) -> dict[str, Any]:
        _repository, path = self._repository(repository_id)
        good = self.git.validate_sha(good)
        bad = self.git.validate_sha(bad)
        indexed = set(
            self.session.scalars(
                select(Commit.sha).where(
                    Commit.repository_id == repository_id,
                    Commit.sha.in_([good, bad]),
                )
            )
        )
        if indexed != {good, bad}:
            raise IngestionError(
                "INVESTIGATION_COMMIT_NOT_INDEXED", "Both commits must be indexed.", 404
            )
        shas = self.git.get_commit_range(
            path,
            good,
            bad,
            max_commits or self.settings.max_regression_range_commits,
        )
        commits = {
            item.sha: item
            for item in self.session.scalars(
                select(Commit).where(Commit.repository_id == repository_id, Commit.sha.in_(shas))
            )
        }
        items = [
            {
                "sha": sha,
                "short_sha": sha[:12],
                "message": commits[sha].message
                if sha in commits
                else self.git.get_commit(path, sha).message,
                "committed_at": commits[sha].committed_at.isoformat() if sha in commits else None,
                "is_merge_commit": commits[sha].is_merge_commit if sha in commits else False,
            }
            for sha in shas
        ]
        return {
            "known_good": good,
            "known_bad": bad,
            "commits": items,
            "changed_files": self.changed_files(repository_id, shas),
            "remaining_commit_count": len(items),
            "suggested_midpoint": items[(len(items) - 1) // 2] if items else None,
            "method": "static ancestry range; repository code was not executed",
        }

    def create_bisect(self, repository_id: UUID, good: str, bad: str) -> dict[str, Any]:
        result = self.range(
            repository_id, good, bad, self.settings.max_bisect_range_commits
        )
        shas = [item["sha"] for item in result["commits"]]
        current = shas[(len(shas) - 1) // 2] if shas else None
        model = BisectSession(
            repository_id=repository_id,
            good_commit_sha=result["known_good"],
            bad_commit_sha=result["known_bad"],
            current_candidate_sha=current,
            remaining_commits=shas,
            classifications={},
            remaining_commit_count=len(shas),
            status="complete" if len(shas) <= 1 else "active",
        )
        self.session.add(model)
        self.session.commit()
        return self._bisect_read(model)

    def classify(
        self, repository_id: UUID, session_id: UUID, sha: str, result: str
    ) -> dict[str, Any]:
        model = self.session.scalar(
            select(BisectSession).where(
                BisectSession.id == session_id,
                BisectSession.repository_id == repository_id,
            )
        )
        if model is None:
            raise IngestionError("BISECT_SESSION_NOT_FOUND", "Bisect session not found.", 404)
        sha = self.git.validate_sha(sha)
        remaining = list(model.remaining_commits or [])
        if sha not in remaining:
            raise IngestionError(
                "BISECT_COMMIT_NOT_IN_RANGE",
                "Commit is not in the remaining bisect range.",
                422,
            )
        index = remaining.index(sha)
        classifications = dict(model.classifications or {})
        classifications[sha] = result
        if result == "good":
            remaining = remaining[index + 1 :]
            model.good_commit_sha = sha
        elif result == "bad":
            remaining = remaining[: index + 1]
            model.bad_commit_sha = sha
        else:
            remaining = [item for item in remaining if item != sha]
        model.classifications = classifications
        model.remaining_commits = remaining
        model.remaining_commit_count = len(remaining)
        model.current_candidate_sha = remaining[(len(remaining) - 1) // 2] if remaining else None
        model.status = "complete" if len(remaining) <= 1 else "active"
        self.session.commit()
        return self._bisect_read(model)

    @staticmethod
    def _bisect_read(model: BisectSession) -> dict[str, Any]:
        return {
            "id": model.id,
            "repository_id": model.repository_id,
            "known_good": model.good_commit_sha,
            "known_bad": model.bad_commit_sha,
            "current_candidate": model.current_candidate_sha,
            "remaining_commits": model.remaining_commits,
            "remaining_commit_count": model.remaining_commit_count,
            "classifications": model.classifications,
            "status": model.status,
            "updated_at": model.updated_at,
            "notice": "This is a manual static bisect assistant; no repository code was executed.",
        }

    def changed_files(self, repository_id: UUID, shas: list[str]) -> dict[str, list[str]]:
        rows = self.session.execute(
            select(Commit.sha, FileChange.old_path, FileChange.new_path)
            .join(FileChange, FileChange.commit_id == Commit.id)
            .where(Commit.repository_id == repository_id, Commit.sha.in_(shas))
        )
        result: dict[str, list[str]] = {sha: [] for sha in shas}
        for sha, old_path, new_path in rows:
            result.setdefault(sha, []).append(new_path or old_path or "")
        return {key: sorted(set(value)) for key, value in result.items()}
