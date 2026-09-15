from celery import Celery
from celery.signals import after_setup_logger

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
celery_app = Celery(
    "codebase_time_machine",
    broker=settings.redis_url.get_secret_value(),
    backend=settings.redis_url.get_secret_value(),
    include=["app.workers.tasks.health", "app.workers.tasks.repository"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3},
    result_backend_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3},
)


@after_setup_logger.connect
def setup_worker_logging(**kwargs: object) -> None:
    configure_logging()
