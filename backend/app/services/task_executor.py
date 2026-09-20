import logging
import threading
from time import perf_counter
from typing import Literal
from uuid import UUID

from app.core.config import get_settings

logger = logging.getLogger("ctm")
TaskName = Literal[
    "index_repository",
    "index_code",
    "index_history",
    "index_github",
    "index_graph",
    "index_ai",
    "index_archaeology",
    "index_architecture_history",
    "build_investigation",
]


def _run_local(task: TaskName, repository_id: UUID, job_id: UUID) -> None:
    from app.db.session import get_engine
    from app.services.ai.indexer import index_ai_repository
    from app.services.archaeology.indexer import index_archaeology_repository
    from app.services.architecture_history.indexer import index_architecture_history
    from app.services.github.indexer import index_github_repository
    from app.services.graph.builder import index_dependency_graph
    from app.services.historical_index import index_historical_repository
    from app.services.indexing import index_code_repository, index_repository
    from app.services.investigation.report import build_investigation

    targets = {
        "index_repository": index_repository,
        "index_code": index_code_repository,
        "index_history": index_historical_repository,
        "index_github": index_github_repository,
        "index_graph": index_dependency_graph,
        "index_ai": index_ai_repository,
        "index_archaeology": index_archaeology_repository,
        "index_architecture_history": index_architecture_history,
        "build_investigation": build_investigation,
    }
    target = targets[task]
    started = perf_counter()
    try:
        target(get_engine(), repository_id, job_id)
        logger.info(
            "background_task_completed",
            extra={
                "task": task,
                "repository_id": repository_id,
                "job_id": job_id,
                "duration_seconds": round(perf_counter() - started, 3),
            },
        )
    except Exception:
        logger.exception(
            "local_background_task_failed",
            extra={
                "task": task,
                "repository_id": repository_id,
                "job_id": job_id,
                "duration_seconds": round(perf_counter() - started, 3),
            },
        )


class TaskExecutor:
    def submit(self, task: TaskName, repository_id: UUID, job_id: UUID) -> None:
        if get_settings().task_execution_mode == "local":
            threading.Thread(
                target=_run_local,
                args=(task, repository_id, job_id),
                name=f"ctm-{task}-{job_id}",
                daemon=True,
            ).start()
            return
        from app.workers.tasks.repository import (
            analyze_ai,
            analyze_archaeology,
            analyze_architecture_history,
            analyze_code,
            analyze_github,
            analyze_graph,
            analyze_history,
            analyze_repository,
            build_bug_investigation,
        )

        celery_tasks = {
            "index_repository": analyze_repository,
            "index_code": analyze_code,
            "index_history": analyze_history,
            "index_github": analyze_github,
            "index_graph": analyze_graph,
            "index_ai": analyze_ai,
            "index_archaeology": analyze_archaeology,
            "index_architecture_history": analyze_architecture_history,
            "build_investigation": build_bug_investigation,
        }
        celery_task = celery_tasks[task]
        celery_task.apply_async(
            args=[str(repository_id), str(job_id)], task_id=str(job_id), retry=False
        )


task_executor = TaskExecutor()
