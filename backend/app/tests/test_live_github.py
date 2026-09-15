import os
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.services.git import GitService
from app.services.repository_url import GitHubRepositoryURL


@pytest.mark.skipif(
    os.getenv("LIVE_GITHUB_TESTS") != "true", reason="Explicit live GitHub opt-in required"
)
def test_small_public_clone(tmp_path):
    git = GitService(Settings(_env_file=None, repository_storage_path=tmp_path, max_commits=100))
    url = GitHubRepositoryURL.parse("https://github.com/octocat/Hello-World")
    remote = git.verify_remote(url)
    path = git.clone_repository(uuid4(), url, remote)
    assert path.exists() and not (path / ".git").exists()  # Bare, no checkout.
    assert git.get_commits(path, git.get_head_sha(path))

    head = git.get_head_sha(path)
    commit = git.get_commit(path, head)
    assert git.get_changed_files(path, commit)
    git.get_commit_diff(path, head)
    git.fetch_repository(path, url, git.verify_remote(url))
    assert git.get_head_sha(path, fetched=True)
