from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LanguageStats(BaseModel):
    language: str
    files: int
    lines: int
    percentage: float


class CodeStats(BaseModel):
    total_files: int
    source_files: int
    parsed_files: int
    unsupported_files: int
    failed_files: int
    total_lines: int
    symbol_count: int
    functions: int
    classes: int
    methods: int
    languages: list[LanguageStats]


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    path: str
    filename: str
    extension: str
    language: str | None
    blob_sha: str
    size_bytes: int
    line_count: int | None
    is_binary: bool
    parse_status: str
    syntax_error_count: int
    indexed_commit_sha: str


class FileTreeNode(BaseModel):
    name: str
    path: str
    type: Literal["directory", "file"]
    language: str | None = None
    size_bytes: int | None = None
    parse_status: str | None = None
    children: list["FileTreeNode"] = Field(default_factory=list)


class FileContent(BaseModel):
    path: str
    content: str
    start_line: int
    end_line: int
    total_lines: int
    truncated: bool


class SymbolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    file_id: UUID
    parent_symbol_id: UUID | None
    lineage_id: UUID | None
    name: str
    qualified_name: str
    kind: str
    signature: str | None
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    visibility: str | None
    is_async: bool
    is_static: bool
    documentation: str | None
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="metadata_json")
    file_path: str | None = None
    language: str | None = None


class SymbolPage(BaseModel):
    items: list[SymbolRead]
    page: int
    page_size: int
    total: int


class ImportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_file_id: UUID
    target_file_id: UUID | None
    module: str
    imported_name: str | None
    alias: str | None
    import_type: str
    resolved: bool
    source_path: str | None = None
    target_path: str | None = None


class ImportPage(BaseModel):
    items: list[ImportRead]
    page: int
    page_size: int
    total: int


class SymbolDetail(SymbolRead):
    parent: SymbolRead | None
    children: list[SymbolRead]
    imports: list[ImportRead]
