import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (UniqueConstraint("repository_id", "sha"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    sha: Mapped[str] = mapped_column(String(40), index=True)
    short_sha: Mapped[str] = mapped_column(String(12))
    message: Mapped[str] = mapped_column(Text)
    author_name: Mapped[str] = mapped_column(Text)
    author_email: Mapped[str] = mapped_column(Text)
    committer_name: Mapped[str] = mapped_column(Text)
    committer_email: Mapped[str] = mapped_column(Text)
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_merge_commit: Mapped[bool]
    insertions: Mapped[int]
    deletions: Mapped[int]
    files_changed: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommitParent(Base):
    __tablename__ = "commit_parents"
    __table_args__ = (UniqueConstraint("commit_id", "parent_order"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), index=True
    )
    parent_sha: Mapped[str] = mapped_column(String(40))
    parent_order: Mapped[int]
