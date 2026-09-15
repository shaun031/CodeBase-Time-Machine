from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


@dataclass(slots=True)
class RateLimitState:
    limit: int | None = None
    remaining: int | None = None
    reset_at: datetime | None = None

    def update(self, headers: Mapping[str, str]) -> None:
        self.limit = _integer(headers.get("x-ratelimit-limit"), self.limit)
        self.remaining = _integer(headers.get("x-ratelimit-remaining"), self.remaining)
        reset = headers.get("x-ratelimit-reset")
        if reset:
            try:
                self.reset_at = datetime.fromtimestamp(int(reset), tz=UTC)
            except (ValueError, OverflowError, OSError):
                self.reset_at = None
        if self.reset_at is None and headers.get("retry-after"):
            value = headers["retry-after"]
            try:
                self.reset_at = datetime.fromtimestamp(
                    datetime.now(UTC).timestamp() + int(value), tz=UTC
                )
            except ValueError:
                try:
                    self.reset_at = parsedate_to_datetime(value).astimezone(UTC)
                except (TypeError, ValueError, OverflowError):
                    pass


def _integer(value: str | None, fallback: int | None) -> int | None:
    try:
        return int(value) if value is not None else fallback
    except ValueError:
        return fallback
