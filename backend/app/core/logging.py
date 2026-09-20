import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        # Only explicitly approved context fields are serialized. No exception payloads or URLs.
        for field in (
            "repository_id",
            "job_id",
            "commit_sha",
            "request_id",
            "task",
            "duration_seconds",
            "status",
        ):
            if hasattr(record, field):
                payload[field] = str(getattr(record, field))
        return json.dumps(payload)


def configure_logging() -> None:
    logger = logging.getLogger("ctm")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
