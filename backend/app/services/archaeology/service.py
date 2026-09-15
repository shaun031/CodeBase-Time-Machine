import math
from collections import defaultdict
from datetime import UTC, datetime
from statistics import median
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    ArchaeologyMetric,
    ArchaeologySyncState,
    CodeSymbol,
    Commit,
    CommitPRLink,
    ContributorEntityMetric,
    CopyMoveCandidate,
    DependencyEdge,
    DependencyNode,
    FileChange,
    FileVersion,
    Repository,
    RepositoryFile,
    SymbolChangeEvent,
    SymbolLineage,
    SymbolRewriteEvent,
    SymbolVersion,
)
from app.schemas.archaeology import (
    ArchaeologyOverview,
    ArchaeologyStatus,
    ArchaeologyTarget,
    ContributorRead,
    ContributorResponse,
    DossierResponse,
    HistoricalSearchItem,
    HistoricalSearchResponse,
    ProvenanceResponse,
    RelatedCodeRead,
    RewriteRead,
    VolatilityResponse,
)
from app.services.archaeology.volatility import STABILITY_FORMULA, VOLATILITY_FORMULA
from app.services.repositories import get_repository


class ArchaeologyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()

    def _commit_time(self, commit_id: UUID) -> datetime:
        commit = self.session.get(Commit, commit_id)
        return commit.committed_at if commit else datetime.min.replace(tzinfo=UTC)

    def status(self, repository_id: UUID) -> ArchaeologyStatus:
        repository = get_repository(self.session, repository_id)
        state = self.session.get(ArchaeologySyncState, repository_id)
        if state is None:
            return ArchaeologyStatus(
                status="not_indexed",
                progress=None,
                step=None,
                files_processed=0,
                symbols_processed=0,
                rewrites_detected=0,
                copy_candidates=0,
                contributors=0,
                last_indexed_sha=None,
                stale=False,
                error=None,
                job_id=None,
                completed_at=None,
            )
        stale = (
            state.last_indexed_sha != repository.head_sha
            or repository.history_stale
            or repository.history_rewritten
        )
        status = "stale" if state.status == "ready" and stale else state.status
        return ArchaeologyStatus(
            status=status,
            progress=state.progress,
            step=state.current_step,
            files_processed=state.files_processed,
            symbols_processed=state.symbols_processed,
            rewrites_detected=state.rewrites_detected,
            copy_candidates=state.copy_candidates,
            contributors=state.contributors,
            last_indexed_sha=state.last_indexed_sha,
            stale=stale,
            error=state.error,
            job_id=state.job_id,
            completed_at=state.completed_at,
        )

    def _ready(self, repository_id: UUID) -> Repository:
        repository = get_repository(self.session, repository_id)
        status = self.status(repository_id)
        if status.status == "failed":
            raise IngestionError(
                "ARCHAEOLOGY_INDEX_FAILED", "Archaeology indexing failed. Reindex and retry.", 409
            )
        if status.stale:
            raise IngestionError(
                "ARCHAEOLOGY_STALE", "Archaeology data is stale. Reindex and retry.", 409
            )
        if status.status != "ready":
            raise IngestionError(
                "ARCHAEOLOGY_NOT_INDEXED", "Build the archaeology index first.", 409
            )
        return repository

    @staticmethod
    def _target(row: ArchaeologyMetric) -> ArchaeologyTarget:
        metadata = row.metadata_json or {}
        current_id = metadata.get("current_file_id")
        return ArchaeologyTarget(
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            current_file_id=UUID(current_id) if current_id else None,
            name=row.name,
            path=row.path,
            kind=row.kind,
            status=row.status,
            introduced_at=row.introduced_at,
            last_modified_at=row.last_modified_at,
            age_days=int(metadata.get("age_days", 0)),
            days_since_last_change=int(metadata.get("days_since_last_change", 0)),
            change_count=row.change_count,
            churn=row.churn,
            contributor_count=row.contributor_count,
            rename_count=row.rename_count,
            move_count=row.move_count,
            rewrite_count=row.rewrite_count,
            changes_last_30_days=int(metadata.get("changes_last_30_days", 0)),
            changes_last_90_days=int(metadata.get("changes_last_90_days", 0)),
            changes_last_180_days=int(metadata.get("changes_last_180_days", 0)),
            volatility=row.volatility_score,
            stability=row.stability_score,
            classification=row.classification,
            metadata=metadata,
        )

    def _metrics(
        self, repository_id: UUID, entity_type: str | None = None
    ) -> list[ArchaeologyMetric]:
        query = select(ArchaeologyMetric).where(ArchaeologyMetric.repository_id == repository_id)
        if entity_type:
            query = query.where(ArchaeologyMetric.entity_type == entity_type)
        return list(self.session.scalars(query).all())

    @staticmethod
    def _concentration(items: list[ContributorRead]) -> dict[str, Any]:
        counts = [max(item.commit_count, 0) for item in items]
        total = sum(counts)
        if not counts or not total:
            return {
                "top_contributor_share": None,
                "normalized_entropy": None,
                "label": "insufficient_data",
            }
        shares = [value / total for value in counts]
        entropy = -sum(value * math.log(value) for value in shares if value)
        normalized = entropy / math.log(len(shares)) if len(shares) > 1 else 0.0
        top = max(shares)
        label = "concentrated" if top >= 0.6 or normalized < 0.45 else "distributed"
        return {
            "top_contributor_share": round(top, 4),
            "normalized_entropy": round(normalized, 4),
            "label": label,
            "explanation": (
                "Concentrated means the top contributor has at least 60% of touches or "
                "normalized contributor entropy is below 0.45."
            ),
        }

    def overview(self, repository_id: UUID) -> ArchaeologyOverview:
        self._ready(repository_id)
        rows = self._metrics(repository_id)
        files, symbols = (
            [row for row in rows if row.entity_type == "file"],
            [row for row in rows if row.entity_type == "symbol"],
        )
        ages_f = [int((row.metadata_json or {}).get("age_days", 0)) for row in files]
        ages_s = [int((row.metadata_json or {}).get("age_days", 0)) for row in symbols]
        contributors = self.contributors(repository_id, "commits").items
        repository_age = max(ages_f + ages_s) if ages_f or ages_s else None
        buckets = {"under_90_days": 0, "90_to_365_days": 0, "1_to_3_years": 0, "over_3_years": 0}
        for age in ages_s:
            buckets[
                "under_90_days"
                if age < 90
                else "90_to_365_days"
                if age < 365
                else "1_to_3_years"
                if age < 1095
                else "over_3_years"
            ] += 1
        return ArchaeologyOverview(
            repository_age_days=repository_age,
            total_historical_files=len(files),
            current_files=sum(row.status == "current" for row in files),
            deleted_files=sum(row.status == "deleted" for row in files),
            current_symbols=sum(row.status == "current" for row in symbols),
            deleted_symbols=sum(row.status == "deleted" for row in symbols),
            renamed_symbols=sum(row.rename_count > 0 for row in symbols),
            moved_symbols=sum(row.move_count > 0 for row in symbols),
            major_rewrites=sum(row.rewrite_count for row in symbols),
            contributors=len(contributors),
            median_symbol_age_days=median(ages_s) if ages_s else None,
            median_file_age_days=median(ages_f) if ages_f else None,
            most_changed_files=[
                self._target(row)
                for row in sorted(
                    files, key=lambda item: (item.change_count, item.churn), reverse=True
                )[:10]
            ],
            oldest_current_symbols=[
                self._target(row)
                for row in sorted(
                    (row for row in symbols if row.status == "current"),
                    key=lambda item: item.introduced_at or datetime.max.replace(tzinfo=UTC),
                )[:10]
            ],
            recently_rewritten_symbols=[
                self._target(row)
                for row in sorted(
                    (row for row in symbols if row.rewrite_count),
                    key=lambda item: item.last_modified_at or datetime.min.replace(tzinfo=UTC),
                    reverse=True,
                )[:10]
            ],
            age_buckets=buckets,
            volatility_formula=VOLATILITY_FORMULA,
            stability_formula=STABILITY_FORMULA,
            canonical_date="Git committer date",
            merge_commit_policy=(
                "Merge commits are excluded from touch and churn metrics when non-merge "
                "evidence exists."
            ),
            knowledge_concentration=self._concentration(contributors),
        )

    def volatility(
        self, repository_id: UUID, level: Literal["file", "symbol"], sort: str, limit: int
    ) -> VolatilityResponse:
        self._ready(repository_id)
        allowed = {
            "volatility": lambda row: row.volatility_score,
            "stability": lambda row: row.stability_score,
            "changes": lambda row: row.change_count,
            "oldest": lambda row: (
                -(row.introduced_at.timestamp() if row.introduced_at else float("inf"))
            ),
            "newest": lambda row: row.introduced_at.timestamp() if row.introduced_at else 0,
        }
        if sort not in allowed:
            raise IngestionError(
                "INVALID_ARCHAEOLOGY_SORT", "Unsupported archaeology sort option.", 422
            )
        rows = sorted(self._metrics(repository_id, level), key=allowed[sort], reverse=True)[:limit]
        return VolatilityResponse(
            level=level,
            items=[self._target(row) for row in rows],
            volatility_formula=VOLATILITY_FORMULA,
            stability_formula=STABILITY_FORMULA,
        )

    def _resolve_metric(
        self,
        repository_id: UUID,
        *,
        file_id: UUID | None = None,
        symbol_id: UUID | None = None,
        lineage_id: UUID | None = None,
    ) -> ArchaeologyMetric:
        selected = sum(value is not None for value in (file_id, symbol_id, lineage_id))
        if selected != 1:
            raise IngestionError(
                "HISTORICAL_ENTITY_NOT_FOUND",
                "Specify exactly one file, symbol, or lineage target.",
                422,
            )
        entity_type, entity_id = "symbol", lineage_id
        if symbol_id:
            symbol = self.session.get(CodeSymbol, symbol_id)
            entity_id = (
                symbol.lineage_id if symbol and symbol.repository_id == repository_id else None
            )
        if file_id:
            file = self.session.get(RepositoryFile, file_id)
            entity_type = "file"
            if not file or file.repository_id != repository_id:
                historical = self.session.scalar(
                    select(ArchaeologyMetric).where(
                        ArchaeologyMetric.repository_id == repository_id,
                        ArchaeologyMetric.entity_type == "file",
                        ArchaeologyMetric.entity_id == file_id,
                    )
                )
                if historical:
                    return historical
                raise IngestionError(
                    "HISTORICAL_ENTITY_NOT_FOUND", "Historical target was not found.", 404
                )
            rows = self._metrics(repository_id, "file")
            match = next(
                (
                    row
                    for row in rows
                    if (row.metadata_json or {}).get("current_file_id") == str(file_id)
                ),
                None,
            )
            if match:
                return match
            entity_id = file_id
        row = (
            self.session.scalar(
                select(ArchaeologyMetric).where(
                    ArchaeologyMetric.repository_id == repository_id,
                    ArchaeologyMetric.entity_type == entity_type,
                    ArchaeologyMetric.entity_id == entity_id,
                )
            )
            if entity_id
            else None
        )
        if row is None:
            raise IngestionError(
                "HISTORICAL_ENTITY_NOT_FOUND", "Historical target was not found.", 404
            )
        return row

    def contributors_for_metric(
        self, repository_id: UUID, metric: ArchaeologyMetric
    ) -> ContributorResponse:
        rows = self.session.scalars(
            select(ContributorEntityMetric)
            .where(
                ContributorEntityMetric.repository_id == repository_id,
                ContributorEntityMetric.entity_type == metric.entity_type,
                ContributorEntityMetric.entity_id == metric.entity_id,
            )
            .order_by(ContributorEntityMetric.knowledge_score.desc())
        ).all()
        items = [
            ContributorRead(
                identity_key=row.identity_key,
                display_name=row.display_name,
                commit_count=row.commit_count,
                lines_changed=row.lines_changed,
                first_activity=row.first_activity,
                last_activity=row.last_activity,
                knowledge_score=row.knowledge_score,
                contribution_share=row.contribution_share,
                introduced=bool(row.introduced),
                evidence={
                    "formula": (row.metadata_json or {}).get("formula"),
                    "entity_id": str(metric.entity_id),
                },
            )
            for row in rows
        ]
        return ContributorResponse(
            items=items,
            concentration=self._concentration(items),
            interpretation=(
                "Scores describe contribution evidence in Git history, not legal ownership, "
                "job title, or code quality."
            ),
        )

    def contributors_for(
        self,
        repository_id: UUID,
        *,
        file_id: UUID | None,
        symbol_id: UUID | None,
        lineage_id: UUID | None,
    ) -> ContributorResponse:
        self._ready(repository_id)
        return self.contributors_for_metric(
            repository_id,
            self._resolve_metric(
                repository_id, file_id=file_id, symbol_id=symbol_id, lineage_id=lineage_id
            ),
        )

    def contributors(self, repository_id: UUID, sort: str) -> ContributorResponse:
        self._ready(repository_id)
        commits = self.session.scalars(
            select(Commit).where(
                Commit.repository_id == repository_id, Commit.is_merge_commit.is_(False)
            )
        ).all()
        file_changes = self.session.scalars(
            select(FileChange).where(FileChange.repository_id == repository_id)
        ).all()
        symbol_versions = self.session.scalars(
            select(SymbolVersion).where(SymbolVersion.repository_id == repository_id)
        ).all()
        by_commit_paths: dict[UUID, set[str]] = defaultdict(set)
        indexed_paths: set[str] = set()
        for metric in self._metrics(repository_id, "file"):
            metadata = metric.metadata_json or {}
            indexed_paths.update(str(path) for path in metadata.get("paths", []) if path)
        for file_change in file_changes:
            path = file_change.new_path or file_change.old_path
            if path in indexed_paths:
                by_commit_paths[file_change.commit_id].add(path)
        by_commit_symbols: dict[UUID, set[UUID]] = defaultdict(set)
        for symbol_version in symbol_versions:
            by_commit_symbols[symbol_version.commit_id].add(symbol_version.lineage_id)
        grouped: dict[str, dict[str, Any]] = {}
        import hashlib

        for commit in commits:
            key = hashlib.sha256(commit.author_email.strip().casefold().encode()).hexdigest()
            contributor = grouped.setdefault(
                key,
                {
                    "name": commit.author_name,
                    "commits": 0,
                    "files": set(),
                    "symbols": set(),
                    "first": commit.committed_at,
                    "last": commit.committed_at,
                },
            )
            contributor["commits"] += 1
            contributor["files"].update(by_commit_paths[commit.id])
            contributor["symbols"].update(by_commit_symbols[commit.id])
            contributor["first"] = min(contributor["first"], commit.committed_at)
            contributor["last"] = max(contributor["last"], commit.committed_at)
        items = [
            ContributorRead(
                identity_key=key,
                display_name=row["name"],
                commit_count=row["commits"],
                files_touched=len(row["files"]),
                symbols_touched=len(row["symbols"]),
                first_activity=row["first"],
                last_activity=row["last"],
            )
            for key, row in grouped.items()
        ]
        keys = {
            "commits": lambda item: item.commit_count,
            "files": lambda item: item.files_touched,
            "symbols": lambda item: item.symbols_touched,
            "recent": lambda item: item.last_activity.timestamp(),
        }
        if sort not in keys:
            raise IngestionError(
                "INVALID_ARCHAEOLOGY_SORT", "Unsupported contributor sort option.", 422
            )
        items.sort(key=keys[sort], reverse=True)
        return ContributorResponse(
            items=items,
            concentration=self._concentration(items),
            interpretation=(
                "Contributors are separated by hashed Git email; raw email addresses are not "
                "exposed. Merge commits are excluded."
            ),
        )

    def provenance(
        self,
        repository_id: UUID,
        *,
        file_id: UUID | None,
        symbol_id: UUID | None,
        lineage_id: UUID | None,
    ) -> ProvenanceResponse:
        self._ready(repository_id)
        metric = self._resolve_metric(
            repository_id, file_id=file_id, symbol_id=symbol_id, lineage_id=lineage_id
        )
        metadata = metric.metadata_json or {}
        timeline: list[dict[str, Any]] = []
        renames: list[dict[str, Any]] = []
        moves: list[dict[str, Any]] = []
        rewrites: list[dict[str, Any]] = []
        if metric.entity_type == "symbol":
            events = self.session.scalars(
                select(SymbolChangeEvent).where(SymbolChangeEvent.lineage_id == metric.entity_id)
            ).all()
            for event in events:
                commit = self.session.get(Commit, event.commit_id)
                version = (
                    self.session.get(SymbolVersion, event.new_version_id)
                    if event.new_version_id
                    else None
                )
                item = {
                    "event": event.event_type,
                    "commit_id": str(event.commit_id),
                    "commit_sha": commit.sha if commit else None,
                    "committed_at": commit.committed_at.isoformat() if commit else None,
                    "author": commit.author_name if commit else None,
                    "name": version.qualified_name if version else None,
                    "path": version.file_path if version else None,
                    "match_type": version.match_type if version else "exact",
                    "confidence": version.match_confidence if version else 1.0,
                    "evidence": version.matching_metadata if version else event.summary_data or {},
                }
                timeline.append(item)
                if "renamed" in event.event_type:
                    renames.append(item)
                if "moved" in event.event_type:
                    moves.append(item)
            for row in self.rewrite_rows(repository_id, lineage_id=metric.entity_id):
                item = row.model_dump(mode="json")
                item["event"] = "major_rewrite"
                timeline.append(item)
                rewrites.append(item)
        else:
            file_versions = list(
                self.session.scalars(
                    select(FileVersion).where(FileVersion.file_lineage_id == metric.entity_id)
                ).all()
            )
            file_versions.sort(key=lambda row: self._commit_time(row.commit_id))
            previous_path: str | None = None
            for file_version in file_versions:
                commit = self.session.get(Commit, file_version.commit_id)
                item = {
                    "event": file_version.change_type,
                    "commit_id": str(file_version.commit_id),
                    "commit_sha": commit.sha if commit else None,
                    "committed_at": commit.committed_at.isoformat() if commit else None,
                    "author": commit.author_name if commit else None,
                    "path": file_version.path,
                    "match_type": "git_file_history",
                    "confidence": 1.0,
                    "evidence": {
                        "blob_sha": file_version.blob_sha,
                        "previous_path": previous_path,
                    },
                }
                timeline.append(item)
                if file_version.change_type == "renamed":
                    renames.append(item)
                    if (
                        previous_path
                        and previous_path.rsplit("/", 1)[0] != file_version.path.rsplit("/", 1)[0]
                    ):
                        moves.append(item)
                previous_path = file_version.path
        timeline.sort(key=lambda row: row.get("committed_at") or "")
        contributors = self.contributors_for_metric(repository_id, metric).items
        return ProvenanceResponse(
            entity_type=metric.entity_type,
            entity_id=metric.entity_id,
            origin={
                "name": metadata.get("original_name") or metadata.get("original_path"),
                "path": metadata.get("original_path"),
                "commit_id": metadata.get("introduced_commit_id"),
                "commit_sha": metadata.get("introduced_commit_sha"),
                "introduced_at": metric.introduced_at.isoformat() if metric.introduced_at else None,
                "date_source": "committer date",
            },
            current_identity={"name": metric.name, "path": metric.path, "kind": metric.kind},
            status=metric.status,
            timeline=timeline,
            renames=renames,
            moves=moves,
            rewrites=rewrites,
            contributors=contributors,
        )

    def rewrite_rows(
        self,
        repository_id: UUID,
        *,
        lineage_id: UUID | None = None,
        file: str | None = None,
        symbol: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[RewriteRead]:
        query = select(SymbolRewriteEvent).where(SymbolRewriteEvent.repository_id == repository_id)
        if lineage_id:
            query = query.where(SymbolRewriteEvent.lineage_id == lineage_id)
        result: list[RewriteRead] = []
        for row in self.session.scalars(query).all():
            commit = self.session.get(Commit, row.commit_id)
            version = self.session.get(SymbolVersion, row.new_version_id)
            if (
                not commit
                or not version
                or (file and file.casefold() not in version.file_path.casefold())
                or (symbol and symbol.casefold() not in version.qualified_name.casefold())
                or (from_date and commit.committed_at < from_date)
                or (to_date and commit.committed_at > to_date)
            ):
                continue
            result.append(
                RewriteRead(
                    id=row.id,
                    lineage_id=row.lineage_id,
                    symbol=version.qualified_name,
                    file_path=version.file_path,
                    commit_id=commit.id,
                    commit_sha=commit.sha,
                    committed_at=commit.committed_at,
                    similarity=row.similarity,
                    lines_added=row.lines_added,
                    lines_deleted=row.lines_deleted,
                    reason=row.reason,
                    evidence=row.evidence,
                    old_version_id=row.old_version_id,
                    new_version_id=row.new_version_id,
                )
            )
        return sorted(result, key=lambda item: item.committed_at, reverse=True)

    def rewrites(self, repository_id: UUID, **filters: Any) -> list[RewriteRead]:
        self._ready(repository_id)
        return self.rewrite_rows(repository_id, **filters)

    def related_code(
        self,
        repository_id: UUID,
        lineage_id: UUID,
        min_similarity: float,
        include_deleted: bool,
        include_historical: bool,
    ) -> list[RelatedCodeRead]:
        self._ready(repository_id)
        del include_historical
        rows = self.session.scalars(
            select(CopyMoveCandidate).where(
                CopyMoveCandidate.repository_id == repository_id,
                or_(
                    CopyMoveCandidate.source_lineage_id == lineage_id,
                    CopyMoveCandidate.target_lineage_id == lineage_id,
                ),
                CopyMoveCandidate.similarity >= min_similarity,
            )
        ).all()
        result = []
        for row in rows:
            candidate_id = (
                row.target_lineage_id
                if row.source_lineage_id == lineage_id
                else row.source_lineage_id
            )
            candidate = self.session.get(SymbolLineage, candidate_id)
            commit = self.session.get(Commit, row.commit_id)
            if not candidate or not commit or (candidate.is_deleted and not include_deleted):
                continue
            result.append(
                RelatedCodeRead(
                    candidate_lineage_id=candidate.id,
                    candidate_name=candidate.current_qualified_name
                    or candidate.current_name
                    or "Deleted symbol",
                    candidate_path=candidate.current_file_path or "Historical path",
                    commit_sha=commit.sha,
                    similarity=row.similarity,
                    relationship=row.relationship,
                    confidence=row.confidence,
                    evidence=row.evidence,
                    status="deleted" if candidate.is_deleted else "current",
                )
            )
        return result

    def search(
        self,
        repository_id: UUID,
        q: str,
        entity_type: str,
        status: str,
        from_date: datetime | None,
        to_date: datetime | None,
        page: int,
        page_size: int,
    ) -> HistoricalSearchResponse:
        self._ready(repository_id)
        needle = q.strip().casefold()
        results: list[HistoricalSearchItem] = []
        for metric in self._metrics(repository_id):
            type_matches = entity_type in {"all", metric.entity_type} or (
                entity_type == f"deleted_{metric.entity_type}" and metric.status == "deleted"
            )
            if not type_matches or status not in {"all", metric.status}:
                continue
            metadata = metric.metadata_json or {}
            names = metadata.get("historical_names", [metric.name])
            paths = metadata.get("historical_paths") or metadata.get("paths") or [metric.path]
            candidates = [(str(value), "historical name") for value in names] + [
                (str(value), "historical file path") for value in paths if value
            ]
            matches = [
                (value, reason) for value, reason in candidates if needle in value.casefold()
            ]
            if not matches:
                continue
            value, reason = matches[0]
            if (from_date and metric.last_modified_at and metric.last_modified_at < from_date) or (
                to_date and metric.introduced_at and metric.introduced_at > to_date
            ):
                continue
            results.append(
                HistoricalSearchItem(
                    entity_type=metric.entity_type,
                    entity_id=metric.entity_id,
                    name=metric.name,
                    historical_name=value if value != metric.name else None,
                    kind=metric.kind,
                    file_path=metric.path,
                    commit_sha=metadata.get("last_commit_sha"),
                    commit_id=UUID(metadata["introduced_commit_id"])
                    if metadata.get("introduced_commit_id")
                    else None,
                    status=metric.status,
                    lineage_id=metric.entity_id if metric.entity_type == "symbol" else None,
                    version_id=None,
                    matched_reason=reason,
                    match_type="exact" if value.casefold() == needle else "lexical",
                    source_available=metric.entity_type == "symbol",
                )
            )
        if entity_type in {"all", "symbol", "deleted_symbol"}:
            query = (
                select(SymbolVersion)
                .where(
                    SymbolVersion.repository_id == repository_id,
                    or_(
                        func.lower(SymbolVersion.name).contains(needle),
                        func.lower(SymbolVersion.qualified_name).contains(needle),
                        func.lower(SymbolVersion.source_text).contains(needle),
                    ),
                )
                .limit(self.settings.max_archaeology_search_results)
            )
            known = {(item.lineage_id, item.historical_name or item.name) for item in results}
            for version in self.session.scalars(query).all():
                lineage = self.session.get(SymbolLineage, version.lineage_id)
                commit = self.session.get(Commit, version.commit_id)
                if (
                    not lineage
                    or not commit
                    or (entity_type == "deleted_symbol" and not lineage.is_deleted)
                    or (
                        status != "all"
                        and status != ("deleted" if lineage.is_deleted else "current")
                    )
                    or (from_date and commit.committed_at < from_date)
                    or (to_date and commit.committed_at > to_date)
                    or (version.lineage_id, version.qualified_name) in known
                ):
                    continue
                reason = (
                    "historical source"
                    if version.source_text and needle in version.source_text.casefold()
                    else "historical name"
                )
                results.append(
                    HistoricalSearchItem(
                        entity_type="symbol",
                        entity_id=version.lineage_id,
                        name=lineage.current_qualified_name or version.qualified_name,
                        historical_name=version.qualified_name,
                        kind=version.kind,
                        file_path=version.file_path,
                        commit_sha=commit.sha,
                        commit_id=commit.id,
                        status="deleted" if lineage.is_deleted else "current",
                        lineage_id=version.lineage_id,
                        version_id=version.id,
                        matched_reason=reason,
                        match_type="exact"
                        if version.qualified_name.casefold() == needle
                        else "lexical",
                        source_available=bool(version.source_text),
                    )
                )
        if entity_type == "all" and status == "all":
            commit_query = (
                select(Commit)
                .where(
                    Commit.repository_id == repository_id,
                    func.lower(Commit.message).contains(needle),
                )
                .limit(self.settings.max_archaeology_search_results)
            )
            for commit in self.session.scalars(commit_query).all():
                if (from_date and commit.committed_at < from_date) or (
                    to_date and commit.committed_at > to_date
                ):
                    continue
                results.append(
                    HistoricalSearchItem(
                        entity_type="commit",
                        entity_id=None,
                        name=commit.short_sha,
                        historical_name=None,
                        kind="commit",
                        file_path=None,
                        commit_sha=commit.sha,
                        commit_id=commit.id,
                        status="historical",
                        lineage_id=None,
                        version_id=None,
                        matched_reason="commit message",
                        match_type="exact" if commit.message.casefold() == needle else "lexical",
                        source_available=False,
                    )
                )
        results = results[: self.settings.max_archaeology_search_results]
        total = len(results)
        start = (page - 1) * page_size
        return HistoricalSearchResponse(
            items=results[start : start + page_size], page=page, page_size=page_size, total=total
        )

    def dossier(
        self,
        repository_id: UUID,
        *,
        file_id: UUID | None,
        symbol_id: UUID | None,
        lineage_id: UUID | None,
    ) -> DossierResponse:
        self._ready(repository_id)
        metric = self._resolve_metric(
            repository_id, file_id=file_id, symbol_id=symbol_id, lineage_id=lineage_id
        )
        provenance = self.provenance(
            repository_id, file_id=file_id, symbol_id=symbol_id, lineage_id=lineage_id
        )
        contributors = self.contributors_for_metric(repository_id, metric)
        relevant_commits = {
            UUID(row["commit_id"]) for row in provenance.timeline if row.get("commit_id")
        }
        pr_count = (
            self.session.scalar(
                select(func.count(func.distinct(CommitPRLink.pull_request_id))).where(
                    CommitPRLink.repository_id == repository_id,
                    CommitPRLink.commit_id.in_(relevant_commits),
                )
            )
            if relevant_commits
            else 0
        )
        node = None
        if metric.entity_type == "symbol":
            symbol = self.session.scalar(
                select(CodeSymbol).where(
                    CodeSymbol.repository_id == repository_id,
                    CodeSymbol.lineage_id == metric.entity_id,
                )
            )
            if symbol:
                node = self.session.scalar(
                    select(DependencyNode).where(
                        DependencyNode.repository_id == repository_id,
                        DependencyNode.symbol_id == symbol.id,
                    )
                )
        elif (metric.metadata_json or {}).get("current_file_id"):
            current_file_id = UUID((metric.metadata_json or {})["current_file_id"])
            node = self.session.scalar(
                select(DependencyNode).where(
                    DependencyNode.repository_id == repository_id,
                    DependencyNode.file_id == current_file_id,
                    DependencyNode.node_type == "file",
                )
            )
        fan_in = (
            self.session.scalar(
                select(func.count())
                .select_from(DependencyEdge)
                .where(DependencyEdge.target_node_id == node.id)
            )
            if node
            else 0
        )
        fan_out = (
            self.session.scalar(
                select(func.count())
                .select_from(DependencyEdge)
                .where(DependencyEdge.source_node_id == node.id)
            )
            if node
            else 0
        )
        related = (
            self.related_code(repository_id, metric.entity_id, 0.8, True, True)
            if metric.entity_type == "symbol"
            else []
        )
        return DossierResponse(
            target=self._target(metric),
            provenance=provenance,
            activity={
                "changes_last_30_days": (metric.metadata_json or {}).get("changes_last_30_days", 0),
                "changes_last_90_days": (metric.metadata_json or {}).get("changes_last_90_days", 0),
                "changes_last_180_days": (metric.metadata_json or {}).get(
                    "changes_last_180_days", 0
                ),
                "churn_interpretation": "Frequently changed; churn is not a quality judgment.",
            },
            contributors=contributors,
            development_context={"linked_pull_requests": pr_count or 0, "linked_issues": 0},
            dependencies={
                "fan_in": fan_in or 0,
                "fan_out": fan_out or 0,
                "available": node is not None,
            },
            related_code=related,
            limitations=[
                "Git history may be incomplete after squashes or force pushes.",
                "Contribution history does not prove expertise or organizational ownership.",
                "Similarity is evidence of related code, not proof of copying.",
            ],
        )
