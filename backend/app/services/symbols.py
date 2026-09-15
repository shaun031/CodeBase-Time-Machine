from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session, aliased

from app.core.ingestion_errors import IngestionError
from app.db.models import CodeImport, CodeSymbol, RepositoryFile
from app.schemas.code import ImportPage, ImportRead, SymbolDetail, SymbolPage, SymbolRead
from app.services.files import FileService


class SymbolService:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _read(
        symbol: CodeSymbol, path: str | None = None, language: str | None = None
    ) -> SymbolRead:
        data = SymbolRead.model_validate(symbol).model_dump()
        data["file_path"] = path
        data["language"] = language
        return SymbolRead(**data)

    def for_file(self, repository_id: UUID, path: str) -> list[SymbolRead]:
        item = FileService(self.session).get_file(repository_id, path)
        symbols = self.session.scalars(
            select(CodeSymbol)
            .where(CodeSymbol.file_id == item.id)
            .order_by(CodeSymbol.start_line, CodeSymbol.start_column)
        )
        return [self._read(symbol, item.path, item.language) for symbol in symbols]

    def search(
        self,
        repository_id: UUID,
        search: str | None,
        kind: str | None,
        language: str | None,
        file: str | None,
        page: int,
        page_size: int,
    ) -> SymbolPage:
        FileService(self.session)._ready(repository_id)
        query = (
            select(CodeSymbol, RepositoryFile.path, RepositoryFile.language)
            .join(RepositoryFile)
            .where(CodeSymbol.repository_id == repository_id)
        )
        conditions: list[ColumnElement[bool]] = []
        if search:
            conditions.append(CodeSymbol.qualified_name.ilike(f"%{search}%"))
        if kind:
            conditions.append(CodeSymbol.kind == kind)
        if language:
            conditions.append(RepositoryFile.language == language)
        if file:
            conditions.append(RepositoryFile.path == FileService.validate_repository_path(file))
        query = query.where(*conditions)
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self.session.execute(
            query.order_by(CodeSymbol.qualified_name, CodeSymbol.start_line)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return SymbolPage(
            items=[self._read(symbol, path, lang) for symbol, path, lang in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    def detail(self, repository_id: UUID, symbol_id: UUID) -> SymbolDetail:
        FileService(self.session)._ready(repository_id)
        row = self.session.execute(
            select(CodeSymbol, RepositoryFile.path, RepositoryFile.language)
            .join(RepositoryFile)
            .where(CodeSymbol.repository_id == repository_id, CodeSymbol.id == symbol_id)
        ).one_or_none()
        if row is None:
            raise IngestionError("SYMBOL_NOT_FOUND", "Symbol not found.", 404)
        symbol, path, language = row
        parent = (
            self.session.get(CodeSymbol, symbol.parent_symbol_id)
            if symbol.parent_symbol_id
            else None
        )
        children = list(
            self.session.scalars(
                select(CodeSymbol)
                .where(CodeSymbol.parent_symbol_id == symbol.id)
                .order_by(CodeSymbol.start_line)
            )
        )
        imports = self._imports_for_file(symbol.file_id)
        return SymbolDetail(
            **self._read(symbol, path, language).model_dump(),
            parent=self._read(parent, path, language) if parent else None,
            children=[self._read(child, path, language) for child in children],
            imports=imports,
        )

    def _imports_for_file(self, file_id: UUID) -> list[ImportRead]:
        Target = aliased(RepositoryFile)
        rows = self.session.execute(
            select(CodeImport, RepositoryFile.path, Target.path)
            .join(RepositoryFile, CodeImport.source_file_id == RepositoryFile.id)
            .outerjoin(Target, CodeImport.target_file_id == Target.id)
            .where(CodeImport.source_file_id == file_id)
            .order_by(CodeImport.module)
        )
        return [
            ImportRead(
                **ImportRead.model_validate(item).model_dump(),
                source_path=source,
                target_path=target,
            )
            for item, source, target in rows
        ]

    def imports(
        self,
        repository_id: UUID,
        file: str | None,
        resolved: bool | None,
        page: int,
        page_size: int,
    ) -> ImportPage:
        FileService(self.session)._ready(repository_id)
        Target = aliased(RepositoryFile)
        query = (
            select(CodeImport, RepositoryFile.path, Target.path)
            .join(RepositoryFile, CodeImport.source_file_id == RepositoryFile.id)
            .outerjoin(Target, CodeImport.target_file_id == Target.id)
            .where(CodeImport.repository_id == repository_id)
        )
        if file:
            query = query.where(RepositoryFile.path == FileService.validate_repository_path(file))
        if resolved is not None:
            query = query.where(CodeImport.resolved == resolved)
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self.session.execute(
            query.order_by(RepositoryFile.path, CodeImport.module)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [
            ImportRead(
                **ImportRead.model_validate(item).model_dump(),
                source_path=source,
                target_path=target,
            )
            for item, source, target in rows
        ]
        return ImportPage(items=items, page=page, page_size=page_size, total=total)
