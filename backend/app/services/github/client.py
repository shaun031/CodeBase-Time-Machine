import asyncio
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.services.github.models import GitHubPage, GitHubResponse
from app.services.github.rate_limit import RateLimitState

logger = logging.getLogger("ctm")
TEMPORARY_STATUS = {500, 502, 503, 504}


class GitHubRateLimitedError(IngestionError):
    def __init__(self, remaining: int | None, reset_at: datetime | None) -> None:
        self.remaining = remaining
        self.reset_at = reset_at
        when = reset_at.isoformat() if reset_at else "the rate-limit reset"
        super().__init__(
            "GITHUB_RATE_LIMITED",
            f"GitHub API rate limit reached. Try again after {when}.",
            429,
        )


class GitHubClient:
    """Read-only REST client restricted to internally constructed GitHub API paths."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        token = self.settings.github_token.get_secret_value()
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "CodeChronicle/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=headers,
            timeout=self.settings.github_request_timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )
        self.rate_limit = RateLimitState()

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _path(path: str) -> str:
        if not path.startswith("/") or "://" in path or ".." in path:
            raise IngestionError("GITHUB_API_ERROR", "Invalid internal GitHub API path.", 500)
        return path

    async def get(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        etag: str | None = None,
    ) -> GitHubResponse:
        safe_path = self._path(path)
        headers = {"If-None-Match": etag} if etag else None
        for attempt in range(self.settings.github_max_retries + 1):
            try:
                response = await self._client.get(safe_path, params=params, headers=headers)
            except httpx.TimeoutException:
                if attempt < self.settings.github_max_retries:
                    await asyncio.sleep(min(0.25 * 2**attempt, 2.0))
                    continue
                raise IngestionError(
                    "GITHUB_API_TIMEOUT", "GitHub API request timed out. Retry the sync.", 504
                ) from None
            except httpx.TransportError:
                if attempt < self.settings.github_max_retries:
                    await asyncio.sleep(min(0.25 * 2**attempt, 2.0))
                    continue
                raise IngestionError(
                    "GITHUB_UNAVAILABLE", "GitHub API is temporarily unavailable.", 503
                ) from None
            self.rate_limit.update(response.headers)
            if response.status_code == 304:
                return GitHubResponse(None, response.headers.get("etag"), True)
            if response.status_code in {403, 429} and (
                response.status_code == 429 or self.rate_limit.remaining == 0
            ):
                raise GitHubRateLimitedError(self.rate_limit.remaining, self.rate_limit.reset_at)
            if (
                response.status_code in TEMPORARY_STATUS
                and attempt < self.settings.github_max_retries
            ):
                await asyncio.sleep(min(0.25 * 2**attempt, 2.0))
                continue
            if response.status_code == 404:
                raise IngestionError(
                    "GITHUB_REPOSITORY_NOT_FOUND",
                    "The public GitHub resource was not found or is unavailable.",
                    404,
                )
            if response.status_code in {401, 403}:
                raise IngestionError(
                    "GITHUB_API_ERROR", "GitHub rejected the read-only API request.", 502
                )
            if response.status_code >= 400:
                raise IngestionError(
                    "GITHUB_API_ERROR",
                    f"GitHub API returned HTTP {response.status_code}.",
                    502,
                )
            if response.status_code == 204 or not response.content:
                return GitHubResponse(None, response.headers.get("etag"))
            try:
                data = response.json()
            except ValueError:
                raise IngestionError(
                    "GITHUB_API_ERROR", "GitHub API returned an unreadable response.", 502
                ) from None
            return GitHubResponse(data, response.headers.get("etag"))
        raise IngestionError("GITHUB_UNAVAILABLE", "GitHub API is temporarily unavailable.", 503)

    async def paginate(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        max_items: int,
    ) -> GitHubPage:
        items: list[dict[str, Any]] = []
        page = 1
        limited = False
        while len(items) < max_items:
            query = dict(params or {})
            query.update({"page": page, "per_page": min(100, max_items - len(items))})
            response = await self.get(path, params=query)
            if not isinstance(response.data, list):
                raise IngestionError(
                    "GITHUB_API_ERROR", "GitHub API returned an unexpected list response.", 502
                )
            batch = [item for item in response.data if isinstance(item, dict)]
            items.extend(batch)
            if len(batch) < int(query["per_page"]):
                break
            if len(items) >= max_items:
                limited = True
                break
            page += 1
        return GitHubPage(items[:max_items], limited)
