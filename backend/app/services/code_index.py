import logging
from collections import defaultdict
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AnalysisJob,
    CodeImport,
    CodeSymbol,
    FileParseError,
    Repository,
    RepositoryFile,
    RepositoryStatus,
)
from app.parsers.models import ParseResult
from app.parsers.registry import ParserRegistry
from app.schemas.code import CodeStats, LanguageStats
from app.services.git import GitService, GitTreeEntry
from app.services.import_resolver import ImportResolver
from app.services.language_detector import LanguageDetector

logger = logging.getLogger("ctm")


class CodeIndexService:
    def __init__(
        self, settings: Settings | None = None, registry: ParserRegistry | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or ParserRegistry()
        self.detector = LanguageDetector()
        self.resolver = ImportResolver()

    @staticmethod
    def _safe_path(value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            not value
            or path.is_absolute()
            or (len(normalized) >= 2 and normalized[1] == ":")
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise IngestionError(
                "INVALID_FILE_PATH", "File path must be a safe repository-relative path.", 422
            )
        return path.as_posix()

    def _analyze(
        self,
        git: GitService,
        repo_path: Path,
        entry: GitTreeEntry,
        language: str | None,
    ) -> tuple[bool, str, int | None, ParseResult | None]:
        if entry.mode == "120000" or entry.object_type != "blob":
            return False, "excluded", None, None
        if entry.size_bytes > self.settings.max_source_file_size_bytes:
            return False, "too_large", None, None
        detection = self.detector.detect(entry.path)
        if detection.binary_by_extension:
            return True, "binary", None, None
        content = git.get_blob(repo_path, entry.blob_sha, entry.size_bytes)
        if self.detector.is_binary(content):
            return True, "binary", None, None
        line_count = len(content.decode("utf-8", "replace").splitlines())
        parser = self.registry.get(language)
        if parser is None:
            return False, "unsupported", line_count, None
        result = parser.parse(content, self.settings.max_parse_time_per_file_seconds)
        return False, "parsed" if result.parse_success else "failed", line_count, result

    def index_repository(
        self, session: Session, repository: Repository, job: AnalysisJob, git: GitService
    ) -> None:
        if not repository.head_sha:
            session.execute(
                delete(RepositoryFile).where(RepositoryFile.repository_id == repository.id)
            )
            return
        repository.status = RepositoryStatus.indexing_code
        job.current_step = "enumerating_repository_files"
        job.progress = 30
        session.commit()
        repo_path = git.storage.path(repository.id)
        entries = git.list_tracked_files(repo_path, repository.head_sha)
        entries = [entry for entry in entries if not self.detector.detect(entry.path).excluded]
        incoming_paths = {self._safe_path(entry.path) for entry in entries}
        existing = list(
            session.scalars(
                select(RepositoryFile).where(RepositoryFile.repository_id == repository.id)
            )
        )
        by_path = {item.path: item for item in existing}
        rename_pool: dict[str, list[RepositoryFile]] = defaultdict(list)
        for existing_file in existing:
            if existing_file.path not in incoming_paths:
                rename_pool[existing_file.blob_sha].append(existing_file)
        retained: set[UUID] = set()
        job.current_step = "parsing_source_files"
        session.commit()
        total = max(1, len(entries))
        for index, entry in enumerate(entries):
            safe_path = self._safe_path(entry.path)
            detection = self.detector.detect(safe_path)
            item: RepositoryFile | None = by_path.get(safe_path)
            if item is None and rename_pool.get(entry.blob_sha):
                item = rename_pool[entry.blob_sha].pop(0)
                item.path = safe_path
            if item is not None:
                retained.add(item.id)
            if item is not None and item.blob_sha == entry.blob_sha:
                item.filename = PurePosixPath(safe_path).name
                item.extension = PurePosixPath(safe_path).suffix.lower()
                item.language = detection.language
                item.size_bytes = entry.size_bytes
                item.indexed_commit_sha = repository.head_sha
            else:
                if item is None:
                    item = RepositoryFile(id=uuid4(), repository_id=repository.id, path=safe_path)
                    session.add(item)
                else:
                    session.execute(delete(CodeImport).where(CodeImport.source_file_id == item.id))
                    session.execute(delete(CodeSymbol).where(CodeSymbol.file_id == item.id))
                    session.execute(delete(FileParseError).where(FileParseError.file_id == item.id))
                item.filename = PurePosixPath(safe_path).name
                item.extension = PurePosixPath(safe_path).suffix.lower()
                item.language = detection.language
                item.blob_sha = entry.blob_sha
                item.size_bytes = entry.size_bytes
                item.indexed_commit_sha = repository.head_sha
                try:
                    (
                        item.is_binary,
                        item.parse_status,
                        item.line_count,
                        result,
                    ) = self._analyze(git, repo_path, entry, detection.language)
                except Exception:
                    logger.warning(
                        "source_file_parse_failed", extra={"repository_id": repository.id}
                    )
                    item.is_binary = False
                    item.parse_status = "failed"
                    item.line_count = None
                    result = ParseResult(
                        parse_success=False,
                        error_message="Static parser could not process this file.",
                    )
                item.syntax_error_count = result.syntax_error_count if result else 0
                session.flush()
                if result:
                    symbol_ids = [uuid4() for _ in result.symbols]
                    session.add_all(
                        [
                            CodeSymbol(
                                id=symbol_ids[position],
                                repository_id=repository.id,
                                file_id=item.id,
                                parent_symbol_id=(
                                    symbol_ids[symbol.parent_index]
                                    if symbol.parent_index is not None
                                    else None
                                ),
                                name=symbol.name,
                                qualified_name=symbol.qualified_name,
                                kind=symbol.kind,
                                signature=symbol.signature,
                                start_line=symbol.start_line,
                                end_line=symbol.end_line,
                                start_column=symbol.start_column,
                                end_column=symbol.end_column,
                                visibility=symbol.visibility,
                                is_async=symbol.is_async,
                                is_static=symbol.is_static,
                                documentation=symbol.documentation,
                                metadata_json=symbol.metadata,
                            )
                            for position, symbol in enumerate(result.symbols)
                        ]
                    )
                    session.add_all(
                        [
                            CodeImport(
                                repository_id=repository.id,
                                source_file_id=item.id,
                                module=value.module,
                                imported_name=value.imported_name,
                                alias=value.alias,
                                import_type=value.import_type,
                            )
                            for value in result.imports
                        ]
                    )
                    if not result.parse_success:
                        session.add(
                            FileParseError(
                                repository_id=repository.id,
                                file_id=item.id,
                                error_type="PARSE_FAILED",
                                message=result.error_message or "Static parsing failed.",
                            )
                        )
            if (index + 1) % 100 == 0:
                job.progress = 40 + (index + 1) / total * 40
                session.commit()
        delete_ids = [item.id for item in existing if item.id not in retained]
        if delete_ids:
            session.execute(delete(RepositoryFile).where(RepositoryFile.id.in_(delete_ids)))
        session.flush()
        job.current_step = "resolving_imports"
        job.progress = 85
        session.commit()
        files = {
            path: file_id
            for path, file_id in session.execute(
                select(RepositoryFile.path, RepositoryFile.id).where(
                    RepositoryFile.repository_id == repository.id
                )
            )
        }
        imports = session.execute(
            select(CodeImport, RepositoryFile.path, RepositoryFile.language)
            .join(RepositoryFile, CodeImport.source_file_id == RepositoryFile.id)
            .where(CodeImport.repository_id == repository.id)
        )
        for imported, source_path, language in imports:
            target = self.resolver.resolve(source_path, imported.module, language, files)
            imported.target_file_id = target
            imported.resolved = target is not None
        session.execute(
            update(RepositoryFile)
            .where(RepositoryFile.repository_id == repository.id)
            .values(indexed_commit_sha=repository.head_sha)
        )
        job.current_step = "saving_code_index"
        job.progress = 95
        session.commit()

    @staticmethod
    def calculate_repository_code_stats(session: Session, repository_id: UUID) -> CodeStats:
        repository = session.get(Repository, repository_id)
        if repository is None:
            raise IngestionError("REPOSITORY_NOT_FOUND", "Repository not found.", 404)
        if repository.status != RepositoryStatus.ready:
            code = (
                "CODE_INDEX_FAILED"
                if repository.status == RepositoryStatus.failed
                else "CODE_INDEX_NOT_READY"
            )
            raise IngestionError(code, "The current code index is not available.", 409)
        row = session.execute(
            select(
                func.count(RepositoryFile.id),
                func.count(RepositoryFile.id).filter(RepositoryFile.language.is_not(None)),
                func.count(RepositoryFile.id).filter(RepositoryFile.parse_status == "parsed"),
                func.count(RepositoryFile.id).filter(RepositoryFile.parse_status == "unsupported"),
                func.count(RepositoryFile.id).filter(RepositoryFile.parse_status == "failed"),
                func.coalesce(func.sum(RepositoryFile.line_count), 0),
            ).where(RepositoryFile.repository_id == repository_id)
        ).one()
        symbol_row = session.execute(
            select(
                func.count(CodeSymbol.id),
                func.count(CodeSymbol.id).filter(CodeSymbol.kind == "function"),
                func.count(CodeSymbol.id).filter(CodeSymbol.kind == "class"),
                func.count(CodeSymbol.id).filter(CodeSymbol.kind.in_(("method", "constructor"))),
            ).where(CodeSymbol.repository_id == repository_id)
        ).one()
        language_query = (
            select(
                RepositoryFile.language,
                func.count(RepositoryFile.id),
                func.coalesce(func.sum(RepositoryFile.line_count), 0),
            )
            .where(
                RepositoryFile.repository_id == repository_id,
                RepositoryFile.language.is_not(None),
            )
            .group_by(RepositoryFile.language)
            .order_by(func.count(RepositoryFile.id).desc(), RepositoryFile.language)
        )
        language_rows = list(session.execute(language_query))
        source_lines = sum(int(value[2]) for value in language_rows)
        languages = [
            LanguageStats(
                language=language,
                files=files,
                lines=lines,
                percentage=round(lines / source_lines * 100, 1) if source_lines else 0,
            )
            for language, files, lines in language_rows
        ]
        return CodeStats(
            total_files=row[0],
            source_files=row[1],
            parsed_files=row[2],
            unsupported_files=row[3],
            failed_files=row[4],
            total_lines=row[5],
            symbol_count=symbol_row[0],
            functions=symbol_row[1],
            classes=symbol_row[2],
            methods=symbol_row[3],
            languages=languages,
        )
