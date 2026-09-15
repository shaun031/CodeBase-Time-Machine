from pathlib import PurePosixPath
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import Repository, RepositoryFile, RepositoryStatus
from app.schemas.code import FileContent, FileRead, FileTreeNode
from app.services.git import GitService


class FileService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    @staticmethod
    def validate_repository_path(value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            not value
            or path.is_absolute()
            or normalized.startswith("/")
            or len(normalized) >= 2
            and normalized[1] == ":"
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise IngestionError(
                "INVALID_FILE_PATH", "File path must stay inside the indexed repository.", 422
            )
        return path.as_posix()

    def _ready(self, repository_id: UUID) -> Repository:
        repository = self.session.get(Repository, repository_id)
        if repository is None:
            raise IngestionError("REPOSITORY_NOT_FOUND", "Repository not found.", 404)
        if repository.status == RepositoryStatus.failed:
            raise IngestionError(
                "CODE_INDEX_FAILED", "Code indexing failed. Retry the code index.", 409
            )
        if repository.status != RepositoryStatus.ready:
            raise IngestionError("CODE_INDEX_NOT_READY", "Wait for code indexing to finish.", 409)
        return repository

    def get_file(self, repository_id: UUID, path: str) -> RepositoryFile:
        self._ready(repository_id)
        safe = self.validate_repository_path(path)
        item = self.session.scalar(
            select(RepositoryFile).where(
                RepositoryFile.repository_id == repository_id, RepositoryFile.path == safe
            )
        )
        if item is None:
            raise IngestionError(
                "FILE_NOT_FOUND", "File not found in the indexed repository snapshot.", 404
            )
        return item

    def get_file_tree(
        self, repository_id: UUID, directory: str | None = None
    ) -> list[FileTreeNode]:
        self._ready(repository_id)
        prefix = ""
        if directory:
            prefix = self.validate_repository_path(directory).rstrip("/") + "/"
        files = list(
            self.session.scalars(
                select(RepositoryFile)
                .where(
                    RepositoryFile.repository_id == repository_id,
                    RepositoryFile.path.startswith(prefix),
                )
                .order_by(RepositoryFile.path)
            )
        )
        roots: dict[str, dict] = {}
        for item in files:
            relative = item.path[len(prefix) :]
            parts = PurePosixPath(relative).parts
            if not parts:
                continue
            level = roots
            current: list[str] = [] if not directory else list(PurePosixPath(directory).parts)
            for position, part in enumerate(parts):
                current.append(part)
                is_file = position == len(parts) - 1
                node = level.setdefault(
                    part,
                    {
                        "name": part,
                        "path": "/".join(current),
                        "type": "file" if is_file else "directory",
                        "language": item.language if is_file else None,
                        "size_bytes": item.size_bytes if is_file else None,
                        "parse_status": item.parse_status if is_file else None,
                        "children": {},
                    },
                )
                level = node["children"]

        def serialize(values: dict[str, dict]) -> list[FileTreeNode]:
            ordered = sorted(
                values.values(), key=lambda value: (value["type"] == "file", value["name"].lower())
            )
            return [
                FileTreeNode(**{**value, "children": serialize(value["children"])})
                for value in ordered
            ]

        return serialize(roots)

    def get_content(
        self, repository_id: UUID, path: str, start_line: int | None, end_line: int | None
    ) -> FileContent:
        repository = self._ready(repository_id)
        item = self.get_file(repository_id, path)
        if item.is_binary:
            raise IngestionError("BINARY_FILE", "Binary file contents cannot be displayed.", 415)
        if item.size_bytes > self.settings.max_source_file_size_bytes:
            raise IngestionError("FILE_TOO_LARGE", "File is too large to display.", 413)
        content = (
            GitService(self.settings)
            .get_blob(
                GitService(self.settings).storage.path(repository.id),
                item.blob_sha,
                item.size_bytes,
            )
            .decode("utf-8", "replace")
        )
        lines = content.splitlines(keepends=True)
        total = len(lines)
        if total == 0:
            return FileContent(
                path=item.path,
                content="",
                start_line=1,
                end_line=1,
                total_lines=0,
                truncated=False,
            )
        start = start_line or 1
        end = end_line or total
        if end < start:
            raise IngestionError(
                "INVALID_LINE_RANGE", "end_line must be greater than or equal to start_line.", 422
            )
        selected = "".join(lines[start - 1 : end])
        return FileContent(
            path=item.path,
            content=selected,
            start_line=start,
            end_line=min(end, total),
            total_lines=total,
            truncated=start > 1 or end < total,
        )

    @staticmethod
    def read(item: RepositoryFile) -> FileRead:
        return FileRead.model_validate(item)
