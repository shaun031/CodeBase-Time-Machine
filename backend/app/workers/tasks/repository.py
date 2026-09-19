from uuid import UUID

from app.db.session import get_engine
from app.services.ai.indexer import index_ai_repository
from app.services.archaeology.indexer import index_archaeology_repository
from app.services.architecture_history.indexer import index_architecture_history
from app.services.github.indexer import index_github_repository
from app.services.graph.builder import index_dependency_graph
from app.services.historical_index import index_historical_repository
from app.services.indexing import index_code_repository, index_repository
from app.services.investigation.report import build_investigation
from app.workers.celery_app import celery_app


@celery_app.task(name="analyze_repository", acks_late=True, reject_on_worker_lost=True)
def analyze_repository(repository_id: str, job_id: str) -> None:
    index_repository(get_engine(), UUID(repository_id), UUID(job_id))


@celery_app.task(name="analyze_code", acks_late=True, reject_on_worker_lost=True)
def analyze_code(repository_id: str, job_id: str) -> None:
    index_code_repository(get_engine(), UUID(repository_id), UUID(job_id))


@celery_app.task(name="analyze_history", acks_late=True, reject_on_worker_lost=True)
def analyze_history(repository_id: str, job_id: str) -> None:
    index_historical_repository(get_engine(), UUID(repository_id), UUID(job_id))


@celery_app.task(name="analyze_github", acks_late=True, reject_on_worker_lost=True)
def analyze_github(repository_id: str, job_id: str) -> None:
    index_github_repository(get_engine(), UUID(repository_id), UUID(job_id))


@celery_app.task(name="analyze_graph", acks_late=True, reject_on_worker_lost=True)
def analyze_graph(repository_id: str, job_id: str) -> None:
    index_dependency_graph(get_engine(), UUID(repository_id), UUID(job_id))


@celery_app.task(name="analyze_ai", acks_late=True, reject_on_worker_lost=True)
def analyze_ai(repository_id: str, job_id: str) -> None:
    index_ai_repository(get_engine(), UUID(repository_id), UUID(job_id))


@celery_app.task(name="analyze_archaeology", acks_late=True, reject_on_worker_lost=True)
def analyze_archaeology(repository_id: str, job_id: str) -> None:
    index_archaeology_repository(get_engine(), UUID(repository_id), UUID(job_id))


@celery_app.task(name="analyze_architecture_history", acks_late=True, reject_on_worker_lost=True)
def analyze_architecture_history(repository_id: str, job_id: str) -> None:
    index_architecture_history(get_engine(), UUID(repository_id), UUID(job_id))


@celery_app.task(name="build_bug_investigation", acks_late=True, reject_on_worker_lost=True)
def build_bug_investigation(repository_id: str, job_id: str) -> None:
    build_investigation(get_engine(), UUID(repository_id), UUID(job_id))
