import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AnalysisJob, JobStatus, Repository, RepositoryStatus
from app.schemas.analysis_job import AnalysisJobRead
from app.schemas.repository import RepositoryRead


@pytest.fixture
def db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run real PostgreSQL integration tests")
    if not url.startswith("postgresql+psycopg://"):
        pytest.fail("Integration tests require PostgreSQL with psycopg")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
    engine.dispose()


@pytest.mark.integration
def test_database_and_pgvector(db):
    assert db.scalar(text("SELECT 1")) == 1
    assert db.scalar(text("SELECT extname FROM pg_extension WHERE extname='vector'")) == "vector"


@pytest.mark.integration
def test_models_round_trip(db):
    name = f"phase0-{uuid4().hex}"
    repo = Repository(
        owner="test", name=name, full_name=f"test/{name}", url=f"https://github.com/test/{name}"
    )
    db.add(repo)
    db.flush()
    job = AnalysisJob(repository_id=repo.id, job_type="health")
    db.add(job)
    db.flush()
    db.expire_all()
    assert isinstance(repo.id, UUID)
    assert repo.status is RepositoryStatus.pending
    assert repo.created_at.tzinfo is not None
    assert job.status is JobStatus.queued
    assert job.progress is None
    assert RepositoryRead.model_validate(repo).full_name == f"test/{name}"
    assert AnalysisJobRead.model_validate(job).repository_id == repo.id
    db.delete(repo)
    db.flush()
    db.expire(job)
    assert job.repository_id is None


@pytest.mark.integration
def test_invalid_progress_is_rejected(db):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(AnalysisJob(job_type="health", progress=101))
        db.flush()


def test_model_metadata():
    assert Repository.__table__.c.id.type.python_type is UUID
    assert AnalysisJob.__table__.c.id.type.python_type is UUID
    assert AnalysisJob.__table__.c.progress.nullable
    assert {index.name for index in Repository.__table__.indexes} == {
        "ix_repositories_full_name",
        "ix_repositories_history_index_status",
        "ix_repositories_status",
    }
    assert len(RepositoryStatus) == 9
    assert len(JobStatus) == 4
