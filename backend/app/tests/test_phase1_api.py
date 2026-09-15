from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.api.routes import repositories
from app.core.ingestion_errors import IngestionError
from app.db.session import get_session
from app.schemas.git import SubmissionResponse


@pytest.fixture
def api(client):
    session = MagicMock()
    client.app.dependency_overrides[get_session] = lambda: session
    yield client, session
    client.app.dependency_overrides.clear()


def test_submission_contract(api, monkeypatch):
    client, session = api
    repo_id, job_id = uuid4(), uuid4()
    submit = MagicMock(
        return_value=SubmissionResponse(repository_id=repo_id, job_id=job_id, status="queued")
    )
    monkeypatch.setattr(repositories, "submit_repository", submit)
    response = client.post("/api/repositories", json={"url": "https://github.com/a/b"})
    assert response.status_code == 202
    assert response.json()["job_id"] == str(job_id)
    submit.assert_called_once_with(session, "https://github.com/a/b")


def test_invalid_url_rejected_before_git(api, monkeypatch):
    from app.services.git import GitService

    verify = MagicMock()
    monkeypatch.setattr(GitService, "verify_remote", verify)
    response = api[0].post("/api/repositories", json={"url": "https://localhost/a/b"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REPOSITORY_URL"
    verify.assert_not_called()


@pytest.mark.parametrize(
    "endpoint,code", [("repositories", "REPOSITORY_NOT_FOUND"), ("jobs", "JOB_NOT_FOUND")]
)
def test_missing_records(api, endpoint, code):
    client, session = api
    session.get.return_value = None
    response = client.get(f"/api/{endpoint}/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == code


def test_pagination_is_bounded(api):
    response = api[0].get(f"/api/repositories/{uuid4()}/commits?page_size=101")
    assert response.status_code == 422


def test_public_failure_is_sanitized(api, monkeypatch):
    from app.services.git import GitService

    monkeypatch.setattr(
        GitService,
        "verify_remote",
        MagicMock(
            side_effect=IngestionError(
                "REPOSITORY_NOT_ACCESSIBLE", "Repository is not publicly accessible.", 422
            )
        ),
    )
    response = api[0].post("/api/repositories", json={"url": "https://github.com/a/b"})
    assert response.json()["error"]["code"] == "REPOSITORY_NOT_ACCESSIBLE"


def test_post_cors_preflight(api):
    response = api[0].options(
        "/api/repositories",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
