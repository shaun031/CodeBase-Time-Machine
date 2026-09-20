import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import repositories, system
from app.core.exceptions import NotFoundError, register_exception_handlers


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "codebase-time-machine"}
    assert response.headers["x-request-id"]


@pytest.mark.parametrize(
    "database,redis,expected",
    [(True, True, 200), (False, True, 503), (True, False, 503), (False, False, 503)],
)
def test_system_status(client, monkeypatch, database, redis, expected):
    monkeypatch.setattr(
        system,
        "get_settings",
        lambda: type("Settings", (), {"task_execution_mode": "celery"})(),
    )
    monkeypatch.setattr(system, "check_database", lambda: database)
    monkeypatch.setattr(system, "check_redis", lambda: redis)
    monkeypatch.setattr(system.OllamaService, "is_available", lambda self: True)
    response = client.get("/api/system/status")
    assert response.status_code == expected
    assert response.json() == {
        "backend": "ok",
        "database": "ok" if database else "unavailable",
        "redis": "ok" if redis else "unavailable",
        "ollama": "ok",
    }


def test_system_status_does_not_require_redis_in_local_mode(client, monkeypatch):
    monkeypatch.setattr(system, "check_database", lambda: True)
    monkeypatch.setattr(
        system,
        "get_settings",
        lambda: type("Settings", (), {"task_execution_mode": "local"})(),
    )
    monkeypatch.setattr(
        system,
        "check_redis",
        lambda: pytest.fail("Local mode must not connect to Redis"),
    )
    monkeypatch.setattr(system.OllamaService, "is_available", lambda self: True)
    response = client.get("/api/system/status")
    assert response.status_code == 200
    assert response.json() == {
        "backend": "ok",
        "database": "ok",
        "redis": "not_required",
        "ollama": "ok",
    }


def test_system_status_reports_ollama_failure_without_degrading_backend(client, monkeypatch):
    monkeypatch.setattr(system, "check_database", lambda: True)
    monkeypatch.setattr(system.OllamaService, "is_available", lambda self: False)
    response = client.get("/api/system/status")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"
    assert response.json()["redis"] == "not_required"
    assert response.json()["ollama"] == "unavailable"


def test_repository_system_status_normalizes_independent_index_states():
    assert repositories._state_status("ready", "same", "same") == "ready"
    assert repositories._state_status("ready", "old", "new") == "stale"
    assert repositories._state_status("syncing", None, None) == "indexing"
    assert repositories._state_status("ready", None, None, error="safe error") == "failed"


def test_cors(client):
    response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    response = client.get("/api/health", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in response.headers


def test_unknown_route(client):
    assert client.get("/missing").json() == {"error": {"code": "HTTP_404", "message": "Not Found"}}


def test_errors_are_predictable_and_do_not_disclose_secrets():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/custom")
    def custom():
        raise NotFoundError("Item not found")

    @app.get("/failure")
    def failure():
        raise RuntimeError("password=do-not-expose")

    @app.get("/validate")
    def validate(number: int):
        return number

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/custom").status_code == 404
        assert client.get("/custom").json()["error"]["code"] == "NOT_FOUND"
        response = client.get("/failure")
        assert response.status_code == 500
        assert "do-not-expose" not in response.text
        assert client.get("/validate?number=secret").json()["error"]["code"] == "VALIDATION_ERROR"
