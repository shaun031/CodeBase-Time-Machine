import json
import logging

from app.core.logging import JsonFormatter
from app.services import system


def test_database_failure_is_reported_without_secrets(monkeypatch, caplog):
    def fail():
        raise RuntimeError("secret-password")

    monkeypatch.setattr(system, "get_engine", fail)
    with caplog.at_level(logging.WARNING, logger="ctm"):
        assert system.check_database() is False
    assert "secret-password" not in caplog.text


def test_logging_context_allowlist():
    record = logging.LogRecord("ctm", logging.INFO, __file__, 1, "test_event", (), None)
    record.request_id = "request-123"
    record.password = "do-not-log"
    data = json.loads(JsonFormatter().format(record))
    assert data["request_id"] == "request-123"
    assert "password" not in data
