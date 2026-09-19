import difflib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    CodeSymbol,
    Commit,
    FileVersion,
    Repository,
    SymbolChangeEvent,
    SymbolLineage,
    SymbolVersion,
)
from app.schemas.history import (
    BlameLineRead,
    FileHistoryRead,
    FileVersionRead,
    HistoricalFileContent,
    HistoricalSymbolSource,
    HistoryCommit,
    HistoryEventPage,
    HistoryStatus,
    LineageSearchItem,
    LineageSearchPage,
    SymbolAtCommit,
    SymbolBlameSummary,
    SymbolEventRead,
    SymbolLineageRead,
    SymbolVersionCompare,
    SymbolVersionPage,
    SymbolVersionRead,
)
from app.services.git import GitService
from app.services.historical_index import HistoricalIndexService
from app.services.language_detector import LanguageDetector
from app.services.repositories import active_job, get_repository


class HistoryService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.git = GitService(self.settings)

    @staticmethod
    def _commit(item: Commit | None) -> HistoryCommit | None:
        if item is None:
            return None
        return HistoryCommit(
            sha=item.sha,
            short_sha=item.short_sha,
            message=item.message,
            author_name=item.author_name,
            authored_at=item.authored_at,
            committed_at=item.committed_at,
            is_merge_commit=item.is_merge_commit,
        )

    def _repository(self, repository_id: UUID, require_history: bool = True) -> Repository:
        repository = get_repository(self.session, repository_id)
        if require_history and repository.history_index_status not in {"ready", "limited"}:
            if repository.history_stale or repository.history_index_status == "stale":
                code = "HISTORY_STALE"
                message = "Git history changed. Reindex history before using this result."
            elif repository.history_index_status == "failed":
                code = "HISTORY_INDEX_FAILED"
                message = "Historical indexing failed. Retry the history index."
            else:
                code = "HISTORY_NOT_INDEXED"
                message = "Historical symbol history has not been indexed yet."
            raise IngestionError(code, message, 409)
        return repository

    def _lineage(self, repository_id: UUID, lineage_id: UUID) -> SymbolLineage:
        self._repository(repository_id)
        lineage = self.session.scalar(
            select(SymbolLineage).where(
                SymbolLineage.id == lineage_id, SymbolLineage.repository_id == repository_id
            )
        )
        if lineage is None:
            raise IngestionError("LINEAGE_NOT_FOUND", "Symbol lineage not found.", 404)
        return lineage

    def _version(self, repository_id: UUID, lineage_id: UUID, version_id: UUID) -> SymbolVersion:
        version = self.session.scalar(
            select(SymbolVersion).where(
                SymbolVersion.id == version_id,
                SymbolVersion.lineage_id == lineage_id,
                SymbolVersion.repository_id == repository_id,
            )
        )
        if version is None:
            raise IngestionError("SYMBOL_VERSION_NOT_FOUND", "Symbol version not found.", 404)
        return version

    def _version_read(self, version: SymbolVersion) -> SymbolVersionRead:
        commit = self.session.get(Commit, version.commit_id)
        assert commit is not None
        return SymbolVersionRead(
            id=version.id,
            lineage_id=version.lineage_id,
            file_path=version.file_path,
            language=version.language,
            name=version.name,
            qualified_name=version.qualified_name,
            kind=version.kind,
            signature=version.signature,
            start_line=version.start_line,
            end_line=version.end_line,
            start_column=version.start_column,
            end_column=version.end_column,
            documentation=version.documentation,
            match_type=version.match_type,
            match_confidence=version.match_confidence,
            matching_metadata=version.matching_metadata,
            source_truncated=version.source_truncated,
            commit=self._commit(commit),
        )

    @staticmethod
    def _label(event_type: str, summary: dict[str, object] | None, name: str) -> str:
        values = summary or {}
        if event_type == "renamed_and_moved":
            return (
                f"{values.get('old_name') or name} renamed to "
                f"{values.get('new_name') or name} and moved to "
                f"{values.get('new_path') or 'another file'}"
            )
        if event_type == "renamed":
            return f"{values.get('old_name') or name} renamed to {values.get('new_name') or name}"
        if event_type == "moved":
            return f"{name} moved to {values.get('new_path') or 'another file'}"
        labels = {
            "introduced": "introduced",
            "reintroduced": "reintroduced",
            "signature_changed": "signature changed",
            "body_changed": "body changed",
            "documentation_changed": "documentation changed",
            "modified": "modified",
            "deleted": "deleted",
        }
        return f"{name} {labels.get(event_type, event_type.replace('_', ' '))}"

    def _event_read(self, event: SymbolChangeEvent) -> SymbolEventRead:
        lineage = self.session.get(SymbolLineage, event.lineage_id)
        commit = self.session.get(Commit, event.commit_id)
        assert lineage is not None and commit is not None
        summary = event.summary_data or {}
        name = str(
            summary.get("new_name")
            or summary.get("old_name")
            or lineage.current_name
            or "Unknown symbol"
        )
        path = summary.get("new_path") or summary.get("old_path") or lineage.current_file_path
        return SymbolEventRead(
            id=event.id,
            lineage_id=event.lineage_id,
            event_type=event.event_type,
            previous_version_id=event.previous_version_id,
            new_version_id=event.new_version_id,
            summary_data=event.summary_data,
            commit=self._commit(commit),
            symbol_name=name,
            symbol_kind=lineage.symbol_kind,
            file_path=str(path) if path else None,
            deterministic_label=self._label(event.event_type, event.summary_data, name),
        )

    def status(self, repository_id: UUID) -> HistoryStatus:
        repository = self._repository(repository_id, require_history=False)
        job = active_job(self.session, repository_id)
        lineages, versions, events = HistoricalIndexService.counts(self.session, repository_id)
        return HistoryStatus(
            status=repository.history_index_status,
            progress=job.progress if job and job.job_type == "historical_index" else None,
            current_step=job.current_step if job and job.job_type == "historical_index" else None,
            indexed_commits=repository.history_indexed_commit_count,
            total_commits=repository.history_total_commit_count or repository.commit_count,
            lineages=lineages,
            versions=versions,
            events=events,
            history_limited=repository.history_limited,
            history_stale=repository.history_stale,
            last_indexed_sha=repository.history_indexed_through_sha,
            job_id=job.id if job and job.job_type == "historical_index" else None,
        )

    def versions(
        self, repository_id: UUID, lineage_id: UUID, page: int, page_size: int
    ) -> SymbolVersionPage:
        self._lineage(repository_id, lineage_id)
        query = (
            select(SymbolVersion)
            .join(Commit, SymbolVersion.commit_id == Commit.id)
            .where(SymbolVersion.lineage_id == lineage_id)
        )
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self.session.scalars(
            query.order_by(Commit.committed_at, Commit.sha)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return SymbolVersionPage(
            items=[self._version_read(item) for item in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    def events(self, repository_id: UUID, lineage_id: UUID) -> list[SymbolEventRead]:
        self._lineage(repository_id, lineage_id)
        rows = self.session.scalars(
            select(SymbolChangeEvent)
            .join(Commit, SymbolChangeEvent.commit_id == Commit.id)
            .where(SymbolChangeEvent.lineage_id == lineage_id)
            .order_by(Commit.committed_at, Commit.sha, SymbolChangeEvent.event_type)
        )
        return [self._event_read(item) for item in rows]

    def lineage(self, repository_id: UUID, lineage_id: UUID) -> SymbolLineageRead:
        lineage = self._lineage(repository_id, lineage_id)
        versions = self.versions(
            repository_id, lineage_id, 1, self.settings.max_history_commits
        ).items
        events = self.events(repository_id, lineage_id)
        introduced = (
            self.session.get(Commit, lineage.introduced_commit_id)
            if lineage.introduced_commit_id
            else None
        )
        last_seen = (
            self.session.get(Commit, lineage.last_seen_commit_id)
            if lineage.last_seen_commit_id
            else None
        )
        deleted = (
            self.session.get(Commit, lineage.deleted_commit_id)
            if lineage.deleted_commit_id
            else None
        )
        return SymbolLineageRead(
            id=lineage.id,
            current_name=lineage.current_name,
            current_qualified_name=lineage.current_qualified_name,
            current_file_path=lineage.current_file_path,
            symbol_kind=lineage.symbol_kind,
            is_deleted=lineage.is_deleted,
            introduced_commit=self._commit(introduced),
            last_seen_commit=self._commit(last_seen),
            deleted_commit=self._commit(deleted),
            latest_version=versions[-1] if versions else None,
            versions=versions,
            events=events,
            previous_names=list(dict.fromkeys(item.name for item in versions)),
            file_paths=list(dict.fromkeys(item.file_path for item in versions)),
        )

    def for_current_symbol(self, repository_id: UUID, symbol_id: UUID) -> SymbolLineageRead:
        self._repository(repository_id)
        symbol = self.session.scalar(
            select(CodeSymbol).where(
                CodeSymbol.id == symbol_id, CodeSymbol.repository_id == repository_id
            )
        )
        if symbol is None:
            raise IngestionError("SYMBOL_NOT_FOUND", "Symbol not found.", 404)
        if symbol.lineage_id is None:
            raise IngestionError(
                "LINEAGE_NOT_FOUND", "No historical lineage is available for this symbol.", 404
            )
        return self.lineage(repository_id, symbol.lineage_id)

    def search_lineages(
        self, repository_id: UUID, search: str | None, page: int, page_size: int
    ) -> LineageSearchPage:
        self._repository(repository_id)
        lineages = list(
            self.session.scalars(
                select(SymbolLineage)
                .where(SymbolLineage.repository_id == repository_id)
                .order_by(SymbolLineage.current_qualified_name)
            )
        )
        versions = list(
            self.session.scalars(
                select(SymbolVersion).where(SymbolVersion.repository_id == repository_id)
            )
        )
        names: dict[UUID, list[str]] = {}
        for version in versions:
            names.setdefault(version.lineage_id, []).append(version.name)
        needle = (search or "").casefold()
        filtered = [
            item
            for item in lineages
            if not needle
            or needle in (item.current_qualified_name or "").casefold()
            or any(needle in value.casefold() for value in names.get(item.id, []))
        ]
        start = (page - 1) * page_size
        return LineageSearchPage(
            items=[
                LineageSearchItem(
                    lineage_id=item.id,
                    current_name=item.current_name,
                    current_qualified_name=item.current_qualified_name,
                    current_file_path=item.current_file_path,
                    symbol_kind=item.symbol_kind,
                    is_deleted=item.is_deleted,
                    previous_names=list(dict.fromkeys(names.get(item.id, []))),
                )
                for item in filtered[start : start + page_size]
            ],
            page=page,
            page_size=page_size,
            total=len(filtered),
        )

    def source(
        self, repository_id: UUID, lineage_id: UUID, version_id: UUID
    ) -> HistoricalSymbolSource:
        repository = self._repository(repository_id)
        self._lineage(repository_id, lineage_id)
        version = self._version(repository_id, lineage_id, version_id)
        commit = self.session.get(Commit, version.commit_id)
        assert commit is not None
        retrieved = version.source_text is None
        source = version.source_text
        if source is None:
            content = self.git.get_file_at_commit(
                self.git.storage.path(repository.id), commit.sha, version.file_path
            ).decode("utf-8", "replace")
            lines = content.splitlines(keepends=True)
            source = "".join(lines[version.start_line - 1 : version.end_line])
            if (
                len(source.encode("utf-8", "replace"))
                > self.settings.max_historical_symbol_source_bytes
            ):
                raise IngestionError(
                    "HISTORICAL_SOURCE_TOO_LARGE", "Historical symbol source is too large.", 413
                )
        return HistoricalSymbolSource(
            version_id=version.id,
            commit_sha=commit.sha,
            file_path=version.file_path,
            start_line=version.start_line,
            end_line=version.end_line,
            language=version.language,
            source=source,
            retrieved_from_git=retrieved,
        )

    def compare(
        self,
        repository_id: UUID,
        lineage_id: UUID,
        from_version: UUID,
        to_version: UUID,
    ) -> SymbolVersionCompare:
        old = self._version(repository_id, lineage_id, from_version)
        new = self._version(repository_id, lineage_id, to_version)
        old_source = self.source(repository_id, lineage_id, old.id).source
        new_source = self.source(repository_id, lineage_id, new.id).source
        diff = "".join(
            difflib.unified_diff(
                old_source.splitlines(keepends=True),
                new_source.splitlines(keepends=True),
                fromfile=f"{old.file_path}@{old.name}",
                tofile=f"{new.file_path}@{new.name}",
            )
        )
        encoded = diff.encode("utf-8", "replace")
        truncated = len(encoded) > self.settings.max_diff_size_bytes
        if truncated:
            diff = encoded[: self.settings.max_diff_size_bytes].decode("utf-8", "replace")
        return SymbolVersionCompare(
            from_version=old.id,
            to_version=new.id,
            old_source=old_source,
            new_source=new_source,
            old_name=old.name,
            new_name=new.name,
            old_path=old.file_path,
            new_path=new.file_path,
            old_signature=old.signature,
            new_signature=new.signature,
            old_lines=(old.start_line, old.end_line),
            new_lines=(new.start_line, new.end_line),
            diff=diff,
            truncated=truncated,
        )

    def at_commit(self, repository_id: UUID, lineage_id: UUID, commit_sha: str) -> SymbolAtCommit:
        repository = self._repository(repository_id)
        self._lineage(repository_id, lineage_id)
        sha = self.git.validate_sha(commit_sha)
        if (
            self.session.scalar(
                select(Commit.id).where(Commit.repository_id == repository_id, Commit.sha == sha)
            )
            is None
        ):
            raise IngestionError(
                "COMMIT_NOT_INDEXED", "Commit is not indexed for this repository.", 404
            )
        shas = self.git.get_commits(self.git.storage.path(repository.id), repository.head_sha)
        target = shas.index(sha)
        order = {value: index for index, value in enumerate(shas)}
        versions = list(
            self.session.scalars(
                select(SymbolVersion).where(SymbolVersion.lineage_id == lineage_id)
            )
        )
        candidates = [
            item
            for item in versions
            if (commit := self.session.get(Commit, item.commit_id)) is not None
            and order.get(commit.sha, len(shas)) <= target
        ]
        commit_positions = {
            item.id: order[item.sha]
            for item in self.session.scalars(
                select(Commit).where(Commit.repository_id == repository_id)
            )
            if item.sha in order
        }
        candidates.sort(key=lambda item: commit_positions[item.commit_id])
        latest = candidates[-1] if candidates else None
        exists = False
        for event in self.events(repository_id, lineage_id):
            position = order.get(event.commit.sha, len(shas))
            if position > target:
                continue
            if event.event_type in {"introduced", "reintroduced"}:
                exists = True
            elif event.event_type == "deleted":
                exists = False
        read = self._version_read(latest) if latest else None
        return SymbolAtCommit(
            commit_sha=sha,
            exists_at_commit=exists,
            version=read if exists else None,
            last_known_version=read,
        )

    def file_history(self, repository_id: UUID, file_path: str) -> FileHistoryRead:
        self._repository(repository_id)
        safe = self.git.validate_path(file_path)
        candidates = list(
            self.session.scalars(
                select(FileVersion).where(
                    FileVersion.repository_id == repository_id, FileVersion.path == safe
                )
            )
        )
        if not candidates:
            raise IngestionError("HISTORICAL_FILE_NOT_FOUND", "File history not found.", 404)
        commit_positions = {
            item.id: index
            for index, item in enumerate(
                self.session.scalars(
                    select(Commit)
                    .where(Commit.repository_id == repository_id)
                    .order_by(Commit.committed_at, Commit.sha)
                )
            )
        }
        candidates.sort(key=lambda item: commit_positions.get(item.commit_id, -1))
        lineage_id = candidates[-1].file_lineage_id
        versions = list(
            self.session.scalars(
                select(FileVersion)
                .join(Commit, FileVersion.commit_id == Commit.id)
                .where(FileVersion.file_lineage_id == lineage_id)
                .order_by(Commit.committed_at, Commit.sha)
            )
        )
        items = [
            FileVersionRead(
                id=item.id,
                path=item.path,
                blob_sha=item.blob_sha,
                language=item.language,
                size_bytes=item.size_bytes,
                line_count=item.line_count,
                change_type=item.change_type,
                commit=self._commit(self.session.get(Commit, item.commit_id)),
            )
            for item in versions
        ]
        return FileHistoryRead(
            lineage_id=lineage_id,
            created=items[0].commit,
            current_path=None if items[-1].change_type == "deleted" else items[-1].path,
            is_deleted=items[-1].change_type == "deleted",
            versions=items,
        )

    def content_at(
        self, repository_id: UUID, file_path: str, commit_sha: str
    ) -> HistoricalFileContent:
        repository = self._repository(repository_id)
        safe = self.git.validate_path(file_path)
        sha = self.git.validate_sha(commit_sha)
        if (
            self.session.scalar(
                select(Commit.id).where(Commit.repository_id == repository_id, Commit.sha == sha)
            )
            is None
        ):
            raise IngestionError(
                "COMMIT_NOT_INDEXED", "Commit is not indexed for this repository.", 404
            )
        raw = self.git.get_file_at_commit(self.git.storage.path(repository.id), sha, safe)
        if LanguageDetector.is_binary(raw):
            raise IngestionError("BINARY_FILE", "Binary file contents cannot be displayed.", 415)
        content = raw.decode("utf-8", "replace")
        return HistoricalFileContent(
            path=safe,
            commit_sha=sha,
            content=content,
            language=LanguageDetector().detect(safe).language,
            total_lines=len(content.splitlines()),
        )

    def repository_events(
        self,
        repository_id: UUID,
        event_type: str | None,
        symbol_kind: str | None,
        file_path: str | None,
        author: str | None,
        from_commit: str | None,
        to_commit: str | None,
        page: int,
        page_size: int,
    ) -> HistoryEventPage:
        self._repository(repository_id)
        query = (
            select(SymbolChangeEvent)
            .join(Commit, SymbolChangeEvent.commit_id == Commit.id)
            .join(SymbolLineage, SymbolChangeEvent.lineage_id == SymbolLineage.id)
            .where(SymbolChangeEvent.repository_id == repository_id)
        )
        if event_type:
            query = query.where(SymbolChangeEvent.event_type == event_type)
        if symbol_kind:
            query = query.where(SymbolLineage.symbol_kind == symbol_kind)
        if author:
            query = query.where(Commit.author_name.ilike(f"%{author}%"))
        rows = list(
            self.session.scalars(query.order_by(Commit.committed_at.desc(), Commit.sha.desc()))
        )
        items = [self._event_read(item) for item in rows]
        if file_path:
            safe = self.git.validate_path(file_path)
            items = [item for item in items if item.file_path == safe]
        if from_commit or to_commit:
            repository = self._repository(repository_id)
            shas = self.git.get_commits(self.git.storage.path(repository.id), repository.head_sha)
            positions = {sha: index for index, sha in enumerate(shas)}
            start_position = 0
            end_position = len(shas) - 1
            if from_commit:
                start_sha = self.git.validate_sha(from_commit)
                if start_sha not in positions:
                    raise IngestionError(
                        "COMMIT_NOT_INDEXED", "Starting commit is not indexed.", 404
                    )
                start_position = positions[start_sha]
            if to_commit:
                end_sha = self.git.validate_sha(to_commit)
                if end_sha not in positions:
                    raise IngestionError("COMMIT_NOT_INDEXED", "Ending commit is not indexed.", 404)
                end_position = positions[end_sha]
            if end_position < start_position:
                raise IngestionError("INVALID_COMMIT_RANGE", "Commit range is reversed.", 422)
            items = [
                item
                for item in items
                if start_position <= positions.get(item.commit.sha, -1) <= end_position
            ]
        start = (page - 1) * page_size
        return HistoryEventPage(
            items=items[start : start + page_size],
            page=page,
            page_size=page_size,
            total=len(items),
        )

    def commit_events(self, repository_id: UUID, commit_sha: str) -> list[SymbolEventRead]:
        self._repository(repository_id)
        sha = self.git.validate_sha(commit_sha)
        commit = self.session.scalar(
            select(Commit).where(Commit.repository_id == repository_id, Commit.sha == sha)
        )
        if commit is None:
            raise IngestionError(
                "COMMIT_NOT_INDEXED", "Commit is not indexed for this repository.", 404
            )
        events = self.session.scalars(
            select(SymbolChangeEvent)
            .where(SymbolChangeEvent.commit_id == commit.id)
            .order_by(SymbolChangeEvent.event_type)
        )
        return [self._event_read(item) for item in events]

    def blame(
        self,
        repository_id: UUID,
        file_path: str,
        start_line: int | None,
        end_line: int | None,
    ) -> list[BlameLineRead]:
        repository = self._repository(repository_id, require_history=False)
        if not repository.head_sha:
            raise IngestionError("COMMIT_NOT_INDEXED", "Repository HEAD is not indexed.", 409)
        lines = self.git.get_blame(
            self.git.storage.path(repository.id),
            repository.head_sha,
            file_path,
            start_line,
            end_line,
        )
        return [
            BlameLineRead(
                line=item.line,
                commit_sha=item.commit_sha,
                author=item.author,
                author_time=datetime.fromtimestamp(item.author_time, UTC),
                source=item.source,
                original_line=item.original_line,
                original_path=item.original_path,
            )
            for item in lines
        ]

    def lineage_blame(self, repository_id: UUID, lineage_id: UUID) -> SymbolBlameSummary:
        lineage = self.lineage(repository_id, lineage_id)
        if (
            lineage.is_deleted
            or lineage.latest_version is None
            or lineage.current_file_path is None
        ):
            return SymbolBlameSummary(
                introduced_commit=lineage.introduced_commit,
                last_symbol_change_commit=lineage.last_seen_commit,
                recent_line_authors=[],
                lines=[],
            )
        latest = lineage.latest_version
        lines = self.blame(
            repository_id, lineage.current_file_path, latest.start_line, latest.end_line
        )
        return SymbolBlameSummary(
            introduced_commit=lineage.introduced_commit,
            last_symbol_change_commit=lineage.last_seen_commit,
            recent_line_authors=list(dict.fromkeys(item.author for item in lines)),
            lines=lines,
        )
