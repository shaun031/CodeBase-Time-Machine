import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.core.ingestion_errors import IngestionError
from app.services.github.client import GitHubClient


def settings(**values):
    return Settings(
        database_url="postgresql+psycopg://test:test@localhost/test",
        github_max_retries=values.pop("github_max_retries", 0),
        **values,
    )


def run(awaitable):
    return asyncio.run(awaitable)


def test_github_client_paginates_and_uses_read_only_headers():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["page"])
        data = [{"id": page * 100 + index} for index in range(100 if page == 1 else 1)]
        return httpx.Response(
            200,
            json=data,
            headers={
                "X-RateLimit-Limit": "60",
                "X-RateLimit-Remaining": "58",
                "X-RateLimit-Reset": "1893456000",
            },
        )

    async def exercise():
        async with GitHubClient(
            settings(github_token="server-secret"), transport=httpx.MockTransport(handler)
        ) as client:
            page = await client.paginate("/repos/owner/repo/issues", max_items=150)
            assert client.rate_limit.remaining == 58
            return page

    page = run(exercise())
    assert len(page.items) == 101
    assert page.limited is False
    assert len(requests) == 2
    assert requests[0].headers["user-agent"] == "CodeChronicle/1.0"
    assert requests[0].headers["authorization"] == "Bearer server-secret"
    assert requests[0].method == "GET"


def test_github_client_retries_temporary_response():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(502 if attempts == 1 else 200, json={"ok": True})

    async def exercise():
        async with GitHubClient(
            settings(github_max_retries=1), transport=httpx.MockTransport(handler)
        ) as client:
            return await client.get("/repos/owner/repo")

    assert run(exercise()).data == {"ok": True}
    assert attempts == 2


@pytest.mark.parametrize(
    ("status", "code"),
    [(404, "GITHUB_REPOSITORY_NOT_FOUND"), (403, "GITHUB_API_ERROR"), (500, "GITHUB_API_ERROR")],
)
def test_github_client_maps_non_retryable_errors(status, code):
    async def exercise():
        transport = httpx.MockTransport(lambda request: httpx.Response(status, json={}))
        async with GitHubClient(settings(), transport=transport) as client:
            await client.get("/repos/owner/repo")

    with pytest.raises(IngestionError) as caught:
        run(exercise())
    assert caught.value.code == code


def test_github_client_reports_rate_limit_without_retrying():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            403,
            json={"message": "rate limited"},
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1893456000"},
        )

    async def exercise():
        async with GitHubClient(
            settings(github_max_retries=3), transport=httpx.MockTransport(handler)
        ) as client:
            await client.get("/repos/owner/repo")

    with pytest.raises(IngestionError) as caught:
        run(exercise())
    assert caught.value.code == "GITHUB_RATE_LIMITED"
    assert "2030" in caught.value.message
    assert calls == 1


def test_github_client_handles_invalid_json_and_empty_response():
    async def invalid():
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"not-json"))
        async with GitHubClient(settings(), transport=transport) as client:
            await client.get("/repos/owner/repo")

    with pytest.raises(IngestionError) as caught:
        run(invalid())
    assert caught.value.code == "GITHUB_API_ERROR"

    async def empty():
        transport = httpx.MockTransport(lambda request: httpx.Response(204))
        async with GitHubClient(settings(), transport=transport) as client:
            return await client.get("/repos/owner/repo")

    assert run(empty()).data is None


def test_github_client_maps_timeout_and_network_failure():
    def handler_for(error):
        def handler(request: httpx.Request) -> httpx.Response:
            raise error

        return handler

    for error, code in [
        (httpx.ReadTimeout("late"), "GITHUB_API_TIMEOUT"),
        (httpx.ConnectError("offline"), "GITHUB_UNAVAILABLE"),
    ]:

        async def exercise(current_error=error):
            async with GitHubClient(
                settings(), transport=httpx.MockTransport(handler_for(current_error))
            ) as client:
                await client.get("/repos/owner/repo")

        with pytest.raises(IngestionError) as caught:
            run(exercise())
        assert caught.value.code == code


def test_github_client_rejects_arbitrary_urls():
    async def exercise():
        async with GitHubClient(settings()) as client:
            await client.get("https://example.com/private")

    with pytest.raises(IngestionError) as caught:
        run(exercise())
    assert caught.value.code == "GITHUB_API_ERROR"
