import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    AnalysisJob,
    Commit,
    CommitPRLink,
    GitHubComment,
    GitHubIssue,
    GitHubIssueReference,
    GitHubPRCommit,
    GitHubPullRequest,
    Repository,
    RepositoryStatus,
    SymbolChangeEvent,
    SymbolLineage,
)
from app.services.github.indexer import GitHubIndexService
from app.services.github.models import GitHubPage, GitHubResponse
from app.services.github.rate_limit import RateLimitState
from app.services.github.service import GitHubService

STAMP = "2020-01-01T12:00:00Z"


@pytest.fixture
def db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run real PostgreSQL integration tests")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
    engine.dispose()


class FixtureClient:
    def __init__(self, sha: str) -> None:
        self.sha = sha
        self.rate_limit = RateLimitState(limit=60, remaining=42)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, path, *, params=None, etag=None):
        if path == "/repos/owner/repo":
            if etag:
                return GitHubResponse(None, etag, True)
            return GitHubResponse(
                {
                    "id": 100,
                    "owner": {"login": "owner"},
                    "name": "repo",
                    "full_name": "owner/repo",
                    "description": "Fixture repository",
                    "default_branch": "main",
                    "html_url": "https://github.com/owner/repo",
                    "homepage": None,
                    "language": "Python",
                    "stargazers_count": 3,
                    "forks_count": 1,
                    "open_issues_count": 1,
                    "archived": False,
                    "fork": False,
                    "created_at": STAMP,
                    "updated_at": STAMP,
                    "pushed_at": STAMP,
                },
                '"repository-etag"',
            )
        if path == "/repos/owner/repo/pulls/12":
            return GitHubResponse(self.pull_request(), None)
        raise AssertionError(f"Unexpected GET {path}")

    async def paginate(self, path, *, params=None, max_items):
        if path == "/repos/owner/repo/pulls":
            return GitHubPage([self.pull_request()], False)
        if path == "/repos/owner/repo/pulls/12/commits":
            return GitHubPage([{"sha": self.sha}], False)
        if path == "/repos/owner/repo/issues/12/comments":
            return GitHubPage([self.comment(301, "Looks good")], False)
        if path == "/repos/owner/repo/pulls/12/comments":
            return GitHubPage(
                [
                    {
                        **self.comment(302, "Cover this branch"),
                        "path": "tax.py",
                        "commit_id": self.sha,
                        "original_commit_id": self.sha,
                        "line": 8,
                        "original_line": 7,
                        "side": "RIGHT",
                        "diff_hunk": "@@ -7 +8 @@",
                    }
                ],
                False,
            )
        if path == "/repos/owner/repo/issues":
            return GitHubPage([self.issue(), {**self.pull_request(), "pull_request": {}}], False)
        if path == "/repos/owner/repo/issues/10/comments":
            return GitHubPage([self.comment(303, "Confirmed")], False)
        raise AssertionError(f"Unexpected page {path}")

    @staticmethod
    def user(user_id=200, login="octocat"):
        return {
            "id": user_id,
            "login": login,
            "avatar_url": f"https://avatars.example/{login}",
            "html_url": f"https://github.com/{login}",
            "type": "User",
        }

    def pull_request(self):
        return {
            "id": 120,
            "number": 12,
            "title": "Fix tax calculation",
            "body": "Fixes #10 and mentions owner/other#44",
            "state": "closed",
            "draft": False,
            "merged": True,
            "merged_at": STAMP,
            "closed_at": STAMP,
            "created_at": STAMP,
            "updated_at": STAMP,
            "user": self.user(),
            "merge_commit_sha": self.sha,
            "base": {"ref": "main"},
            "head": {"ref": "fix-tax"},
            "additions": 4,
            "deletions": 2,
            "changed_files": 1,
            "commits": 1,
            "comments": 1,
            "review_comments": 1,
            "html_url": "https://github.com/owner/repo/pull/12",
            "labels": [{"id": 501, "name": "bug", "description": "A bug", "color": "d73a4a"}],
        }

    def issue(self):
        return {
            "id": 110,
            "number": 10,
            "title": "Calculator returns incorrect tax",
            "body": "Tax is wrong.",
            "state": "closed",
            "user": self.user(201, "reporter"),
            "created_at": STAMP,
            "updated_at": STAMP,
            "closed_at": STAMP,
            "html_url": "https://github.com/owner/repo/issues/10",
            "comments": 1,
            "milestone": {"title": "v1"},
            "labels": [{"id": 501, "name": "bug", "description": "A bug", "color": "d73a4a"}],
        }

    def comment(self, comment_id, body):
        return {
            "id": comment_id,
            "user": self.user(202, "reviewer"),
            "body": body,
            "created_at": STAMP,
            "updated_at": STAMP,
            "html_url": f"https://github.com/owner/repo/comments/{comment_id}",
        }


@pytest.mark.integration
def test_github_sync_is_idempotent_and_builds_symbol_evidence_chain(db):
    sha = "a" * 40
    repository = Repository(
        owner="owner",
        name="repo",
        full_name=f"owner/repo-{uuid4().hex}",
        url="https://github.com/owner/repo",
        status=RepositoryStatus.ready,
        head_sha=sha,
        default_branch="main",
        history_index_status="ready",
    )
    db.add(repository)
    db.flush()
    commit = Commit(
        repository_id=repository.id,
        sha=sha,
        short_sha=sha[:12],
        message="Fix calculation. See #10",
        author_name="Fixture Author",
        author_email="fixture@example.com",
        committer_name="Fixture Author",
        committer_email="fixture@example.com",
        authored_at=datetime(2020, 1, 1, 12, tzinfo=UTC),
        committed_at=datetime(2020, 1, 1, 12, tzinfo=UTC),
        is_merge_commit=False,
        insertions=4,
        deletions=2,
        files_changed=1,
    )
    db.add(commit)
    db.flush()
    lineage = SymbolLineage(
        repository_id=repository.id,
        symbol_kind="function",
        current_name="calculate_tax",
        current_qualified_name="calculate_tax",
        current_file_path="tax.py",
        introduced_commit_id=commit.id,
        last_seen_commit_id=commit.id,
    )
    db.add(lineage)
    db.flush()
    db.add(
        SymbolChangeEvent(
            repository_id=repository.id,
            lineage_id=lineage.id,
            commit_id=commit.id,
            event_type="body_changed",
            summary_data={"new_name": "calculate_tax", "new_path": "tax.py"},
        )
    )
    job = AnalysisJob(repository_id=repository.id, job_type="github_sync")
    db.add(job)
    db.flush()
    fixture = FixtureClient(sha)
    service = GitHubIndexService(
        Settings(
            database_url="postgresql+psycopg://unused:unused@localhost/unused",
            max_github_pull_requests=20,
            max_github_issues=20,
            max_github_comments=20,
            max_github_review_comments=20,
        ),
        client_factory=lambda: fixture,
    )
    service.run(db, repository, job)
    service.run(db, repository, job)

    assert db.scalar(select(func.count()).select_from(GitHubPullRequest)) == 1
    assert db.scalar(select(func.count()).select_from(GitHubIssue)) == 1
    assert db.scalar(select(func.count()).select_from(GitHubComment)) == 3
    assert db.scalar(select(func.count()).select_from(GitHubPRCommit)) == 1
    assert db.scalar(select(func.count()).select_from(CommitPRLink)) == 2
    assert db.scalar(select(func.count()).select_from(GitHubIssueReference)) == 3

    context = GitHubService(db).symbol_context(repository.id, lineage.id)
    [event] = context.events
    assert event.event.symbol_name == "calculate_tax"
    assert event.commit.sha == sha
    assert event.pull_requests[0].number == 12
    local_issue = next(item for item in event.issues if item.number == 10)
    assert local_issue.issue is not None
    assert local_issue.issue.title == "Calculator returns incorrect tax"
    assert local_issue.reference_type in {"fixes", "mentions"}

    pull = GitHubService(db).pull_request(repository.id, 12)
    assert pull.labels[0].name == "bug"
    assert pull.review_comments[0].path == "tax.py"
    assert pull.affected_symbols[0].lineage_id == lineage.id
