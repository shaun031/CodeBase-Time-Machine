import re
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import (
    AIIndexState,
    CodeSymbol,
    Commit,
    CommitPRLink,
    EvidenceDocument,
    EvidenceEmbedding,
    GitHubIssue,
    GitHubIssueReference,
    GitHubPRCommit,
    GitHubPullRequest,
    Repository,
    RepositoryFile,
    SymbolChangeEvent,
    SymbolLineage,
)
from app.schemas.ai import AskRequest, EvidenceRead
from app.services.ai.evidence import is_sensitive_path
from app.services.ai.ollama import OllamaService
from app.services.git import GitService


@dataclass
class ResolvedTarget:
    lineage_id: UUID | None = None
    symbol_id: UUID | None = None
    file_path: str | None = None
    commit_shas: set[str] = field(default_factory=set)
    pull_request_numbers: set[int] = field(default_factory=set)
    issue_numbers: set[int] = field(default_factory=set)
    symbol_name: str | None = None
    introduction_sha: str | None = None
    debug: dict[str, Any] = field(default_factory=dict)


def evidence_url(repository_id: UUID, document: EvidenceDocument) -> str | None:
    root = f"/repos/{repository_id}"
    if document.symbol_lineage_id:
        return f"{root}/history/symbols/{document.symbol_lineage_id}"
    if document.pull_request_number:
        return f"{root}/pull-requests/{document.pull_request_number}"
    if document.issue_number:
        return f"{root}/issues/{document.issue_number}"
    if document.commit_sha:
        return f"{root}/commits/{document.commit_sha}"
    if document.file_path:
        return f"{root}/code?path={document.file_path}"
    if document.evidence_type in {"dependency_context", "architecture_component", "impact_context"}:
        return f"{root}/architecture"
    return None


def as_evidence(
    repository_id: UUID,
    document: EvidenceDocument,
    score: float,
    relationship: str,
    reason: str,
) -> EvidenceRead:
    return EvidenceRead(
        id=str(document.id),
        type=document.evidence_type,
        title=document.title,
        text=document.content,
        source_id=str(document.source_id) if document.source_id else None,
        source_url=evidence_url(repository_id, document),
        commit_sha=document.commit_sha,
        file_path=document.file_path,
        symbol_lineage_id=str(document.symbol_lineage_id) if document.symbol_lineage_id else None,
        pr_number=document.pull_request_number,
        issue_number=document.issue_number,
        score=max(0.0, min(1.0, score)),
        relationship=relationship,
        retrieval_reason=reason,
        metadata=document.metadata_json or {},
    )


class EvidenceRetriever:
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        ollama: OllamaService | None = None,
        git: GitService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.ollama = ollama or OllamaService(self.settings)
        self.git = git or GitService(self.settings)

    def resolve_target(self, repository_id: UUID, request: AskRequest) -> ResolvedTarget:
        requested_path = GitService.validate_path(request.file_path) if request.file_path else None
        target = ResolvedTarget(
            lineage_id=request.lineage_id,
            symbol_id=request.symbol_id,
            file_path=requested_path,
            commit_shas=set(),
            pull_request_numbers={request.pull_request_number}
            if request.pull_request_number
            else set(),
            issue_numbers={request.issue_number} if request.issue_number else set(),
        )
        question = request.question
        if not target.pull_request_numbers:
            pr_match = re.search(r"(?:\bpr\b|pull request)\s*#?(\d+)", question, re.I)
            if pr_match:
                target.pull_request_numbers.add(int(pr_match.group(1)))
        if not target.issue_numbers:
            issue_match = re.search(r"\bissue\s*#?(\d+)", question, re.I)
            if issue_match:
                target.issue_numbers.add(int(issue_match.group(1)))
        raw_sha = request.commit_sha
        if raw_sha is None:
            sha_match = re.search(r"\b[0-9a-f]{7,40}\b", question, re.I)
            raw_sha = sha_match.group(0) if sha_match else None
        if raw_sha:
            matches = list(
                self.session.scalars(
                    select(Commit.sha)
                    .where(
                        Commit.repository_id == repository_id,
                        Commit.sha.ilike(f"{raw_sha.lower()}%"),
                    )
                    .limit(2)
                )
            )
            if len(matches) == 1:
                target.commit_shas.add(matches[0])
        if request.symbol_id:
            symbol = self.session.scalar(
                select(CodeSymbol).where(
                    CodeSymbol.repository_id == repository_id, CodeSymbol.id == request.symbol_id
                )
            )
            if symbol:
                target.lineage_id = target.lineage_id or symbol.lineage_id
                target.symbol_name = symbol.qualified_name
                file = self.session.get(RepositoryFile, symbol.file_id)
                target.file_path = target.file_path or (file.path if file else None)
        if not target.lineage_id and not target.symbol_id:
            identifiers = list(
                dict.fromkeys(re.findall(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", question))
            )
            ignored = {"what", "which", "where", "when", "does", "this", "that", "explain", "why"}
            likely = [
                value
                for value in identifiers
                if value.lower() not in ignored
                and ("." in value or "_" in value or value[:1].isupper())
            ]
            for identifier in reversed(likely[-6:]):
                symbols = list(
                    self.session.scalars(
                        select(CodeSymbol)
                        .where(
                            CodeSymbol.repository_id == repository_id,
                            or_(
                                func.lower(CodeSymbol.name) == identifier.lower(),
                                func.lower(CodeSymbol.qualified_name) == identifier.lower(),
                            ),
                        )
                        .limit(2)
                    )
                )
                if len(symbols) == 1:
                    symbol = symbols[0]
                    target.symbol_id = symbol.id
                    target.lineage_id = symbol.lineage_id
                    target.symbol_name = symbol.qualified_name
                    file = self.session.get(RepositoryFile, symbol.file_id)
                    target.file_path = target.file_path or (file.path if file else None)
                    break
        if request.file_path and request.start_line:
            containing = self.session.scalar(
                select(CodeSymbol)
                .join(RepositoryFile, RepositoryFile.id == CodeSymbol.file_id)
                .where(
                    CodeSymbol.repository_id == repository_id,
                    RepositoryFile.path == request.file_path,
                    CodeSymbol.start_line <= request.start_line,
                    CodeSymbol.end_line >= (request.end_line or request.start_line),
                )
                .order_by((CodeSymbol.end_line - CodeSymbol.start_line).asc())
            )
            if containing:
                target.symbol_id = containing.id
                target.lineage_id = target.lineage_id or containing.lineage_id
                target.symbol_name = containing.qualified_name
        if target.lineage_id:
            lineage = self.session.scalar(
                select(SymbolLineage).where(
                    SymbolLineage.repository_id == repository_id,
                    SymbolLineage.id == target.lineage_id,
                )
            )
            if lineage:
                target.symbol_name = (
                    target.symbol_name or lineage.current_qualified_name or lineage.current_name
                )
                target.file_path = target.file_path or lineage.current_file_path
                events = list(
                    self.session.scalars(
                        select(SymbolChangeEvent).where(
                            SymbolChangeEvent.repository_id == repository_id,
                            SymbolChangeEvent.lineage_id == lineage.id,
                        )
                    )
                )
                commit_ids = {event.commit_id for event in events}
                if lineage.introduced_commit_id:
                    commit_ids.add(lineage.introduced_commit_id)
                    introduced = self.session.get(Commit, lineage.introduced_commit_id)
                    target.introduction_sha = introduced.sha if introduced else None
                if commit_ids:
                    target.commit_shas.update(
                        self.session.scalars(
                            select(Commit.sha).where(
                                Commit.repository_id == repository_id, Commit.id.in_(commit_ids)
                            )
                        )
                    )
        if target.file_path and request.start_line and not is_sensitive_path(target.file_path):
            repository = self.session.get(Repository, repository_id)
            if repository and repository.head_sha and self.git.storage.path(repository_id).exists():
                try:
                    blame = self.git.get_blame(
                        self.git.storage.path(repository_id),
                        repository.head_sha,
                        target.file_path,
                        request.start_line,
                        request.end_line or request.start_line,
                    )
                    target.commit_shas.update(item.commit_sha for item in blame)
                    target.debug["blame"] = [
                        {"line": item.line, "commit_sha": item.commit_sha, "author": item.author}
                        for item in blame
                    ]
                except Exception:
                    target.debug["blame"] = []
        self._expand_relationships(repository_id, target)
        target.debug.update(
            {
                "lineage_id": str(target.lineage_id) if target.lineage_id else None,
                "symbol_name": target.symbol_name,
                "introduction_sha": target.introduction_sha,
                "file_path": target.file_path,
                "commit_shas": sorted(target.commit_shas),
                "pull_request_numbers": sorted(target.pull_request_numbers),
                "issue_numbers": sorted(target.issue_numbers),
            }
        )
        return target

    def _expand_relationships(self, repository_id: UUID, target: ResolvedTarget) -> None:
        commit_ids: set[UUID] = set()
        if target.commit_shas:
            commit_ids.update(
                self.session.scalars(
                    select(Commit.id).where(
                        Commit.repository_id == repository_id, Commit.sha.in_(target.commit_shas)
                    )
                )
            )
        pr_ids: set[UUID] = set()
        if target.issue_numbers:
            issue_ids = set(
                self.session.scalars(
                    select(GitHubIssue.id).where(
                        GitHubIssue.repository_id == repository_id,
                        GitHubIssue.number.in_(target.issue_numbers),
                    )
                )
            )
            if issue_ids:
                pr_ids.update(
                    self.session.scalars(
                        select(GitHubIssueReference.source_id).where(
                            GitHubIssueReference.repository_id == repository_id,
                            GitHubIssueReference.target_issue_id.in_(issue_ids),
                            GitHubIssueReference.source_type == "pull_request",
                        )
                    )
                )
        if commit_ids:
            pr_ids.update(
                self.session.scalars(
                    select(CommitPRLink.pull_request_id).where(
                        CommitPRLink.repository_id == repository_id,
                        CommitPRLink.commit_id.in_(commit_ids),
                    )
                )
            )
        if target.commit_shas:
            pr_ids.update(
                self.session.scalars(
                    select(GitHubPRCommit.pull_request_id).where(
                        GitHubPRCommit.repository_id == repository_id,
                        GitHubPRCommit.commit_sha.in_(target.commit_shas),
                    )
                )
            )
        if target.pull_request_numbers:
            pr_ids.update(
                self.session.scalars(
                    select(GitHubPullRequest.id).where(
                        GitHubPullRequest.repository_id == repository_id,
                        GitHubPullRequest.number.in_(target.pull_request_numbers),
                    )
                )
            )
        if pr_ids:
            target.pull_request_numbers.update(
                self.session.scalars(
                    select(GitHubPullRequest.number).where(
                        GitHubPullRequest.repository_id == repository_id,
                        GitHubPullRequest.id.in_(pr_ids),
                    )
                )
            )
            target.issue_numbers.update(
                self.session.scalars(
                    select(GitHubIssueReference.target_number).where(
                        GitHubIssueReference.repository_id == repository_id,
                        GitHubIssueReference.source_id.in_(pr_ids),
                        GitHubIssueReference.target_issue_id.is_not(None),
                    )
                )
            )
            target.commit_shas.update(
                self.session.scalars(
                    select(GitHubPRCommit.commit_sha).where(
                        GitHubPRCommit.repository_id == repository_id,
                        GitHubPRCommit.pull_request_id.in_(pr_ids),
                    )
                )
            )

    def _deterministic(self, repository_id: UUID, target: ResolvedTarget) -> list[EvidenceRead]:
        rows_by_id: dict[UUID, EvidenceDocument] = {}

        def collect(*conditions: Any, limit: int = 30) -> None:
            rows = self.session.scalars(
                select(EvidenceDocument)
                .where(EvidenceDocument.repository_id == repository_id, *conditions)
                .order_by(
                    EvidenceDocument.created_source_at.desc().nullslast(),
                    EvidenceDocument.id,
                )
                .limit(limit)
            )
            for row in rows:
                rows_by_id[row.id] = row

        if target.lineage_id:
            collect(EvidenceDocument.symbol_lineage_id == target.lineage_id)
        if target.commit_shas:
            collect(
                EvidenceDocument.commit_sha.in_(target.commit_shas),
                EvidenceDocument.evidence_type.in_(
                    {
                        "commit",
                        "commit_diff",
                        "pull_request",
                        "review_comment",
                        "pr_comment",
                        "issue_comment",
                    }
                ),
            )
        if target.pull_request_numbers:
            collect(EvidenceDocument.pull_request_number.in_(target.pull_request_numbers))
        if target.issue_numbers:
            collect(EvidenceDocument.issue_number.in_(target.issue_numbers))
        if target.file_path:
            collect(EvidenceDocument.file_path == target.file_path, limit=20)
        if not rows_by_id:
            return []

        candidates: list[EvidenceRead] = []
        for row in rows_by_id.values():
            same_lineage = bool(target.lineage_id and row.symbol_lineage_id == target.lineage_id)
            same_symbol = bool(
                target.symbol_id
                and row.source_id == target.symbol_id
                and row.evidence_type == "symbol_current"
            )
            same_commit = bool(row.commit_sha and row.commit_sha in target.commit_shas)
            same_pr = bool(
                row.pull_request_number and row.pull_request_number in target.pull_request_numbers
            )
            same_issue = bool(row.issue_number and row.issue_number in target.issue_numbers)
            same_file = bool(target.file_path and row.file_path == target.file_path)

            if same_symbol:
                score, reason = 1.0, "direct_selected_symbol"
            elif same_lineage:
                lineage_scores = {
                    "symbol_change": 0.99,
                    "symbol_version": 0.97,
                    "symbol_current": 0.98,
                }
                score = lineage_scores.get(row.evidence_type, 0.95)
                reason = f"direct_symbol_{row.evidence_type}"
            elif same_pr:
                score, reason = 0.94, "direct_pull_request_link"
            elif same_issue:
                score, reason = 0.93, "direct_issue_reference"
            elif same_commit and row.evidence_type == "commit":
                score, reason = 0.96, "direct_commit"
            elif same_commit and row.evidence_type == "commit_diff":
                score, reason = 0.95, "direct_commit_diff"
            elif same_commit:
                score, reason = 0.9, f"direct_commit_{row.evidence_type}"
            elif same_file:
                score, reason = 0.78, f"direct_file_{row.evidence_type}"
            else:
                score, reason = 0.7, f"direct_{row.evidence_type}"
            if (
                target.introduction_sha
                and row.commit_sha == target.introduction_sha
                and (same_lineage or row.evidence_type in {"commit", "commit_diff"})
            ):
                score = min(1.0, score + 0.01)
                reason = f"symbol_introduction+{reason}"
            candidates.append(as_evidence(repository_id, row, score, "direct", reason))
        candidates.sort(key=lambda item: (-item.score, item.title))
        counts: dict[str, int] = {}
        diverse: list[EvidenceRead] = []
        for candidate in candidates:
            type_count = counts.get(candidate.type, 0)
            if type_count >= 3:
                continue
            candidate.score = max(0.0, candidate.score - 0.03 * type_count)
            diverse.append(candidate)
            counts[candidate.type] = type_count + 1
        return sorted(diverse, key=lambda item: (-item.score, item.title))

    def _lexical(self, repository_id: UUID, question: str, top_k: int) -> list[EvidenceRead]:
        tokens = list(dict.fromkeys(re.findall(r"[A-Za-z_$][\w$.-]{2,}", question)))[:8]
        if not tokens:
            return []
        conditions = [
            or_(
                EvidenceDocument.title.ilike(f"%{token}%"),
                EvidenceDocument.content.ilike(f"%{token}%"),
            )
            for token in tokens
        ]
        rows = list(
            self.session.scalars(
                select(EvidenceDocument)
                .where(EvidenceDocument.repository_id == repository_id, or_(*conditions))
                .order_by(EvidenceDocument.created_source_at.desc().nullslast())
                .limit(top_k * 3)
            )
        )
        values = []
        for row in rows:
            haystack = f"{row.title}\n{row.content}".lower()
            matches = sum(1 for token in tokens if token.lower() in haystack)
            score = 0.35 + 0.25 * matches / len(tokens)
            values.append(as_evidence(repository_id, row, score, "lexical", "lexical_match"))
        return sorted(values, key=lambda item: (-item.score, item.title))[:top_k]

    def _vector(self, repository_id: UUID, question: str, top_k: int) -> list[EvidenceRead]:
        state = self.session.get(AIIndexState, repository_id)
        model = self.settings.ollama_embedding_model
        if (
            not state
            or state.status != "ready"
            or state.embedding_model != model
            or not state.embedding_dimension
        ):
            return []
        vector = self.ollama.embed([question])[0]
        if len(vector) != state.embedding_dimension:
            return []
        distance = EvidenceEmbedding.embedding.cosine_distance(vector)
        rows = self.session.execute(
            select(EvidenceDocument, distance.label("distance"))
            .join(EvidenceEmbedding, EvidenceEmbedding.evidence_document_id == EvidenceDocument.id)
            .where(
                EvidenceDocument.repository_id == repository_id,
                EvidenceEmbedding.repository_id == repository_id,
                EvidenceEmbedding.embedding_model == model,
                EvidenceEmbedding.embedding_dimension == len(vector),
            )
            .order_by(distance.asc())
            .limit(top_k)
        ).all()
        return [
            as_evidence(
                repository_id, row, max(0.0, 1.0 - float(dist)), "semantic", "semantic_similarity"
            )
            for row, dist in rows
        ]

    def retrieve(
        self, repository_id: UUID, request: AskRequest, *, top_k: int | None = None
    ) -> tuple[list[EvidenceRead], ResolvedTarget, dict[str, Any]]:
        started = time.perf_counter()
        limit = top_k or self.settings.rag_top_k_final
        target = self.resolve_target(repository_id, request)
        deterministic = self._deterministic(repository_id, target)
        lexical = self._lexical(
            repository_id, request.question, top_k or self.settings.rag_top_k_lexical
        )
        vector = self._vector(
            repository_id, request.question, top_k or self.settings.rag_top_k_vector
        )
        fused: dict[str, EvidenceRead] = {}
        for candidate in [*deterministic, *vector, *lexical]:
            current = fused.get(candidate.id)
            if current is None:
                fused[candidate.id] = candidate
            else:
                reasons = set(current.retrieval_reason.split("+"))
                reasons.add(candidate.retrieval_reason)
                current.retrieval_reason = "+".join(sorted(reasons))
                current.score = min(1.0, max(current.score, candidate.score) + 0.05)
                if current.relationship != "direct" and candidate.relationship == "direct":
                    current.relationship = "direct"
        ranked = sorted(
            fused.values(),
            key=lambda item: (item.relationship != "direct", -item.score, item.title),
        )[: max(limit, min(len(deterministic), 20))]
        diagnostics = {
            "resolved_target": target.debug,
            "deterministic_candidates": len(deterministic),
            "vector_candidates": len(vector),
            "lexical_candidates": len(lexical),
            "final_evidence": len(ranked),
            "query_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        return ranked, target, diagnostics
