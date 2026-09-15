"""Add current-snapshot static analysis storage."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_static_analysis"
down_revision = "0002_git_history"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "repository_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("extension", sa.String(50), nullable=False, server_default=""),
        sa.Column("language", sa.String(50)),
        sa.Column("blob_sha", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("line_count", sa.Integer()),
        sa.Column("is_binary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("parse_status", sa.String(30), nullable=False),
        sa.Column("syntax_error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indexed_commit_sha", sa.String(40), nullable=False),
        sa.UniqueConstraint("repository_id", "path"),
        *timestamps(),
    )
    for name in [
        "repository_id",
        "path",
        "language",
        "blob_sha",
        "parse_status",
        "indexed_commit_sha",
    ]:
        op.create_index(f"ix_repository_files_{name}", "repository_files", [name])
    op.create_index(
        "ix_repository_files_repository_path", "repository_files", ["repository_id", "path"]
    )
    op.create_table(
        "code_symbols",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            sa.Uuid(),
            sa.ForeignKey("repository_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="CASCADE")
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("signature", sa.Text()),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("start_column", sa.Integer(), nullable=False),
        sa.Column("end_column", sa.Integer(), nullable=False),
        sa.Column("visibility", sa.String(30)),
        sa.Column("is_async", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_static", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("documentation", sa.Text()),
        sa.Column("metadata", postgresql.JSONB()),
        *timestamps(),
    )
    for name in ["repository_id", "file_id", "parent_symbol_id", "kind"]:
        op.create_index(f"ix_code_symbols_{name}", "code_symbols", [name])
    op.create_index("ix_code_symbols_repository_name", "code_symbols", ["repository_id", "name"])
    op.create_index(
        "ix_code_symbols_repository_qualified", "code_symbols", ["repository_id", "qualified_name"]
    )
    op.create_table(
        "code_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_file_id",
            sa.Uuid(),
            sa.ForeignKey("repository_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_file_id", sa.Uuid(), sa.ForeignKey("repository_files.id", ondelete="SET NULL")
        ),
        sa.Column("module", sa.Text(), nullable=False),
        sa.Column("imported_name", sa.Text()),
        sa.Column("alias", sa.Text()),
        sa.Column("import_type", sa.String(30), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for name in ["repository_id", "source_file_id", "target_file_id", "resolved"]:
        op.create_index(f"ix_code_imports_{name}", "code_imports", [name])
    op.create_table(
        "file_parse_errors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            sa.Uuid(),
            sa.ForeignKey("repository_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("error_type", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_file_parse_errors_repository_id", "file_parse_errors", ["repository_id"])
    op.create_index("ix_file_parse_errors_file_id", "file_parse_errors", ["file_id"])


def downgrade() -> None:
    for table in ["file_parse_errors", "code_imports", "code_symbols", "repository_files"]:
        op.drop_table(table)
