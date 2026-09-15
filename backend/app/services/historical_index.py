import logging
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, delete, func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AnalysisJob,
    CodeSymbol,
    Commit,
    FileLineage,
    FileVersion,
    JobStatus,
    Repository,
    RepositoryStatus,
    SymbolChangeEvent,
    SymbolLineage,
    SymbolVersion,
)
from app.parsers.git_history import GitFileChange
from app.parsers.models import ParsedSymbol
from app.parsers.registry import ParserRegistry
from app.services.git import GitService, GitTreeEntry
from app.services.language_detector import LanguageDetector
from app.services.symbol_matcher import HistoricalSymbol, SymbolMatch, SymbolMatcher, digest

logger = logging.getLogger("ctm")


@dataclass
class FileState:
    lineage: FileLineage
    version: FileVersion


@dataclass
class FileContext:
    state: FileState
    previous: list[HistoricalSymbol]
    current: list[HistoricalSymbol]
    change_type: str
    local_matches: list[SymbolMatch]
    unmatched_previous: list[int]
    unmatched_current: list[int]
    old_path: str | None


class HistoricalIndexService:
    """Build symbol history from immutable Git objects and Phase 1 file changes."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.detector = LanguageDetector()
        self.registry = ParserRegistry()
        self.matcher = SymbolMatcher(
            self.settings.symbol_match_threshold, self.settings.symbol_rename_match_threshold
        )

    @staticmethod
    def _symbol_source(source: str, symbol: ParsedSymbol) -> str:
        lines = source.splitlines(keepends=True)
        return "".join(lines[symbol.start_line - 1 : symbol.end_line])

    def _parse_symbols(
        self, source_bytes: bytes, language: str, file_path: str, file_lineage_id: UUID
    ) -> list[HistoricalSymbol]:
        parser = self.registry.get(language)
        if parser is None or self.detector.is_binary(source_bytes):
            return []
        result = parser.parse(source_bytes, self.settings.max_parse_time_per_file_seconds)
        if not result.parse_success:
            return []
        source = source_bytes.decode("utf-8", "replace")
        return [
            HistoricalSymbol(
                symbol=symbol,
                source=self._symbol_source(source, symbol),
                file_path=file_path,
                file_lineage_id=file_lineage_id,
            )
            for symbol in result.symbols
        ]

    @staticmethod
    def _from_version(version: SymbolVersion, file_lineage_id: UUID) -> HistoricalSymbol:
        return HistoricalSymbol(
            symbol=ParsedSymbol(
                name=version.name,
                qualified_name=version.qualified_name,
                kind=version.kind,
                signature=version.signature,
                start_line=version.start_line,
                end_line=version.end_line,
                start_column=version.start_column,
                end_column=version.end_column,
                documentation=version.documentation,
            ),
            source=version.source_text or "",
            file_path=version.file_path,
            file_lineage_id=file_lineage_id,
            lineage_id=version.lineage_id,
            version_id=version.id,
            parent_lineage_id=version.parent_lineage_id,
        )

    def _clear(self, session: Session, repository_id: UUID) -> None:
        session.execute(
            update(CodeSymbol)
            .where(CodeSymbol.repository_id == repository_id)
            .values(lineage_id=None)
        )
        session.execute(
            delete(SymbolChangeEvent).where(SymbolChangeEvent.repository_id == repository_id)
        )
        session.execute(delete(SymbolVersion).where(SymbolVersion.repository_id == repository_id))
        session.execute(delete(SymbolLineage).where(SymbolLineage.repository_id == repository_id))
        session.execute(delete(FileVersion).where(FileVersion.repository_id == repository_id))
        session.execute(delete(FileLineage).where(FileLineage.repository_id == repository_id))
        session.flush()

    def _load_state(
        self, session: Session, repository_id: UUID, order: dict[UUID, int]
    ) -> tuple[
        dict[str, FileState],
        dict[UUID, list[HistoricalSymbol]],
        list[HistoricalSymbol],
    ]:
        file_versions = list(
            session.scalars(select(FileVersion).where(FileVersion.repository_id == repository_id))
        )
        latest_files: dict[UUID, FileVersion] = {}
        for file_version in sorted(file_versions, key=lambda item: order.get(item.commit_id, -1)):
            latest_files[file_version.file_lineage_id] = file_version
        file_lineages = {
            item.id: item
            for item in session.scalars(
                select(FileLineage).where(FileLineage.repository_id == repository_id)
            )
        }
        active_files = {
            version.path: FileState(file_lineages[lineage_id], version)
            for lineage_id, version in latest_files.items()
            if version.change_type != "deleted" and lineage_id in file_lineages
        }
        version_to_file = {
            file_version.id: file_version.file_lineage_id for file_version in file_versions
        }
        symbol_versions = list(
            session.scalars(
                select(SymbolVersion).where(SymbolVersion.repository_id == repository_id)
            )
        )
        latest_symbols: dict[UUID, SymbolVersion] = {}
        for symbol_version in sorted(
            symbol_versions, key=lambda item: order.get(item.commit_id, -1)
        ):
            latest_symbols[symbol_version.lineage_id] = symbol_version
        lineages = {
            item.id: item
            for item in session.scalars(
                select(SymbolLineage).where(SymbolLineage.repository_id == repository_id)
            )
        }
        active_symbols: dict[UUID, list[HistoricalSymbol]] = {}
        deleted_symbols: list[HistoricalSymbol] = []
        for lineage_id, symbol_version in latest_symbols.items():
            lineage = lineages.get(lineage_id)
            file_lineage_id = (
                version_to_file.get(symbol_version.file_version_id)
                if symbol_version.file_version_id
                else None
            )
            if lineage is None or file_lineage_id is None:
                continue
            item = self._from_version(symbol_version, file_lineage_id)
            if lineage.is_deleted:
                deleted_symbols.append(item)
            else:
                active_symbols.setdefault(file_lineage_id, []).append(item)
        for items in active_symbols.values():
            items.sort(key=lambda item: (item.symbol.start_line, item.symbol.start_column))
        return active_files, active_symbols, deleted_symbols

    def _file_context(
        self,
        session: Session,
        repository_id: UUID,
        commit: Commit,
        path: Path,
        git: GitService,
        change: GitFileChange,
        active_files: dict[str, FileState],
        active_symbols: dict[UUID, list[HistoricalSymbol]],
    ) -> FileContext | None:
        old_path = git.validate_path(change.old_path) if change.old_path else None
        new_path = git.validate_path(change.new_path) if change.new_path else None
        detected = self.detector.detect(new_path or old_path or "")
        if detected.excluded or detected.language is None:
            return None
        previous_state = active_files.get(old_path or new_path or "")
        if change.change_type == "deleted":
            if previous_state is None or old_path is None:
                return None
            old_version = previous_state.version
            version = FileVersion(
                file_lineage_id=previous_state.lineage.id,
                repository_id=repository_id,
                commit_id=commit.id,
                path=old_path,
                blob_sha=old_version.blob_sha,
                language=old_version.language,
                size_bytes=old_version.size_bytes,
                line_count=old_version.line_count,
                change_type="deleted",
                previous_file_version_id=old_version.id,
            )
            session.add(version)
            session.flush()
            return FileContext(
                FileState(previous_state.lineage, version),
                list(active_symbols.get(previous_state.lineage.id, [])),
                [],
                "deleted",
                [],
                list(range(len(active_symbols.get(previous_state.lineage.id, [])))),
                [],
                old_path,
            )
        if new_path is None:
            return None
        blob_sha, size = git.get_blob_sha(path, commit.sha, new_path)
        source = git.get_blob(path, blob_sha, size)
        if change.change_type == "renamed" and previous_state is not None:
            lineage = previous_state.lineage
        elif change.change_type == "modified" and previous_state is not None:
            lineage = previous_state.lineage
        else:
            lineage = FileLineage(repository_id=repository_id)
            session.add(lineage)
            session.flush()
        previous_version = (
            previous_state.version
            if previous_state and previous_state.lineage.id == lineage.id
            else None
        )
        language = self.detector.detect(new_path).language
        version = FileVersion(
            file_lineage_id=lineage.id,
            repository_id=repository_id,
            commit_id=commit.id,
            path=new_path,
            blob_sha=blob_sha,
            language=language,
            size_bytes=size,
            line_count=len(source.splitlines()),
            change_type=change.change_type,
            previous_file_version_id=previous_version.id if previous_version else None,
        )
        session.add(version)
        session.flush()
        previous = list(active_symbols.get(lineage.id, []))
        current = self._parse_symbols(source, language or "", new_path, lineage.id)
        matched = self.matcher.match(previous, current)
        return FileContext(
            FileState(lineage, version),
            previous,
            current,
            change.change_type,
            matched.matches,
            matched.unmatched_previous,
            matched.unmatched_current,
            old_path,
        )

    @staticmethod
    def _event_types(previous: HistoricalSymbol, current: HistoricalSymbol) -> list[str]:
        events: list[str] = []
        renamed = previous.symbol.name != current.symbol.name
        previous_parent = previous.symbol.qualified_name.rpartition(".")[0]
        current_parent = current.symbol.qualified_name.rpartition(".")[0]
        moved = previous.file_path != current.file_path or previous_parent != current_parent
        if renamed and moved:
            events.append("renamed_and_moved")
        elif renamed:
            events.append("renamed")
        elif moved:
            events.append("moved")
        if previous.signature_hash != current.signature_hash:
            events.append("signature_changed")
        if previous.normalized_body_hash != current.normalized_body_hash:
            events.append("body_changed")
        if digest(previous.symbol.documentation) != digest(current.symbol.documentation):
            events.append("documentation_changed")
        if (
            previous.symbol.start_line != current.symbol.start_line
            or previous.symbol.end_line != current.symbol.end_line
        ) and not events:
            events.append("modified")
        if not events and previous.body_hash != current.body_hash:
            events.append("modified")
        return events

    @staticmethod
    def _summary(
        previous: HistoricalSymbol | None, current: HistoricalSymbol | None
    ) -> dict[str, object]:
        return {
            "old_name": previous.symbol.name if previous else None,
            "new_name": current.symbol.name if current else None,
            "old_path": previous.file_path if previous else None,
            "new_path": current.file_path if current else None,
            "old_signature": previous.symbol.signature if previous else None,
            "new_signature": current.symbol.signature if current else None,
            "old_start_line": previous.symbol.start_line if previous else None,
            "old_end_line": previous.symbol.end_line if previous else None,
            "new_start_line": current.symbol.start_line if current else None,
            "new_end_line": current.symbol.end_line if current else None,
        }

    def _new_lineage(
        self, session: Session, repository_id: UUID, commit: Commit, current: HistoricalSymbol
    ) -> SymbolLineage:
        lineage = SymbolLineage(
            repository_id=repository_id,
            symbol_kind=current.symbol.kind,
            current_name=current.symbol.name,
            current_qualified_name=current.symbol.qualified_name,
            current_file_path=current.file_path,
            introduced_commit_id=commit.id,
            last_seen_commit_id=commit.id,
            is_deleted=False,
        )
        session.add(lineage)
        session.flush()
        return lineage

    def _new_version(
        self,
        session: Session,
        repository_id: UUID,
        commit: Commit,
        file_version: FileVersion,
        current: HistoricalSymbol,
        lineage: SymbolLineage,
        match_type: str,
        confidence: float,
        evidence: dict[str, object],
        parent_lineage_id: UUID | None,
    ) -> SymbolVersion:
        encoded = current.source.encode("utf-8", "replace")
        store_source = len(encoded) <= self.settings.max_historical_symbol_source_bytes
        version = SymbolVersion(
            lineage_id=lineage.id,
            repository_id=repository_id,
            commit_id=commit.id,
            file_version_id=file_version.id,
            file_path=current.file_path,
            language=file_version.language,
            name=current.symbol.name,
            qualified_name=current.symbol.qualified_name,
            kind=current.symbol.kind,
            signature=current.symbol.signature,
            start_line=current.symbol.start_line,
            end_line=current.symbol.end_line,
            start_column=current.symbol.start_column,
            end_column=current.symbol.end_column,
            body_hash=current.body_hash,
            normalized_body_hash=current.normalized_body_hash,
            signature_hash=current.signature_hash,
            structure_hash=current.structure_hash,
            source_text=current.source if store_source else None,
            source_truncated=not store_source,
            documentation=current.symbol.documentation,
            parent_lineage_id=parent_lineage_id,
            match_type=match_type,
            match_confidence=confidence,
            matching_metadata=evidence,
        )
        session.add(version)
        session.flush()
        lineage.current_name = current.symbol.name
        lineage.current_qualified_name = current.symbol.qualified_name
        lineage.current_file_path = current.file_path
        lineage.symbol_kind = current.symbol.kind
        lineage.last_seen_commit_id = commit.id
        lineage.deleted_commit_id = None
        lineage.is_deleted = False
        return version

    @staticmethod
    def _add_event(
        session: Session,
        repository_id: UUID,
        commit: Commit,
        lineage_id: UUID,
        event_type: str,
        previous_version_id: UUID | None,
        new_version_id: UUID | None,
        summary: dict[str, object],
    ) -> None:
        session.add(
            SymbolChangeEvent(
                repository_id=repository_id,
                lineage_id=lineage_id,
                commit_id=commit.id,
                previous_version_id=previous_version_id,
                new_version_id=new_version_id,
                event_type=event_type,
                summary_data=summary,
            )
        )

    def _persist_contexts(
        self,
        session: Session,
        repository_id: UUID,
        commit: Commit,
        contexts: list[FileContext],
        active_files: dict[str, FileState],
        active_symbols: dict[UUID, list[HistoricalSymbol]],
        deleted_symbols: list[HistoricalSymbol],
    ) -> tuple[int, int, int]:
        match_by_current: dict[tuple[int, int], tuple[HistoricalSymbol, SymbolMatch]] = {}
        remaining_old: list[tuple[int, int, HistoricalSymbol]] = []
        remaining_new: list[tuple[int, int, HistoricalSymbol]] = []
        for context_index, context in enumerate(contexts):
            for match in context.local_matches:
                match_by_current[context_index, match.current_index] = (
                    context.previous[match.previous_index],
                    match,
                )
            remaining_old.extend(
                (context_index, index, context.previous[index])
                for index in context.unmatched_previous
            )
            remaining_new.extend(
                (context_index, index, context.current[index])
                for index in context.unmatched_current
            )

        if remaining_old and remaining_new:
            cross = self.matcher.match(
                [item[2] for item in remaining_old], [item[2] for item in remaining_new]
            )
            matched_old: set[int] = set()
            matched_new: set[int] = set()
            for match in cross.matches:
                old_context, old_index, old = remaining_old[match.previous_index]
                new_context, new_index, _ = remaining_new[match.current_index]
                if old_context == new_context:
                    continue
                match_by_current[new_context, new_index] = (old, match)
                matched_old.add(match.previous_index)
                matched_new.add(match.current_index)
            remaining_old = [
                item for index, item in enumerate(remaining_old) if index not in matched_old
            ]
            remaining_new = [
                item for index, item in enumerate(remaining_new) if index not in matched_new
            ]

        reintroduced: dict[tuple[int, int], tuple[HistoricalSymbol, SymbolMatch]] = {}
        if deleted_symbols and remaining_new:
            result = self.matcher.match(deleted_symbols, [item[2] for item in remaining_new])
            used_new: set[int] = set()
            used_deleted: set[int] = set()
            for match in result.matches:
                context_index, current_index, _ = remaining_new[match.current_index]
                reintroduced[context_index, current_index] = (
                    deleted_symbols[match.previous_index],
                    match,
                )
                used_new.add(match.current_index)
                used_deleted.add(match.previous_index)
            remaining_new = [
                item for index, item in enumerate(remaining_new) if index not in used_new
            ]
            deleted_symbols[:] = [
                item for index, item in enumerate(deleted_symbols) if index not in used_deleted
            ]

        versions_created = lineages_created = events_created = 0
        current_active: dict[UUID, list[HistoricalSymbol]] = {}
        for context_index, context in enumerate(contexts):
            lineage_by_index: dict[int, SymbolLineage] = {}
            pending: list[
                tuple[
                    int,
                    HistoricalSymbol,
                    HistoricalSymbol | None,
                    SymbolMatch | None,
                    bool,
                ]
            ] = []
            for current_index, current in enumerate(context.current):
                previous_and_match = match_by_current.get((context_index, current_index))
                was_reintroduced = False
                if previous_and_match is None:
                    previous_and_match = reintroduced.get((context_index, current_index))
                    was_reintroduced = previous_and_match is not None
                previous = previous_and_match[0] if previous_and_match else None
                candidate_match = previous_and_match[1] if previous_and_match else None
                if previous and previous.lineage_id:
                    lineage = session.get(SymbolLineage, previous.lineage_id)
                    assert lineage is not None
                else:
                    lineage = self._new_lineage(session, repository_id, commit, current)
                    lineages_created += 1
                lineage_by_index[current_index] = lineage
                pending.append(
                    (current_index, current, previous, candidate_match, was_reintroduced)
                )
            for current_index, current, previous, candidate_match, was_reintroduced in pending:
                lineage = lineage_by_index[current_index]
                parent_id = None
                if current.symbol.parent_index is not None:
                    parent = lineage_by_index.get(current.symbol.parent_index)
                    parent_id = parent.id if parent else None
                event_types = self._event_types(previous, current) if previous else ["introduced"]
                if was_reintroduced:
                    event_types = ["reintroduced", *event_types]
                needs_version = previous is None or bool(event_types) or was_reintroduced
                if needs_version:
                    version = self._new_version(
                        session,
                        repository_id,
                        commit,
                        context.state.version,
                        current,
                        lineage,
                        candidate_match.match_type
                        if candidate_match
                        else ("body_similarity" if was_reintroduced else "exact"),
                        candidate_match.confidence
                        if candidate_match
                        else (0.9 if was_reintroduced else 1.0),
                        candidate_match.evidence
                        if candidate_match
                        else {"introduced": not was_reintroduced},
                        parent_id,
                    )
                    versions_created += 1
                    current_active.setdefault(context.state.lineage.id, []).append(
                        replace(
                            current,
                            lineage_id=lineage.id,
                            version_id=version.id,
                            parent_lineage_id=parent_id,
                        )
                    )
                    for event_type in dict.fromkeys(event_types):
                        self._add_event(
                            session,
                            repository_id,
                            commit,
                            lineage.id,
                            event_type,
                            previous.version_id if previous else None,
                            version.id,
                            self._summary(previous, current),
                        )
                        events_created += 1
                elif previous:
                    lineage.last_seen_commit_id = commit.id
                    current_active.setdefault(context.state.lineage.id, []).append(previous)

        for _, _, previous in remaining_old:
            if previous.lineage_id is None:
                continue
            lineage = session.get(SymbolLineage, previous.lineage_id)
            if lineage is None or lineage.is_deleted:
                continue
            lineage.is_deleted = True
            lineage.deleted_commit_id = commit.id
            self._add_event(
                session,
                repository_id,
                commit,
                lineage.id,
                "deleted",
                previous.version_id,
                None,
                self._summary(previous, None),
            )
            events_created += 1
            deleted_symbols.append(previous)

        for context in contexts:
            old_path = context.old_path
            if old_path and old_path != context.state.version.path:
                active_files.pop(old_path, None)
            if context.change_type == "deleted":
                active_files.pop(context.state.version.path, None)
                active_symbols.pop(context.state.lineage.id, None)
            else:
                active_files[context.state.version.path] = context.state
                active_symbols[context.state.lineage.id] = current_active.get(
                    context.state.lineage.id, []
                )
        return versions_created, lineages_created, events_created

    @staticmethod
    def _stored_changes(session: Session, commit_id: UUID) -> list[GitFileChange]:
        from app.db.models import FileChange

        rows = session.scalars(
            select(FileChange)
            .where(FileChange.commit_id == commit_id)
            .order_by(FileChange.change_order)
        )
        return [
            GitFileChange(
                old_path=row.old_path,
                new_path=row.new_path,
                change_type=row.change_type,
                additions=row.additions,
                deletions=row.deletions,
                similarity_score=row.similarity_score,
            )
            for row in rows
        ]

    @staticmethod
    def _baseline_changes(entries: list[GitTreeEntry]) -> list[GitFileChange]:
        return [GitFileChange(None, item.path, "added", None, None, None) for item in entries]

    def _relevant_change(self, change: GitFileChange) -> bool:
        path = change.new_path or change.old_path
        if not path:
            return False
        detected = self.detector.detect(path)
        return not detected.excluded and detected.language is not None

    def _link_current_symbols(self, session: Session, repository: Repository) -> None:
        if repository.history_indexed_through_sha != repository.head_sha:
            return
        lineages = list(
            session.scalars(
                select(SymbolLineage).where(
                    SymbolLineage.repository_id == repository.id,
                    SymbolLineage.is_deleted.is_(False),
                )
            )
        )
        lookup = {
            (item.current_file_path, item.symbol_kind, item.current_qualified_name): item.id
            for item in lineages
        }
        for symbol in session.scalars(
            select(CodeSymbol).where(CodeSymbol.repository_id == repository.id)
        ):
            from app.db.models import RepositoryFile

            file = session.get(RepositoryFile, symbol.file_id)
            symbol.lineage_id = lookup.get(
                (file.path if file else None, symbol.kind, symbol.qualified_name)
            )

    def index_repository(
        self,
        session: Session,
        repository: Repository,
        job: AnalysisJob,
        git: GitService | None = None,
    ) -> None:
        git = git or GitService(self.settings)
        if not repository.head_sha:
            raise IngestionError("HISTORY_NOT_INDEXED", "Git history must be indexed first.", 409)
        path = git.storage.path(repository.id)
        if not path.exists():
            raise IngestionError(
                "HISTORY_NOT_INDEXED", "The local Git object cache is unavailable.", 409
            )
        started = time.monotonic()
        all_shas = git.get_commits(path, repository.head_sha)
        repository.history_total_commit_count = len(all_shas)
        limited_by_commits = len(all_shas) > self.settings.max_history_commits
        selected_shas = all_shas[-self.settings.max_history_commits :]
        full_rebuild = (
            repository.history_stale
            or repository.history_indexed_through_sha not in all_shas
            or repository.history_index_status in {"not_indexed", "failed"}
        )
        if full_rebuild:
            self._clear(session, repository.id)
            repository.history_indexed_through_sha = None
            repository.history_indexed_commit_count = 0
            session.flush()
        elif repository.history_indexed_through_sha:
            position = all_shas.index(repository.history_indexed_through_sha)
            selected_shas = all_shas[position + 1 :]
            limited_by_commits = repository.history_limited
        commit_rows = list(
            session.scalars(
                select(Commit).where(
                    Commit.repository_id == repository.id, Commit.sha.in_(all_shas)
                )
            )
        )
        commits_by_sha = {item.sha: item for item in commit_rows}
        order = {
            commits_by_sha[sha].id: index
            for index, sha in enumerate(all_shas)
            if sha in commits_by_sha
        }
        active_files, active_symbols, deleted_symbols = self._load_state(
            session, repository.id, order
        )
        repository.history_index_status = "indexing"
        repository.history_stale = False
        repository.history_limited = limited_by_commits
        job.current_step = "preparing_commit_history"
        job.progress = 5
        session.commit()

        files_processed = 0
        processed_base = repository.history_indexed_commit_count
        for index, sha in enumerate(selected_shas):
            if time.monotonic() - started > self.settings.max_history_index_time_seconds:
                repository.history_limited = True
                break
            commit = commits_by_sha.get(sha)
            if commit is None:
                raise IngestionError(
                    "COMMIT_NOT_INDEXED", "A historical commit is not indexed.", 409
                )
            baseline = full_rebuild and limited_by_commits and index == 0
            all_changes = (
                self._baseline_changes(git.list_tracked_files(path, sha))
                if baseline
                else self._stored_changes(session, commit.id)
            )
            changes = [change for change in all_changes if self._relevant_change(change)]
            if files_processed + len(changes) > self.settings.max_historical_files:
                repository.history_limited = True
                break
            contexts: list[FileContext] = []
            for change in changes:
                try:
                    context = self._file_context(
                        session,
                        repository.id,
                        commit,
                        path,
                        git,
                        change,
                        active_files,
                        active_symbols,
                    )
                except IngestionError as error:
                    if error.code in {"FILE_TOO_LARGE", "HISTORICAL_SOURCE_TOO_LARGE"}:
                        continue
                    raise
                if context:
                    contexts.append(context)
            self._persist_contexts(
                session,
                repository.id,
                commit,
                contexts,
                active_files,
                active_symbols,
                deleted_symbols,
            )
            files_processed += len(changes)
            repository.history_indexed_through_sha = sha
            repository.history_indexed_commit_count = processed_base + index + 1
            job.current_step = "building_symbol_lineages"
            job.progress = 15 + 80 * (index + 1) / max(1, len(selected_shas))
            session.commit()

        self._link_current_symbols(session, repository)
        repository.history_index_status = "limited" if repository.history_limited else "ready"
        job.current_step = "finalizing_timelines"
        job.progress = 100
        session.commit()
        logger.info(
            "historical_index_completed",
            extra={"repository_id": repository.id, "job_id": job.id},
        )

    @staticmethod
    def counts(session: Session, repository_id: UUID) -> tuple[int, int, int]:
        return (
            session.scalar(
                select(func.count())
                .select_from(SymbolLineage)
                .where(SymbolLineage.repository_id == repository_id)
            )
            or 0,
            session.scalar(
                select(func.count())
                .select_from(SymbolVersion)
                .where(SymbolVersion.repository_id == repository_id)
            )
            or 0,
            session.scalar(
                select(func.count())
                .select_from(SymbolChangeEvent)
                .where(SymbolChangeEvent.repository_id == repository_id)
            )
            or 0,
        )


def index_historical_repository(
    engine: Engine, repository_id: UUID, job_id: UUID, git: GitService | None = None
) -> None:
    git = git or GitService()
    lock_key = int.from_bytes(repository_id.bytes[:8], signed=True)
    with engine.connect() as lock_connection:
        acquired = lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
        )
        lock_connection.commit()
        if not acquired:
            return
        try:
            with Session(engine, expire_on_commit=False) as session:
                job = session.get(AnalysisJob, job_id)
                repository = session.get(Repository, repository_id)
                if (
                    job is None
                    or repository is None
                    or job.repository_id != repository_id
                    or job.status in {JobStatus.completed, JobStatus.failed}
                ):
                    return
                try:
                    job.status = JobStatus.running
                    job.started_at = job.started_at or datetime.now(UTC)
                    job.error_message = None
                    repository.status = RepositoryStatus.indexing_history
                    repository.history_index_status = "indexing"
                    session.commit()
                    HistoricalIndexService(git.settings).index_repository(
                        session, repository, job, git
                    )
                    now = datetime.now(UTC)
                    repository.status = RepositoryStatus.ready
                    repository.indexing_error = None
                    job.status = JobStatus.completed
                    job.current_step = "completed"
                    job.progress = None
                    job.completed_at = now
                    session.commit()
                except Exception as error:
                    session.rollback()
                    message = (
                        error.message
                        if isinstance(error, IngestionError)
                        else "Historical indexing failed. Retry the history index."
                    )
                    repository.status = RepositoryStatus.ready
                    repository.history_index_status = "failed"
                    job.status = JobStatus.failed
                    job.error_message = message
                    job.completed_at = datetime.now(UTC)
                    job.progress = None
                    session.commit()
                    logger.exception(
                        "historical_index_failed",
                        extra={"repository_id": repository_id, "job_id": job_id},
                    )
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            lock_connection.commit()
