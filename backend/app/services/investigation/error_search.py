import re
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AIIndexState,
    Commit,
    GitHubComment,
    GitHubIssue,
    GitHubPullRequest,
    Repository,
    RepositoryFile,
    SymbolVersion,
)
from app.schemas.ai import AskRequest
from app.services.ai.ollama import OllamaService
from app.services.ai.retrieval import EvidenceRetriever
from app.services.git import GitService


class ErrorSearchService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.git = GitService(settings)

    @staticmethod
    def _pattern(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    def search(self, repository_id: UUID, query: str | None) -> list[dict[str, Any]]:
        value = (query or "").strip()[:1000]
        if not value:
            return []
        pattern = self._pattern(value)
        limit = self.settings.max_investigation_candidates
        results: list[dict[str, Any]] = []
        commits = self.session.scalars(
            select(Commit)
            .where(
                Commit.repository_id == repository_id,
                Commit.message.ilike(pattern, escape="\\"),
            )
            .limit(limit)
        )
        results.extend(
            {
                "type": "commit",
                "match": "exact",
                "commit_sha": item.sha,
                "label": item.message[:300],
            }
            for item in commits
        )
        prs = self.session.scalars(
            select(GitHubPullRequest)
            .where(
                GitHubPullRequest.repository_id == repository_id,
                or_(
                    GitHubPullRequest.title.ilike(pattern, escape="\\"),
                    GitHubPullRequest.body.ilike(pattern, escape="\\"),
                ),
            )
            .limit(limit)
        )
        results.extend(
            {
                "type": "pull_request",
                "match": "exact",
                "number": item.number,
                "label": item.title,
                "url": item.html_url,
            }
            for item in prs
        )
        issues = self.session.scalars(
            select(GitHubIssue)
            .where(
                GitHubIssue.repository_id == repository_id,
                or_(
                    GitHubIssue.title.ilike(pattern, escape="\\"),
                    GitHubIssue.body.ilike(pattern, escape="\\"),
                ),
            )
            .limit(limit)
        )
        results.extend(
            {
                "type": "issue",
                "match": "exact",
                "number": item.number,
                "label": item.title,
                "url": item.html_url,
            }
            for item in issues
        )
        comments = self.session.scalars(
            select(GitHubComment)
            .where(
                GitHubComment.repository_id == repository_id,
                GitHubComment.body.ilike(pattern, escape="\\"),
            )
            .limit(limit)
        )
        results.extend(
            {
                "type": "comment",
                "match": "exact",
                "label": (item.body or "")[:300],
                "url": item.html_url,
            }
            for item in comments
        )
        versions = self.session.scalars(
            select(SymbolVersion)
            .where(
                SymbolVersion.repository_id == repository_id,
                SymbolVersion.source_text.ilike(pattern, escape="\\"),
            )
            .limit(limit)
        )
        results.extend(
            {
                "type": "historical_source",
                "match": "exact",
                "lineage_id": str(item.lineage_id),
                "path": item.file_path,
                "label": item.qualified_name,
            }
            for item in versions
        )
        repository = self.session.get(Repository, repository_id)
        if repository and repository.head_sha:
            tokens = [
                token
                for token in re.findall(r"[A-Za-z0-9_.$-]{3,}", value)
                if len(token) >= 3
            ]
            needle = value.lower()
            if tokens:
                indexed_files = self.session.scalars(
                    select(RepositoryFile)
                    .where(
                        RepositoryFile.repository_id == repository_id,
                        RepositoryFile.is_binary.is_(False),
                        RepositoryFile.size_bytes
                        <= self.settings.max_source_file_size_bytes,
                    )
                    .order_by(RepositoryFile.path)
                    .limit(self.settings.max_repository_files)
                )
                for entry in indexed_files:
                    if len(results) >= limit:
                        break
                    try:
                        source = self.git.get_blob(
                            self.git.storage.path(repository_id),
                            entry.blob_sha,
                            entry.size_bytes,
                        ).decode("utf-8", "replace")
                    except Exception:
                        continue
                    if needle in source.lower():
                        results.append(
                            {
                                "type": "current_source",
                                "match": "exact",
                                "path": entry.path,
                                "label": value[:300],
                            }
                        )
        state = self.session.get(AIIndexState, repository_id)
        if state and state.status == "ready" and OllamaService(self.settings).is_available():
            try:
                semantic, _, _ = EvidenceRetriever(
                    self.session, self.settings
                ).retrieve(
                    repository_id,
                    AskRequest(question=value),
                    top_k=min(10, limit),
                )
            except (IngestionError, ValueError):
                semantic = []
            for item in semantic:
                if "semantic_similarity" not in item.retrieval_reason:
                    continue
                results.append(
                    {
                        "type": item.type,
                        "match": "semantic",
                        "commit_sha": item.commit_sha,
                        "path": item.file_path,
                        "number": item.pr_number or item.issue_number,
                        "label": item.title,
                        "score": item.score,
                    }
                )
                if len(results) >= limit:
                    break
        return results[:limit]
