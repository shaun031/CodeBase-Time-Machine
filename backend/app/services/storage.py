import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.core.ingestion_errors import IngestionError


class RepositoryStorage:
    def __init__(self, root: Path | None = None) -> None:
        configured = root if root is not None else get_settings().repository_storage_path
        self.root = configured.absolute()

    def path(self, repository_id: UUID, temporary: bool = False) -> Path:
        path = self.root / str(UUID(str(repository_id))) / ("repo.tmp" if temporary else "repo")
        return self.validate(path)

    def validate(self, path: Path) -> Path:
        root = self.root.resolve()
        if not path.resolve().is_relative_to(root) or path.resolve() == root:
            raise IngestionError("UNSAFE_STORAGE_PATH", "Repository storage path is unsafe.", 500)
        relative = path.relative_to(self.root)
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink() or current.is_junction():
                raise IngestionError(
                    "UNSAFE_STORAGE_PATH", "Repository storage path is unsafe.", 500
                )
        return path

    def remove_temporary(self, repository_id: UUID) -> None:
        path = self.path(repository_id, temporary=True)
        if path.exists():
            self._remove_tree(path)

    def remove_repository(self, repository_id: UUID) -> None:
        path = self.path(repository_id)
        if path.exists():
            self._remove_tree(path)

    def _remove_tree(self, path: Path) -> None:
        """Remove a repository tree, including read-only Git objects on Windows."""

        def make_writable_and_retry(
            function: Callable[..., object], failed_path: str, _error: BaseException
        ) -> None:
            Path(failed_path).chmod(stat.S_IWRITE)
            function(failed_path)

        shutil.rmtree(self.validate(path), onexc=make_writable_and_retry)

    def size(self, path: Path) -> int:
        total = 0
        if path.exists():
            for entry in path.rglob("*"):
                if entry.is_symlink() or entry.is_junction():
                    raise IngestionError("UNSAFE_STORAGE_PATH", "Unexpected storage link detected.")
                try:
                    if entry.is_file():
                        total += entry.stat().st_size
                except FileNotFoundError:
                    pass  # Git can atomically rename a pack during a size scan.
        return total
