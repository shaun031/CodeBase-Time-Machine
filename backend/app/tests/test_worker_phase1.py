from uuid import UUID, uuid4

from app.workers.celery_app import celery_app
from app.workers.tasks import repository


def test_repository_task_registered_and_passes_internal_ids(monkeypatch):
    calls = []
    engine = object()
    monkeypatch.setattr(repository, "get_engine", lambda: engine)
    monkeypatch.setattr(repository, "index_repository", lambda *args: calls.append(args))
    repo_id, job_id = str(uuid4()), str(uuid4())
    celery_app.loader.import_default_modules()
    assert "analyze_repository" in celery_app.tasks
    repository.analyze_repository.apply(args=[repo_id, job_id]).get()
    assert calls == [(engine, UUID(repo_id), UUID(job_id))]
