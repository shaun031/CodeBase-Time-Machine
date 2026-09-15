from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.ingestion_errors import IngestionError
from app.parsers.git_history import parse_changes
from app.services.git import GitService
from app.services.repository_url import GitHubRepositoryURL
from app.tests.git_fixtures import create_repository


@pytest.fixture(scope="module")
def fixture_repo(tmp_path_factory):
    path = tmp_path_factory.mktemp("git-fixture") / "repo"
    return path, create_repository(path)


@pytest.fixture
def git(tmp_path):
    return GitService(Settings(_env_file=None, repository_storage_path=tmp_path / "storage"))


def test_metadata_and_messages(git, fixture_repo):
    path, shas = fixture_repo
    git.ensure_git_available()
    assert git.get_default_branch(path) == "main"
    assert git.get_head_sha(path) == shas["head"]
    commits = git.get_commits(path, shas["head"])
    assert len(commits) == 10
    assert commits[0] == shas["root"]
    assert commits[-1] == shas["head"]
    message = git.get_commit(path, shas["unicode"])
    assert "café 日本語\n\nMultiline" in message.message
    assert message.author_email == "fixture@example.test"
    assert message.authored_at.tzinfo is not None
    merge = git.get_commit(path, shas["merge"])
    assert merge.parents == [shas["main"], shas["feature"]]
    assert git.is_ancestor(path, shas["root"], shas["head"])
    assert not git.is_ancestor(path, shas["feature"], shas["main"])


def test_changes_and_renames(git, fixture_repo):
    path, shas = fixture_repo
    root = git.get_changed_files(path, git.get_commit(path, shas["root"]))
    assert root[0].change_type == "added"
    assert root[0].old_path is None
    assert root[0].additions == 1
    rename = git.get_changed_files(path, git.get_commit(path, shas["rename"]))
    assert len(rename) == 1
    assert (rename[0].old_path, rename[0].new_path) == ("app.py", "main.py")
    assert rename[0].change_type == "renamed"
    assert rename[0].similarity_score == 100
    binary = git.get_changed_files(path, git.get_commit(path, shas["binary"]))
    assert binary[0].additions is None and binary[0].deletions is None
    deleted = git.get_changed_files(path, git.get_commit(path, shas["head"]))
    assert deleted[0].change_type == "deleted" and deleted[0].new_path is None
    merge = git.get_changed_files(path, git.get_commit(path, shas["merge"]))
    assert [change.new_path for change in merge] == ["feature.txt"]


def test_tags_and_diff(git, fixture_repo):
    path, shas = fixture_repo
    tags = git.get_tags(path)
    assert tags == [
        {"name": "v0.1", "target_sha": shas["rename"], "annotated": False},
        {"name": "v1.0", "target_sha": shas["head"], "annotated": True},
    ]
    diff, truncated = git.get_commit_diff(path, shas["unicode"])
    assert "+print('world')" in diff and not truncated
    git.settings.max_diff_size_bytes = 32
    diff, truncated = git.get_commit_diff(path, shas["unicode"])
    assert truncated and len(diff.encode()) <= 32


def test_limits(git, fixture_repo):
    path, shas = fixture_repo
    git.settings.max_commits = 2
    with pytest.raises(IngestionError, match="MAX_COMMITS"):
        git.get_commits(path, shas["head"])


def test_tab_newline_paths_are_not_split():
    raw = b":100644 100644 abc def R100\0old\tname\n.py\0new name.py\0"
    nums = b"0\t0\t\0old\tname\n.py\0new name.py\0"
    changes = parse_changes(raw, nums)
    assert changes[0].old_path == "old\tname\n.py"


def test_verify_remote_builds_safe_command(git, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return b"ref: refs/heads/trunk\tHEAD\n" + b"a" * 40 + b"\tHEAD\n", False, 0

    monkeypatch.setattr(git.runner, "run", run)
    remote = git.verify_remote(GitHubRepositoryURL.parse("https://github.com/owner/repo"))
    assert remote.default_branch == "trunk"
    assert calls[0][0] == ["ls-remote", "--symref", "https://github.com/owner/repo.git", "HEAD"]
    assert calls[0][1]["network"] is True


def test_clone_failure_cleans_partial(git, monkeypatch):
    repository_id = uuid4()

    def fail(args, **kwargs):
        path = Path(args[-1])
        path.mkdir()
        (path / "partial").write_text("partial")
        raise IngestionError("CLONE_FAILED", "Clone failed")

    monkeypatch.setattr(git.runner, "run", fail)
    from app.services.git import RemoteInfo

    with pytest.raises(IngestionError):
        git.clone_repository(
            repository_id, GitHubRepositoryURL("owner", "repo"), RemoteInfo("main", "a" * 40)
        )
    assert not git.storage.path(repository_id).exists()
    assert not git.storage.path(repository_id, temporary=True).exists()


def test_invalid_sha_cannot_be_an_option(git):
    with pytest.raises(IngestionError):
        git.get_commit(Path("."), "--output=anything")


def test_hook_and_external_diff_are_not_executed(git, fixture_repo, tmp_path):
    path, shas = fixture_repo
    marker = tmp_path / "executed"
    # An external diff specified through inherited env must never be used.
    import os

    old = os.environ.get("GIT_EXTERNAL_DIFF")
    os.environ["GIT_EXTERNAL_DIFF"] = f"touch {marker}"
    try:
        git.get_commit_diff(path, shas["unicode"])
    finally:
        if old is None:
            os.environ.pop("GIT_EXTERNAL_DIFF", None)
        else:
            os.environ["GIT_EXTERNAL_DIFF"] = old
    assert not marker.exists()


def test_empty_repository(git, tmp_path):
    import os
    import subprocess

    path = tmp_path / "empty"
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=empty", str(path)],
        env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
        check=True,
        capture_output=True,
    )
    assert git.get_head_sha(path) is None
    assert git.get_commits(path, None) == []
    assert git.get_tags(path) == []


def test_uuid_storage_and_traversal(git):
    repository_id = uuid4()
    path = git.storage.path(repository_id)
    assert path == git.settings.repository_storage_path / str(repository_id) / "repo"
    with pytest.raises((ValueError, IngestionError)):
        git.storage.path("../escape")
    with pytest.raises(IngestionError):
        git.storage.validate(git.settings.repository_storage_path / ".." / "outside")


def test_git_missing_is_typed(git, monkeypatch):
    monkeypatch.setattr("app.services.git_runner.shutil.which", lambda _: None)
    with pytest.raises(IngestionError) as error:
        git.ensure_git_available()
    assert error.value.code == "GIT_NOT_AVAILABLE"


def test_failed_clone_is_atomic_and_no_shallow_checkout(git, monkeypatch):
    from app.services.git import RemoteInfo

    repository_id = uuid4()
    calls = []

    def clone(args, **kwargs):
        calls.append(args)
        temporary = Path(args[-1])
        temporary.mkdir()
        (temporary / "HEAD").write_text("ref: refs/heads/main")
        return b"", False, 0

    monkeypatch.setattr(git.runner, "run", clone)
    path = git.clone_repository(
        repository_id, GitHubRepositoryURL("owner", "repo"), RemoteInfo("main", "a" * 40)
    )
    assert (path / "HEAD").exists()
    assert not git.storage.path(repository_id, temporary=True).exists()
    assert "--bare" in calls[0] and "--single-branch" in calls[0]
    assert not any(arg.startswith("--depth") for arg in calls[0])


def test_historical_git_access_and_blame(git, fixture_repo):
    path, shas = fixture_repo
    blob_sha, size = git.get_blob_sha(path, shas["unicode"], "app.py")
    assert len(blob_sha) == 40 and size > 0
    assert b"print('world')" in git.get_file_at_commit(path, shas["unicode"], "app.py")
    assert git.file_exists_at_commit(path, shas["unicode"], "app.py")
    assert not git.file_exists_at_commit(path, shas["unicode"], "missing.py")
    assert git.get_parent_commits(path, shas["rename"])
    changes = git.get_changed_files_between(
        path, git.get_parent_commits(path, shas["rename"])[0], shas["rename"]
    )
    assert changes[0].change_type == "renamed"
    diff, truncated = git.get_file_diff(
        path, git.get_parent_commits(path, shas["unicode"])[0], shas["unicode"], "app.py"
    )
    assert "+print('world')" in diff and not truncated
    history = git.get_file_history(path, "main.py")
    assert history[0].sha == shas["rename"]
    blame = git.get_blame(path, shas["head"], "main.py", 1, 2)
    assert [line.line for line in blame] == [1, 2]
    assert all(len(line.commit_sha) == 40 for line in blame)


@pytest.mark.parametrize(
    "value",
    ["../../../etc/passwd", r"C:\Windows\System32\config", "--help", "$(command)"],
)
def test_historical_paths_are_rejected(git, value):
    with pytest.raises(IngestionError) as error:
        git.get_file_at_commit(Path("."), "a" * 40, value)
    assert error.value.code == "INVALID_FILE_PATH"


@pytest.mark.parametrize("value", ["HEAD~1", "--help", "$(command)", "a" * 39])
def test_historical_commit_refs_are_rejected(git, value):
    with pytest.raises(IngestionError) as error:
        git.get_parent_commits(Path("."), value)
    assert error.value.code == "INVALID_COMMIT_SHA"
