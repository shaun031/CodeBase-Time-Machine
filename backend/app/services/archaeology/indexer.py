import hashlib
import math
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AIAnswerCache,
    AnalysisJob,
    ArchaeologyMetric,
    ArchaeologySyncState,
    Commit,
    ContributorEntityMetric,
    CopyMoveCandidate,
    FileChange,
    FileLineage,
    FileVersion,
    JobStatus,
    Repository,
    RepositoryFile,
    SymbolChangeEvent,
    SymbolLineage,
    SymbolRewriteEvent,
    SymbolVersion,
)
from app.services.archaeology.similarity import changed_lines, code_similarity, normalized_tokens
from app.services.archaeology.volatility import temporal_scores
from app.services.git import GitService
from app.services.language_detector import LanguageDetector


def _identity(email: str) -> str:
    return hashlib.sha256(email.strip().casefold().encode()).hexdigest()


def _days(now: datetime, value: datetime | None) -> int:
    return max(0, (now - value).days) if value else 0


def _changed_line_total(left: str | None, right: str | None) -> int:
    added, deleted = changed_lines(left, right)
    return added + deleted


class ArchaeologyIndexService:
    """Materialize bounded metrics from existing Git, file, and symbol history."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.detector = LanguageDetector()

    @staticmethod
    def _state(session: Session, repository_id: UUID) -> ArchaeologySyncState:
        state = session.get(ArchaeologySyncState, repository_id)
        if state is None:
            state = ArchaeologySyncState(repository_id=repository_id)
            session.add(state)
            session.flush()
        return state

    @staticmethod
    def _progress(
        session: Session, state: ArchaeologySyncState, job: AnalysisJob, value: int, step: str
    ) -> None:
        state.progress = value
        state.current_step = step
        job.progress = value
        job.current_step = step
        session.commit()

    @staticmethod
    def _contributors(
        session: Session,
        repository_id: UUID,
        entity_type: str,
        entity_id: UUID,
        commits: list[tuple[Commit, int]],
        introduced_commit_id: UUID | None,
        now: datetime,
    ) -> int:
        grouped: dict[str, dict[str, Any]] = {}
        seen: set[UUID] = set()
        for commit, lines in sorted(commits, key=lambda item: item[0].committed_at):
            if commit.id in seen or commit.is_merge_commit:
                continue
            seen.add(commit.id)
            key = _identity(commit.author_email)
            row = grouped.setdefault(
                key,
                {
                    "name": commit.author_name,
                    "commits": 0,
                    "lines": 0,
                    "first": commit.committed_at,
                    "last": commit.committed_at,
                    "introduced": 0,
                },
            )
            row["commits"] += 1
            row["lines"] += max(lines, 0)
            row["last"] = max(row["last"], commit.committed_at)
            row["first"] = min(row["first"], commit.committed_at)
            row["introduced"] = int(row["introduced"] or commit.id == introduced_commit_id)
        if not grouped:
            return 0
        raw_scores: dict[str, float] = {}
        for key, row in grouped.items():
            recency = math.exp(-_days(now, row["last"]) / 365)
            # Explainable repository-history score: 65% touch frequency, 25% recency,
            # 10% introduction bonus, normalized among contributors to this entity.
            raw_scores[key] = row["commits"] * 0.65 + recency * 0.25 + row["introduced"] * 0.10
        score_total = sum(raw_scores.values()) or 1
        commit_total = sum(row["commits"] for row in grouped.values()) or 1
        for key, row in grouped.items():
            session.add(
                ContributorEntityMetric(
                    repository_id=repository_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    identity_key=key,
                    display_name=row["name"],
                    commit_count=row["commits"],
                    lines_changed=row["lines"],
                    first_activity=row["first"],
                    last_activity=row["last"],
                    knowledge_score=round(raw_scores[key] / score_total, 6),
                    contribution_share=round(row["commits"] / commit_total, 6),
                    introduced=row["introduced"],
                    metadata_json={
                        "formula": (
                            "normalized(0.65*touches + 0.25*exp(-days_since_change/365) "
                            "+ 0.10*introduced)"
                        )
                    },
                )
            )
        return len(grouped)

    def _line_age(
        self, repository_id: UUID, repository: Repository, path: str, now: datetime
    ) -> dict[str, Any]:
        if not repository.head_sha:
            return {}
        try:
            blame = GitService(self.settings).get_blame(
                Path(repository.local_path or ""), repository.head_sha, path, 1, None
            )
        except IngestionError:
            return {"line_age_limited": True}
        dates = [
            datetime.fromtimestamp(row.author_time, UTC) for row in blame if row.author_time > 0
        ]
        ages = [_days(now, value) for value in dates]
        return {
            "line_age_limited": len(blame) >= self.settings.max_blame_lines,
            "lines_sampled": len(ages),
            "oldest_line_date": min(dates).isoformat() if dates else None,
            "newest_line_date": max(dates).isoformat() if dates else None,
            "median_line_age_days": round(median(ages), 1) if ages else None,
            "average_line_age_days": round(mean(ages), 1) if ages else None,
        }

    def build(self, session: Session, repository_id: UUID, job_id: UUID) -> None:
        started = time.monotonic()
        now = datetime.now(UTC)
        repository = session.get(Repository, repository_id)
        job = session.get(AnalysisJob, job_id)
        if repository is None or job is None:
            raise IngestionError(
                "ARCHAEOLOGY_INDEX_FAILED", "Repository indexing job was not found.", 404
            )
        if repository.history_index_status != "ready":
            raise IngestionError(
                "ARCHAEOLOGY_NOT_INDEXED", "Historical indexing must finish first.", 409
            )
        state = self._state(session, repository_id)
        state.status, state.started_at, state.error, state.job_id = "indexing", now, None, job_id
        job.status, job.started_at = JobStatus.running, now
        self._progress(session, state, job, 5, "loading indexed history")
        try:
            session.execute(
                delete(ContributorEntityMetric).where(
                    ContributorEntityMetric.repository_id == repository_id
                )
            )
            session.execute(
                delete(CopyMoveCandidate).where(CopyMoveCandidate.repository_id == repository_id)
            )
            session.execute(
                delete(SymbolRewriteEvent).where(SymbolRewriteEvent.repository_id == repository_id)
            )
            session.execute(
                delete(ArchaeologyMetric).where(ArchaeologyMetric.repository_id == repository_id)
            )

            commits = {
                item.id: item
                for item in session.scalars(
                    select(Commit).where(Commit.repository_id == repository_id)
                ).all()
            }
            file_changes = session.scalars(
                select(FileChange).where(FileChange.repository_id == repository_id)
            ).all()
            current_files = session.scalars(
                select(RepositoryFile).where(RepositoryFile.repository_id == repository_id)
            ).all()
            current_by_path = {item.path: item for item in current_files}
            file_lineages = session.scalars(
                select(FileLineage)
                .where(FileLineage.repository_id == repository_id)
                .limit(self.settings.max_archaeology_files + 1)
            ).all()
            symbol_lineages = session.scalars(
                select(SymbolLineage)
                .where(SymbolLineage.repository_id == repository_id)
                .limit(self.settings.max_archaeology_symbols + 1)
            ).all()
            if (
                len(file_lineages) > self.settings.max_archaeology_files
                or len(symbol_lineages) > self.settings.max_archaeology_symbols
            ):
                raise IngestionError(
                    "ARCHAEOLOGY_LIMIT_REACHED",
                    "Repository exceeds configured archaeology limits.",
                    413,
                )
            self._progress(session, state, job, 15, "computing file provenance and age")

            for index, file_lineage in enumerate(file_lineages):
                file_versions = list(
                    session.scalars(
                        select(FileVersion).where(FileVersion.file_lineage_id == file_lineage.id)
                    ).all()
                )
                file_versions.sort(key=lambda row: commits[row.commit_id].committed_at)
                if not file_versions:
                    continue
                paths = list(dict.fromkeys(row.path for row in file_versions))
                if self.detector.detect(paths[-1]).excluded:
                    continue
                relevant = [
                    row for row in file_changes if row.old_path in paths or row.new_path in paths
                ]
                commit_lines = [
                    (commits[row.commit_id], (row.additions or 0) + (row.deletions or 0))
                    for row in relevant
                    if row.commit_id in commits
                ]
                non_merge = [item for item in commit_lines if not item[0].is_merge_commit]
                used = non_merge or commit_lines
                dates = [item[0].committed_at for item in used] or [
                    commits[row.commit_id].committed_at for row in file_versions
                ]
                introduced_commit = commits[file_versions[0].commit_id]
                last_commit = max(
                    (commits[row.commit_id] for row in file_versions),
                    key=lambda row: row.committed_at,
                )
                current = current_by_path.get(file_versions[-1].path)
                deleted_flag = file_versions[-1].change_type == "deleted" or current is None
                contributors = self._contributors(
                    session,
                    repository_id,
                    "file",
                    file_lineage.id,
                    used,
                    introduced_commit.id,
                    now,
                )
                recent = {
                    days: sum(value >= now - timedelta(days=days) for value in dates)
                    for days in (30, 90, 180)
                }
                changes_recent_window = sum(
                    value >= now - timedelta(days=self.settings.archaeology_recent_days)
                    for value in dates
                )
                changes = len({item[0].id for item in used})
                age = _days(now, introduced_commit.committed_at)
                elapsed = _days(now, last_commit.committed_at)
                scores = temporal_scores(
                    age_days=age,
                    days_since_change=elapsed,
                    changes_180d=changes_recent_window,
                    total_changes=changes,
                    rewrites=0,
                    contributors=contributors,
                    deleted=deleted_flag,
                )
                line_age = (
                    self._line_age(repository_id, repository, file_versions[-1].path, now)
                    if current
                    and current.line_count
                    and current.line_count <= self.settings.max_blame_lines
                    else {
                        "line_age_limited": bool(
                            current
                            and current.line_count
                            and current.line_count > self.settings.max_blame_lines
                        )
                    }
                )
                session.add(
                    ArchaeologyMetric(
                        repository_id=repository_id,
                        entity_type="file",
                        entity_id=file_lineage.id,
                        name=file_versions[-1].path.rsplit("/", 1)[-1],
                        path=file_versions[-1].path,
                        kind=file_versions[-1].language,
                        status="deleted" if deleted_flag else "current",
                        introduced_at=introduced_commit.committed_at,
                        last_modified_at=last_commit.committed_at,
                        change_count=changes,
                        churn=sum(lines for _, lines in used),
                        contributor_count=contributors,
                        rename_count=sum(row.change_type == "renamed" for row in relevant),
                        move_count=sum(
                            row.change_type == "renamed"
                            and row.old_path
                            and row.new_path
                            and row.old_path.rsplit("/", 1)[0] != row.new_path.rsplit("/", 1)[0]
                            for row in relevant
                        ),
                        rewrite_count=0,
                        volatility_score=scores.volatility,
                        stability_score=scores.stability,
                        classification=scores.classification,
                        metadata_json={
                            "file_lineage_id": str(file_lineage.id),
                            "current_file_id": str(current.id) if current else None,
                            "original_path": file_versions[0].path,
                            "current_path": file_versions[-1].path,
                            "paths": paths,
                            "introduced_commit_id": str(introduced_commit.id),
                            "introduced_commit_sha": introduced_commit.sha,
                            "last_commit_sha": last_commit.sha,
                            "age_days": age,
                            "days_since_last_change": elapsed,
                            "changes_last_30_days": recent[30],
                            "changes_last_90_days": recent[90],
                            "changes_last_180_days": recent[180],
                            "recent_window_days": self.settings.archaeology_recent_days,
                            "changes_recent_window": changes_recent_window,
                            "lines_added": sum(
                                row.additions or 0
                                for row in relevant
                                if not commits[row.commit_id].is_merge_commit
                            ),
                            "lines_deleted": sum(
                                row.deletions or 0
                                for row in relevant
                                if not commits[row.commit_id].is_merge_commit
                            ),
                            **line_age,
                        },
                    )
                )
                if (
                    index % 100 == 0
                    and time.monotonic() - started > self.settings.max_archaeology_build_seconds
                ):
                    raise IngestionError(
                        "ARCHAEOLOGY_LIMIT_REACHED",
                        "Archaeology indexing exceeded its time limit.",
                        413,
                    )

            self._progress(session, state, job, 40, "detecting symbol rewrites")
            all_versions: dict[UUID, list[SymbolVersion]] = {}
            rewrite_counts: dict[UUID, int] = defaultdict(int)
            comparisons = 0
            for symbol_lineage in symbol_lineages:
                symbol_versions = list(
                    session.scalars(
                        select(SymbolVersion).where(SymbolVersion.lineage_id == symbol_lineage.id)
                    ).all()
                )
                symbol_versions.sort(key=lambda row: commits[row.commit_id].committed_at)
                all_versions[symbol_lineage.id] = symbol_versions
                for old, new in zip(symbol_versions, symbol_versions[1:], strict=False):
                    comparisons += 1
                    if comparisons > self.settings.max_rewrite_comparisons:
                        raise IngestionError(
                            "ARCHAEOLOGY_LIMIT_REACHED", "Rewrite comparison limit reached.", 413
                        )
                    similarity = code_similarity(old.source_text, new.source_text)
                    added, removed = changed_lines(old.source_text, new.source_text)
                    meaningful = (
                        max(
                            len(normalized_tokens(old.source_text)),
                            len(normalized_tokens(new.source_text)),
                        )
                        >= 8
                    )
                    large_replacement = added + removed >= max(
                        4,
                        int(
                            max(
                                old.end_line - old.start_line + 1, new.end_line - new.start_line + 1
                            )
                            * 0.4
                        ),
                    )
                    if (
                        meaningful
                        and large_replacement
                        and similarity < self.settings.symbol_rewrite_similarity_threshold
                    ):
                        reason = (
                            f"Token similarity {similarity:.2f} is below configured threshold "
                            f"{self.settings.symbol_rewrite_similarity_threshold:.2f}; "
                            f"{added + removed} lines changed."
                        )
                        session.add(
                            SymbolRewriteEvent(
                                repository_id=repository_id,
                                lineage_id=symbol_lineage.id,
                                old_version_id=old.id,
                                new_version_id=new.id,
                                commit_id=new.commit_id,
                                similarity=similarity,
                                lines_added=added,
                                lines_deleted=removed,
                                reason=reason,
                                evidence={
                                    "old_structure_hash": old.structure_hash,
                                    "new_structure_hash": new.structure_hash,
                                    "signature_changed": old.signature_hash != new.signature_hash,
                                    "threshold": self.settings.symbol_rewrite_similarity_threshold,
                                },
                            )
                        )
                        rewrite_counts[symbol_lineage.id] += 1

            self._progress(session, state, job, 55, "computing symbol churn and contributors")
            events_by_lineage: dict[UUID, list[SymbolChangeEvent]] = defaultdict(list)
            for event in session.scalars(
                select(SymbolChangeEvent).where(SymbolChangeEvent.repository_id == repository_id)
            ).all():
                events_by_lineage[event.lineage_id].append(event)
            for symbol_lineage in symbol_lineages:
                symbol_versions = all_versions[symbol_lineage.id]
                if not symbol_versions:
                    continue
                version_commits = [
                    (
                        commits[row.commit_id],
                        _changed_line_total(previous.source_text, row.source_text),
                    )
                    for previous, row in zip(symbol_versions, symbol_versions[1:], strict=False)
                ]
                version_commits.insert(
                    0,
                    (
                        commits[symbol_versions[0].commit_id],
                        max(
                            0,
                            symbol_versions[0].end_line - symbol_versions[0].start_line + 1,
                        ),
                    ),
                )
                introduced_commit = commits[symbol_versions[0].commit_id]
                last_commit = commits[symbol_versions[-1].commit_id]
                contributors = self._contributors(
                    session,
                    repository_id,
                    "symbol",
                    symbol_lineage.id,
                    version_commits,
                    introduced_commit.id,
                    now,
                )
                event_types = [row.event_type for row in events_by_lineage[symbol_lineage.id]]
                dates = [
                    commit.committed_at
                    for commit, _ in version_commits
                    if not commit.is_merge_commit
                ] or [commit.committed_at for commit, _ in version_commits]
                recent = {
                    days: sum(value >= now - timedelta(days=days) for value in dates)
                    for days in (30, 90, 180)
                }
                changes_recent_window = sum(
                    value >= now - timedelta(days=self.settings.archaeology_recent_days)
                    for value in dates
                )
                changes = len(
                    {commit.id for commit, _ in version_commits if not commit.is_merge_commit}
                ) or len({commit.id for commit, _ in version_commits})
                age, elapsed = (
                    _days(now, introduced_commit.committed_at),
                    _days(now, last_commit.committed_at),
                )
                scores = temporal_scores(
                    age_days=age,
                    days_since_change=elapsed,
                    changes_180d=changes_recent_window,
                    total_changes=changes,
                    rewrites=rewrite_counts[symbol_lineage.id],
                    contributors=contributors,
                    deleted=symbol_lineage.is_deleted,
                )
                session.add(
                    ArchaeologyMetric(
                        repository_id=repository_id,
                        entity_type="symbol",
                        entity_id=symbol_lineage.id,
                        name=(
                            symbol_lineage.current_qualified_name
                            or symbol_versions[-1].qualified_name
                        ),
                        path=(symbol_lineage.current_file_path or symbol_versions[-1].file_path),
                        kind=symbol_lineage.symbol_kind,
                        status="deleted" if symbol_lineage.is_deleted else "current",
                        introduced_at=introduced_commit.committed_at,
                        last_modified_at=last_commit.committed_at,
                        change_count=changes,
                        churn=sum(lines for _, lines in version_commits),
                        contributor_count=contributors,
                        rename_count=sum("renamed" in value for value in event_types),
                        move_count=sum("moved" in value for value in event_types),
                        rewrite_count=rewrite_counts[symbol_lineage.id],
                        volatility_score=scores.volatility,
                        stability_score=scores.stability,
                        classification=scores.classification,
                        metadata_json={
                            "lineage_id": str(symbol_lineage.id),
                            "original_name": symbol_versions[0].qualified_name,
                            "original_path": symbol_versions[0].file_path,
                            "current_name": symbol_lineage.current_qualified_name,
                            "current_path": symbol_lineage.current_file_path,
                            "historical_names": list(
                                dict.fromkeys(row.qualified_name for row in symbol_versions)
                            ),
                            "historical_paths": list(
                                dict.fromkeys(row.file_path for row in symbol_versions)
                            ),
                            "introduced_commit_id": str(introduced_commit.id),
                            "introduced_commit_sha": introduced_commit.sha,
                            "last_commit_sha": last_commit.sha,
                            "age_days": age,
                            "days_since_last_change": elapsed,
                            "changes_last_30_days": recent[30],
                            "changes_last_90_days": recent[90],
                            "changes_last_180_days": recent[180],
                            "recent_window_days": self.settings.archaeology_recent_days,
                            "changes_recent_window": changes_recent_window,
                            "body_change_count": sum(
                                old.body_hash != new.body_hash
                                for old, new in zip(
                                    symbol_versions, symbol_versions[1:], strict=False
                                )
                            ),
                            "signature_change_count": sum(
                                old.signature_hash != new.signature_hash
                                for old, new in zip(
                                    symbol_versions, symbol_versions[1:], strict=False
                                )
                            ),
                            "documentation_change_count": sum(
                                old.documentation != new.documentation
                                and old.body_hash == new.body_hash
                                for old, new in zip(
                                    symbol_versions, symbol_versions[1:], strict=False
                                )
                            ),
                        },
                    )
                )

            self._progress(session, state, job, 75, "detecting related copied or moved code")
            first_versions = [
                rows[0] for rows in all_versions.values() if rows and rows[0].source_text
            ]
            historical_versions = [
                version for rows in all_versions.values() for version in rows if version.source_text
            ]
            buckets: dict[tuple[str | None, str, int], list[SymbolVersion]] = defaultdict(list)
            for version in historical_versions:
                size_bucket = max(1, len(normalized_tokens(version.source_text)) // 10)
                buckets[(version.language, version.kind, size_bucket)].append(version)
            for versions in buckets.values():
                versions.sort(
                    key=lambda version: commits[version.commit_id].committed_at,
                    reverse=True,
                )
            candidate_count = 0
            for target in first_versions:
                target_size = max(1, len(normalized_tokens(target.source_text)))
                bucket = max(1, target_size // 10)
                compared = 0
                comparison_limit = self.settings.max_copy_candidates_per_symbol * 20
                best_by_lineage: dict[UUID, tuple[SymbolVersion, float]] = {}
                for size_bucket in sorted({max(1, bucket - 1), bucket, bucket + 1}):
                    for source in buckets.get((target.language, target.kind, size_bucket), []):
                        if (
                            source.lineage_id == target.lineage_id
                            or commits[source.commit_id].committed_at
                            >= commits[target.commit_id].committed_at
                        ):
                            continue
                        if compared >= comparison_limit:
                            break
                        compared += 1
                        similarity = code_similarity(source.source_text, target.source_text)
                        if similarity < 0.80:
                            continue
                        existing = best_by_lineage.get(source.lineage_id)
                        if existing is None or similarity > existing[1]:
                            best_by_lineage[source.lineage_id] = (source, similarity)
                    if compared >= comparison_limit:
                        break
                ranked = sorted(
                    best_by_lineage.values(),
                    key=lambda item: (
                        item[1],
                        commits[item[0].commit_id].committed_at,
                    ),
                    reverse=True,
                )[: self.settings.max_copy_candidates_per_symbol]
                for source, similarity in ranked:
                    source_lineage = next(
                        row for row in symbol_lineages if row.id == source.lineage_id
                    )
                    disappeared = bool(
                        source_lineage.deleted_commit_id
                        and commits[source_lineage.deleted_commit_id].committed_at
                        <= commits[target.commit_id].committed_at
                    )
                    relationship = (
                        "known_move"
                        if similarity == 1 and disappeared
                        else "exact_copy"
                        if similarity == 1
                        else "probable_move"
                        if disappeared
                        else "probable_copy"
                    )
                    confidence = 1.0 if similarity == 1 else round(min(0.95, similarity), 4)
                    session.add(
                        CopyMoveCandidate(
                            repository_id=repository_id,
                            source_lineage_id=source.lineage_id,
                            target_lineage_id=target.lineage_id,
                            source_version_id=source.id,
                            target_version_id=target.id,
                            commit_id=target.commit_id,
                            relationship=relationship,
                            similarity=similarity,
                            confidence=confidence,
                            evidence={
                                "method": "normalized token sequence",
                                "source_path": source.file_path,
                                "target_path": target.file_path,
                                "source_disappeared_before_target": disappeared,
                            },
                        )
                    )
                    candidate_count += 1

            self._progress(session, state, job, 92, "finalizing archaeology index")
            session.execute(
                delete(AIAnswerCache).where(AIAnswerCache.repository_id == repository_id)
            )
            distinct_people = session.scalars(
                select(ContributorEntityMetric.identity_key)
                .where(ContributorEntityMetric.repository_id == repository_id)
                .distinct()
            ).all()
            state.status, state.progress, state.current_step = "ready", 100, "ready"
            state.files_processed = len(file_lineages)
            state.symbols_processed = len(symbol_lineages)
            state.rewrites_detected = sum(rewrite_counts.values())
            state.copy_candidates = candidate_count
            state.contributors = len(distinct_people)
            state.last_indexed_sha = repository.head_sha
            state.completed_at = datetime.now(UTC)
            job.status, job.progress, job.current_step = JobStatus.completed, 100, "ready"
            job.completed_at = state.completed_at
            session.commit()
        except Exception as exc:
            session.rollback()
            state = self._state(session, repository_id)
            job = session.get(AnalysisJob, job_id)
            state.status, state.error, state.completed_at = (
                "failed",
                str(exc)[:1000],
                datetime.now(UTC),
            )
            if job:
                job.status, job.error_message, job.completed_at = (
                    JobStatus.failed,
                    str(exc)[:1000],
                    state.completed_at,
                )
            session.commit()
            raise


def index_archaeology_repository(engine: Engine, repository_id: UUID, job_id: UUID) -> None:
    with Session(engine) as session:
        ArchaeologyIndexService().build(session, repository_id, job_id)
