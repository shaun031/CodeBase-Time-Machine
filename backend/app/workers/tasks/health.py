import logging
from typing import Any

from app.workers.celery_app import celery_app

logger = logging.getLogger("ctm")


@celery_app.task(bind=True, name="health_check_task")
def health_check_task(self: Any) -> dict[str, str]:
    context = {"job_id": self.request.id}
    logger.info("celery_task_started", extra=context)
    result = {"status": "ok"}
    logger.info("celery_task_completed", extra=context)
    return result
