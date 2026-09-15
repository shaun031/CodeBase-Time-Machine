import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.ingestion_errors import IngestionError


@dataclass(frozen=True)
class GitHubRepositoryURL:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.full_name}"

    @property
    def clone_url(self) -> str:
        return f"{self.url}.git"

    @classmethod
    def parse(cls, value: str) -> "GitHubRepositoryURL":
        def invalid() -> IngestionError:
            return IngestionError(
                "INVALID_REPOSITORY_URL",
                "Enter a public repository URL: https://github.com/owner/repository.",
                422,
            )

        value = value.strip()
        if not value or len(value) > 2048 or any(ord(c) < 33 for c in value):
            raise invalid()
        try:
            parsed = urlsplit(value)
        except ValueError:
            raise invalid() from None
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            raise invalid()
        if "?" in value or "#" in value or "%" in value or "\\" in value:
            raise invalid()
        parts = parsed.path.removesuffix("/").split("/")
        if len(parts) != 3 or parts[0]:
            raise invalid()
        owner, name = parts[1].lower(), parts[2].lower()
        name = name.removesuffix(".git")
        if (
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?", owner)
            or "--" in owner
            or not re.fullmatch(r"[a-z0-9_.-]{1,100}", name)
            or name in {".", ".."}
            or name.startswith("-")
        ):
            raise invalid()
        return cls(owner=owner, name=name)
