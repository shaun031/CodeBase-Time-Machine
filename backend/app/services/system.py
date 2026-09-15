import logging

from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

logger = logging.getLogger("ctm")


def check_database() -> bool:
    try:
        with get_engine().connect() as connection:
            return connection.scalar(text("SELECT 1")) == 1
    except Exception:
        logger.warning("database_connection_error")
        return False


def check_redis() -> bool:
    try:
        with Redis.from_url(
            get_settings().redis_url.get_secret_value(),
            socket_connect_timeout=2,
            socket_timeout=2,
            retry=Retry(NoBackoff(), 0),
        ) as client:
            return bool(client.ping())
    except Exception:
        logger.warning("redis_connection_error")
        return False
