"""Add read-only GitHub development context storage."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_github_context"
down_revision = "0004_historical_lineage"
branch_labels = None
depends_on = None


def uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), primary_key=True)


def repo_fk() -> sa.Column:
    return sa.Column(
        "repository_id",
        sa.Uuid(),
        sa.ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "github_repository_metadata",
        uuid_pk(),
        repo_fk(),
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(511), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("default_branch", sa.String(255)),
        sa.Column("html_url", sa.Text(), nullable=False),
        sa.Column("homepage", sa.Text()),
        sa.Column("language", sa.String(100)),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("forks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_issues_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fork", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("github_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("github_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pushed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("repository_id"),
    )
    op.create_index(
        "ix_github_repository_metadata_repository_id",
        "github_repository_metadata",
        ["repository_id"],
    )
    op.create_index(
        "ix_github_repository_metadata_github_repository_id",
        "github_repository_metadata",
        ["github_repository_id"],
    )

    op.create_table(
        "github_users",
        uuid_pk(),
        sa.Column("github_user_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.Text()),
        sa.Column("html_url", sa.Text()),
        sa.Column("user_type", sa.String(50), nullable=False, server_default="User"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("github_user_id"),
    )
    op.create_index("ix_github_users_github_user_id", "github_users", ["github_user_id"])
    op.create_index("ix_github_users_login", "github_users", ["login"])

    op.create_table(
        "github_pull_requests",
        uuid_pk(),
        repo_fk(),
        sa.Column("github_pr_id", sa.BigInteger(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("draft", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("merged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("merged_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("github_users.id", ondelete="SET NULL")),
        sa.Column("author_login", sa.String(255)),
        sa.Column("merge_commit_sha", sa.String(40)),
        sa.Column("base_branch", sa.Text(), nullable=False),
        sa.Column("head_branch", sa.Text(), nullable=False),
        sa.Column("additions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deletions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("commits_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_comments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("html_url", sa.Text(), nullable=False),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "repository_id", "github_pr_id", name="uq_github_pull_requests_repo_github_id"
        ),
        sa.UniqueConstraint("repository_id", "number", name="uq_github_pull_requests_repo_number"),
    )
    for column in [
        "repository_id",
        "state",
        "updated_at",
        "author_id",
        "author_login",
        "merge_commit_sha",
    ]:
        op.create_index(f"ix_github_pull_requests_{column}", "github_pull_requests", [column])
    op.create_index(
        "ix_github_pull_requests_repo_state",
        "github_pull_requests",
        ["repository_id", "state"],
    )

    op.create_table(
        "github_issues",
        uuid_pk(),
        repo_fk(),
        sa.Column("github_issue_id", sa.BigInteger(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("github_users.id", ondelete="SET NULL")),
        sa.Column("author_login", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("html_url", sa.Text(), nullable=False),
        sa.Column("comments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("milestone", sa.Text()),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "repository_id", "github_issue_id", name="uq_github_issues_repo_github_id"
        ),
        sa.UniqueConstraint("repository_id", "number", name="uq_github_issues_repo_number"),
    )
    for column in ["repository_id", "state", "updated_at", "author_id", "author_login"]:
        op.create_index(f"ix_github_issues_{column}", "github_issues", [column])
    op.create_index("ix_github_issues_repo_state", "github_issues", ["repository_id", "state"])

    op.create_table(
        "github_labels",
        uuid_pk(),
        repo_fk(),
        sa.Column("github_label_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("color", sa.String(12)),
        sa.UniqueConstraint(
            "repository_id", "github_label_id", name="uq_github_labels_repo_github_id"
        ),
        sa.UniqueConstraint("repository_id", "name", name="uq_github_labels_repo_name"),
    )
    op.create_index("ix_github_labels_repository_id", "github_labels", ["repository_id"])
    op.create_index("ix_github_labels_name", "github_labels", ["name"])

    op.create_table(
        "github_pr_labels",
        uuid_pk(),
        sa.Column(
            "pull_request_id",
            sa.Uuid(),
            sa.ForeignKey("github_pull_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "label_id",
            sa.Uuid(),
            sa.ForeignKey("github_labels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("pull_request_id", "label_id"),
    )
    op.create_index("ix_github_pr_labels_pull_request_id", "github_pr_labels", ["pull_request_id"])
    op.create_index("ix_github_pr_labels_label_id", "github_pr_labels", ["label_id"])
    op.create_table(
        "github_issue_labels",
        uuid_pk(),
        sa.Column(
            "issue_id",
            sa.Uuid(),
            sa.ForeignKey("github_issues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "label_id",
            sa.Uuid(),
            sa.ForeignKey("github_labels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("issue_id", "label_id"),
    )
    op.create_index("ix_github_issue_labels_issue_id", "github_issue_labels", ["issue_id"])
    op.create_index("ix_github_issue_labels_label_id", "github_issue_labels", ["label_id"])

    op.create_table(
        "github_comments",
        uuid_pk(),
        sa.Column("github_comment_id", sa.BigInteger(), nullable=False),
        repo_fk(),
        sa.Column("issue_id", sa.Uuid(), sa.ForeignKey("github_issues.id", ondelete="CASCADE")),
        sa.Column(
            "pull_request_id",
            sa.Uuid(),
            sa.ForeignKey("github_pull_requests.id", ondelete="CASCADE"),
        ),
        sa.Column("comment_type", sa.String(30), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("github_users.id", ondelete="SET NULL")),
        sa.Column("author_login", sa.String(255)),
        sa.Column("body", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("html_url", sa.Text(), nullable=False),
        sa.Column("path", sa.Text()),
        sa.Column("commit_sha", sa.String(40)),
        sa.Column("original_commit_sha", sa.String(40)),
        sa.Column("line", sa.Integer()),
        sa.Column("original_line", sa.Integer()),
        sa.Column("side", sa.String(10)),
        sa.Column("diff_hunk", sa.Text()),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("repository_id", "github_comment_id", "comment_type"),
    )
    for column in [
        "repository_id",
        "issue_id",
        "pull_request_id",
        "comment_type",
        "author_id",
    ]:
        op.create_index(f"ix_github_comments_{column}", "github_comments", [column])
    op.create_index(
        "ix_github_comments_pr_type",
        "github_comments",
        ["pull_request_id", "comment_type"],
    )
    op.create_index(
        "ix_github_comments_issue_type",
        "github_comments",
        ["issue_id", "comment_type"],
    )

    op.create_table(
        "github_pr_commits",
        uuid_pk(),
        repo_fk(),
        sa.Column(
            "pull_request_id",
            sa.Uuid(),
            sa.ForeignKey("github_pull_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("pull_request_id", "commit_sha"),
    )
    for column in ["repository_id", "pull_request_id", "commit_sha"]:
        op.create_index(f"ix_github_pr_commits_{column}", "github_pr_commits", [column])

    op.create_table(
        "commit_pr_links",
        uuid_pk(),
        repo_fk(),
        sa.Column(
            "commit_id", sa.Uuid(), sa.ForeignKey("commits.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "pull_request_id",
            sa.Uuid(),
            sa.ForeignKey("github_pull_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("link_type", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("commit_id", "pull_request_id", "link_type"),
    )
    for column in ["repository_id", "commit_id", "pull_request_id", "link_type"]:
        op.create_index(f"ix_commit_pr_links_{column}", "commit_pr_links", [column])

    op.create_table(
        "github_issue_references",
        uuid_pk(),
        repo_fk(),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column(
            "target_issue_id",
            sa.Uuid(),
            sa.ForeignKey("github_issues.id", ondelete="CASCADE"),
        ),
        sa.Column("target_owner", sa.String(255), nullable=False),
        sa.Column("target_repository", sa.String(255), nullable=False),
        sa.Column("target_number", sa.Integer(), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("raw_reference", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.UniqueConstraint(
            "repository_id",
            "source_type",
            "source_id",
            "target_owner",
            "target_repository",
            "target_number",
            "reference_type",
        ),
    )
    for column in [
        "repository_id",
        "source_type",
        "source_id",
        "target_issue_id",
        "reference_type",
    ]:
        op.create_index(f"ix_github_issue_references_{column}", "github_issue_references", [column])

    op.create_table(
        "github_sync_state",
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="not_synced"),
        sa.Column("progress", sa.Float()),
        sa.Column("current_step", sa.String(255)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_pr_updated_at", sa.DateTime(timezone=True)),
        sa.Column("last_issue_updated_at", sa.DateTime(timezone=True)),
        sa.Column("repository_etag", sa.Text()),
        sa.Column("pull_requests_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issues_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_comments_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("github_index_limited", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rate_limit_remaining", sa.Integer()),
        sa.Column("rate_limit_reset_at", sa.DateTime(timezone=True)),
        sa.Column("sync_error", sa.Text()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_github_sync_state_status", "github_sync_state", ["status"])


def downgrade() -> None:
    for table in [
        "github_sync_state",
        "github_issue_references",
        "commit_pr_links",
        "github_pr_commits",
        "github_comments",
        "github_issue_labels",
        "github_pr_labels",
        "github_labels",
        "github_issues",
        "github_pull_requests",
        "github_users",
        "github_repository_metadata",
    ]:
        op.drop_table(table)
