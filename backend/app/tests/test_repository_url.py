import pytest

from app.core.ingestion_errors import IngestionError
from app.services.repository_url import GitHubRepositoryURL


@pytest.mark.parametrize(
    "value",
    [
        "https://github.com/Pallets/Flask",
        "https://GITHUB.com/pallets/flask.git",
        " https://github.com/pallets/flask/ ",
    ],
)
def test_normalization(value):
    url = GitHubRepositoryURL.parse(value)
    assert url.full_name == "pallets/flask"
    assert url.clone_url == "https://github.com/pallets/flask.git"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://example.com/a/b",
        "http://github.com/a/b",
        "https://localhost/a/b",
        "https://127.0.0.1/a/b",
        "https://[::1]/a/b",
        "git@github.com:a/b.git",
        "ssh://github.com/a/b",
        "file:///a/b",
        "https://token@github.com/a/b",
        "https://github.com/a",
        "https://github.com//b",
        "https://github.com/a/b/tree/main",
        "https://github.com/a/b?x=y",
        "https://github.com/a/b#readme",
        "https://github.com/a/b?",
        "https://github.com:443/a/b",
        "https://api.github.com/a/b",
        "https://github.com/a/..",
        "https://github.com/a/%2e%2e",
        "https://github.com/a/--upload-pack=bad",
        "https://github.com/a/b\nother",
        "https://github.com/a/b\\evil",
    ],
)
def test_reject_unsafe(value):
    with pytest.raises(IngestionError) as error:
        GitHubRepositoryURL.parse(value)
    assert error.value.code == "INVALID_REPOSITORY_URL"
