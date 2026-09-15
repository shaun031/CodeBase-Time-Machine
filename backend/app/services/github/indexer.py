import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AnalysisJob,
    GitHubComment,
    GitHubIssue,
    GitHubIssueLabel,
    GitHubLabel,
    GitHubPRCommit,
    GitHubPRLabel,
    GitHubPullRequest,
    GitHubRepositoryMetadata,
    GitHubSyncState,
    GitHubUser,
    JobStatus,
    Repository,
)
from app.services.github.client import GitHubClient, GitHubRateLimitedError
from app.services.github.linking import GitHubLinkingService

logger = logging.getLogger("ctm")
ClientFactory = Callable[[], GitHubClient]


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _integer(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _string(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


class GitHubIndexService:
    def __init__(
        self,
        settings: Settings | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client_factory = client_factory or (lambda: GitHubClient(self.settings))
        self.linking = GitHubLinkingService()

    def run(self, session: Session, repository: Repository, job: AnalysisJob) -> None:
        asyncio.run(self._sync(session, repository, job))

    def _state(self, session: Session, repository_id: UUID) -> GitHubSyncState:
        state = session.get(GitHubSyncState, repository_id)
        if state is None:
            state = GitHubSyncState(repository_id=repository_id, status="queued")
            session.add(state)
            session.flush()
        return state

    @staticmethod
    def _progress(
        session: Session,
        state: GitHubSyncState,
        job: AnalysisJob,
        step: str,
        progress: float,
    ) -> None:
        state.current_step = step
        state.progress = progress
        job.current_step = step
        job.progress = progress
        session.commit()

    def _body(self, value: Any, state: GitHubSyncState) -> str | None:
        if not isinstance(value, str):
            return None
        if len(value) > self.settings.max_github_body_length:
            state.github_index_limited = True
            return value[: self.settings.max_github_body_length]
        return value

    def _user(self, session: Session, data: Any) -> tuple[GitHubUser | None, str | None]:
        if not isinstance(data, dict) or not isinstance(data.get("id"), int):
            return None, None
        user = session.scalar(select(GitHubUser).where(GitHubUser.github_user_id == data["id"]))
        if user is None:
            user = GitHubUser(github_user_id=data["id"], login=_string(data.get("login")))
            session.add(user)
        user.login = _string(data.get("login"), user.login)
        user.avatar_url = (
            data.get("avatar_url") if isinstance(data.get("avatar_url"), str) else None
        )
        user.html_url = data.get("html_url") if isinstance(data.get("html_url"), str) else None
        user.user_type = _string(data.get("type"), "User")
        session.flush()
        return user, user.login

    def _label(self, session: Session, repository_id: UUID, data: Any) -> GitHubLabel | None:
        if not isinstance(data, dict) or not isinstance(data.get("id"), int):
            return None
        label = session.scalar(
            select(GitHubLabel).where(
                GitHubLabel.repository_id == repository_id,
                GitHubLabel.github_label_id == data["id"],
            )
        )
        if label is None:
            label = GitHubLabel(
                repository_id=repository_id,
                github_label_id=data["id"],
                name=_string(data.get("name")),
            )
            session.add(label)
        label.name = _string(data.get("name"), label.name)
        label.description = (
            data.get("description") if isinstance(data.get("description"), str) else None
        )
        label.color = data.get("color") if isinstance(data.get("color"), str) else None
        session.flush()
        return label

    def _metadata(
        self,
        session: Session,
        repository: Repository,
        data: dict[str, Any],
        state: GitHubSyncState,
    ) -> None:
        github_id = data.get("id")
        created = _datetime(data.get("created_at"))
        updated = _datetime(data.get("updated_at"))
        if not isinstance(github_id, int) or created is None or updated is None:
            raise IngestionError(
                "GITHUB_API_ERROR", "GitHub repository metadata is incomplete.", 502
            )
        item = session.scalar(
            select(GitHubRepositoryMetadata).where(
                GitHubRepositoryMetadata.repository_id == repository.id
            )
        )
        if item is None:
            item = GitHubRepositoryMetadata(
                repository_id=repository.id,
                github_repository_id=github_id,
                owner=repository.owner,
                name=repository.name,
                full_name=repository.full_name,
                html_url=repository.url,
                github_created_at=created,
                github_updated_at=updated,
            )
            session.add(item)
        owner_value = data.get("owner")
        owner: dict[str, Any] = owner_value if isinstance(owner_value, dict) else {}
        item.github_repository_id = github_id
        item.owner = _string(owner.get("login"), repository.owner)
        item.name = _string(data.get("name"), repository.name)
        item.full_name = _string(data.get("full_name"), repository.full_name)
        item.description = self._body(data.get("description"), state)
        item.default_branch = _string(data.get("default_branch")) or None
        item.html_url = _string(data.get("html_url"), repository.url)
        item.homepage = _string(data.get("homepage")) or None
        item.language = _string(data.get("language")) or None
        item.stars = _integer(data.get("stargazers_count"))
        item.forks = _integer(data.get("forks_count"))
        item.open_issues_count = _integer(data.get("open_issues_count"))
        item.archived = bool(data.get("archived", False))
        item.fork = bool(data.get("fork", False))
        item.github_created_at = created
        item.github_updated_at = updated
        item.pushed_at = _datetime(data.get("pushed_at"))
        item.synced_at = datetime.now(UTC)

    def _pull_request(
        self,
        session: Session,
        repository: Repository,
        data: dict[str, Any],
        state: GitHubSyncState,
    ) -> GitHubPullRequest:
        number = _integer(data.get("number"))
        github_id = _integer(data.get("id"))
        created = _datetime(data.get("created_at"))
        updated = _datetime(data.get("updated_at"))
        if not number or not github_id or created is None or updated is None:
            raise IngestionError("GITHUB_API_ERROR", "Pull request metadata is incomplete.", 502)
        item = session.scalar(
            select(GitHubPullRequest).where(
                GitHubPullRequest.repository_id == repository.id,
                GitHubPullRequest.number == number,
            )
        )
        user, login = self._user(session, data.get("user"))
        base_value = data.get("base")
        head_value = data.get("head")
        base: dict[str, Any] = base_value if isinstance(base_value, dict) else {}
        head: dict[str, Any] = head_value if isinstance(head_value, dict) else {}
        if item is None:
            item = GitHubPullRequest(
                repository_id=repository.id,
                github_pr_id=github_id,
                number=number,
                title=_string(data.get("title"), "Untitled pull request"),
                state=_string(data.get("state"), "open"),
                created_at=created,
                updated_at=updated,
                base_branch=_string(base.get("ref")),
                head_branch=_string(head.get("ref")),
                html_url=_string(data.get("html_url"), repository.url),
            )
            session.add(item)
        item.github_pr_id = github_id
        item.title = _string(data.get("title"), item.title)
        item.body = self._body(data.get("body"), state)
        item.state = _string(data.get("state"), item.state)
        item.draft = bool(data.get("draft", False))
        item.merged = bool(data.get("merged", data.get("merged_at") is not None))
        item.merged_at = _datetime(data.get("merged_at"))
        item.closed_at = _datetime(data.get("closed_at"))
        item.created_at = created
        item.updated_at = updated
        item.author_id = user.id if user else None
        item.author_login = login
        item.merge_commit_sha = _string(data.get("merge_commit_sha")) or None
        item.base_branch = _string(base.get("ref"), item.base_branch)
        item.head_branch = _string(head.get("ref"), item.head_branch)
        item.additions = _integer(data.get("additions"))
        item.deletions = _integer(data.get("deletions"))
        item.changed_files = _integer(data.get("changed_files"))
        item.commits_count = _integer(data.get("commits"))
        item.comments_count = _integer(data.get("comments"))
        item.review_comments_count = _integer(data.get("review_comments"))
        item.html_url = _string(data.get("html_url"), item.html_url)
        item.synced_at = datetime.now(UTC)
        session.flush()
        session.execute(delete(GitHubPRLabel).where(GitHubPRLabel.pull_request_id == item.id))
        for raw_label in data.get("labels", []):
            label = self._label(session, repository.id, raw_label)
            if label:
                session.add(GitHubPRLabel(pull_request_id=item.id, label_id=label.id))
        return item

    def _issue(
        self,
        session: Session,
        repository: Repository,
        data: dict[str, Any],
        state: GitHubSyncState,
    ) -> GitHubIssue:
        number = _integer(data.get("number"))
        github_id = _integer(data.get("id"))
        created = _datetime(data.get("created_at"))
        updated = _datetime(data.get("updated_at"))
        if not number or not github_id or created is None or updated is None:
            raise IngestionError("GITHUB_API_ERROR", "Issue metadata is incomplete.", 502)
        item = session.scalar(
            select(GitHubIssue).where(
                GitHubIssue.repository_id == repository.id, GitHubIssue.number == number
            )
        )
        user, login = self._user(session, data.get("user"))
        milestone_value = data.get("milestone")
        milestone: dict[str, Any] = milestone_value if isinstance(milestone_value, dict) else {}
        if item is None:
            item = GitHubIssue(
                repository_id=repository.id,
                github_issue_id=github_id,
                number=number,
                title=_string(data.get("title"), "Untitled issue"),
                state=_string(data.get("state"), "open"),
                created_at=created,
                updated_at=updated,
                html_url=_string(data.get("html_url"), repository.url),
            )
            session.add(item)
        item.github_issue_id = github_id
        item.title = _string(data.get("title"), item.title)
        item.body = self._body(data.get("body"), state)
        item.state = _string(data.get("state"), item.state)
        item.author_id = user.id if user else None
        item.author_login = login
        item.created_at = created
        item.updated_at = updated
        item.closed_at = _datetime(data.get("closed_at"))
        item.html_url = _string(data.get("html_url"), item.html_url)
        item.comments_count = _integer(data.get("comments"))
        item.milestone = _string(milestone.get("title")) or None
        item.synced_at = datetime.now(UTC)
        session.flush()
        session.execute(delete(GitHubIssueLabel).where(GitHubIssueLabel.issue_id == item.id))
        for raw_label in data.get("labels", []):
            label = self._label(session, repository.id, raw_label)
            if label:
                session.add(GitHubIssueLabel(issue_id=item.id, label_id=label.id))
        return item

    def _comment(
        self,
        session: Session,
        repository: Repository,
        data: dict[str, Any],
        state: GitHubSyncState,
        *,
        comment_type: str,
        pull_request_id: UUID | None = None,
        issue_id: UUID | None = None,
    ) -> None:
        github_id = _integer(data.get("id"))
        created = _datetime(data.get("created_at"))
        updated = _datetime(data.get("updated_at")) or created
        if not github_id or created is None or updated is None:
            return
        item = session.scalar(
            select(GitHubComment).where(
                GitHubComment.repository_id == repository.id,
                GitHubComment.github_comment_id == github_id,
                GitHubComment.comment_type == comment_type,
            )
        )
        user, login = self._user(session, data.get("user"))
        if item is None:
            item = GitHubComment(
                github_comment_id=github_id,
                repository_id=repository.id,
                comment_type=comment_type,
                created_at=created,
                updated_at=updated,
                html_url=_string(data.get("html_url"), repository.url),
            )
            session.add(item)
        item.issue_id = issue_id
        item.pull_request_id = pull_request_id
        item.author_id = user.id if user else None
        item.author_login = login
        item.body = self._body(data.get("body"), state)
        item.created_at = created
        item.updated_at = updated
        item.html_url = _string(data.get("html_url"), item.html_url)
        item.path = _string(data.get("path")) or None
        item.commit_sha = _string(data.get("commit_id")) or None
        item.original_commit_sha = _string(data.get("original_commit_id")) or None
        item.line = data.get("line") if isinstance(data.get("line"), int) else None
        item.original_line = (
            data.get("original_line") if isinstance(data.get("original_line"), int) else None
        )
        item.side = _string(data.get("side")) or None
        item.diff_hunk = self._body(data.get("diff_hunk"), state)
        item.synced_at = datetime.now(UTC)

    async def _sync(self, session: Session, repository: Repository, job: AnalysisJob) -> None:
        state = self._state(session, repository.id)
        state.status = "syncing"
        state.sync_error = None
        state.github_index_limited = False
        self._progress(session, state, job, "fetching_repository_metadata", 5)
        base = f"/repos/{repository.owner}/{repository.name}"
        async with self.client_factory() as client:
            metadata = await client.get(base, etag=state.repository_etag)
            if not metadata.not_modified:
                if not isinstance(metadata.data, dict):
                    raise IngestionError(
                        "GITHUB_API_ERROR", "GitHub repository metadata is invalid.", 502
                    )
                self._metadata(session, repository, metadata.data, state)
                state.repository_etag = metadata.etag
            self._progress(session, state, job, "fetching_pull_requests", 15)
            pull_page = await client.paginate(
                f"{base}/pulls",
                params={"state": "all", "sort": "updated", "direction": "desc"},
                max_items=self.settings.max_github_pull_requests,
            )
            state.github_index_limited = state.github_index_limited or pull_page.limited
            newest_pr = state.last_pr_updated_at
            changed_pulls: list[dict[str, Any]] = []
            for summary in pull_page.items:
                updated = _datetime(summary.get("updated_at"))
                if newest_pr is None or (updated and updated > newest_pr):
                    changed_pulls.append(summary)
            if state.last_synced_at is None:
                changed_pulls = pull_page.items
            comment_budget = self.settings.max_github_comments
            review_budget = self.settings.max_github_review_comments
            for index, summary in enumerate(changed_pulls):
                number = _integer(summary.get("number"))
                detail_response = await client.get(f"{base}/pulls/{number}")
                if not isinstance(detail_response.data, dict):
                    continue
                pull_request = self._pull_request(session, repository, detail_response.data, state)
                commit_page = await client.paginate(
                    f"{base}/pulls/{number}/commits",
                    max_items=max(1, self.settings.max_commits),
                )
                state.github_index_limited = state.github_index_limited or commit_page.limited
                session.execute(
                    delete(GitHubPRCommit).where(GitHubPRCommit.pull_request_id == pull_request.id)
                )
                for commit_data in commit_page.items:
                    sha = _string(commit_data.get("sha"))
                    if len(sha) == 40:
                        session.add(
                            GitHubPRCommit(
                                repository_id=repository.id,
                                pull_request_id=pull_request.id,
                                commit_sha=sha,
                            )
                        )
                if comment_budget > 0:
                    comments = await client.paginate(
                        f"{base}/issues/{number}/comments", max_items=comment_budget
                    )
                    session.execute(
                        delete(GitHubComment).where(
                            GitHubComment.pull_request_id == pull_request.id,
                            GitHubComment.comment_type == "pr_comment",
                        )
                    )
                    for data in comments.items:
                        self._comment(
                            session,
                            repository,
                            data,
                            state,
                            comment_type="pr_comment",
                            pull_request_id=pull_request.id,
                        )
                    comment_budget -= len(comments.items)
                    state.github_index_limited = state.github_index_limited or comments.limited
                elif pull_request.comments_count > 0:
                    state.github_index_limited = True
                if review_budget > 0:
                    reviews = await client.paginate(
                        f"{base}/pulls/{number}/comments", max_items=review_budget
                    )
                    session.execute(
                        delete(GitHubComment).where(
                            GitHubComment.pull_request_id == pull_request.id,
                            GitHubComment.comment_type == "review_comment",
                        )
                    )
                    for data in reviews.items:
                        self._comment(
                            session,
                            repository,
                            data,
                            state,
                            comment_type="review_comment",
                            pull_request_id=pull_request.id,
                        )
                    review_budget -= len(reviews.items)
                    state.github_index_limited = state.github_index_limited or reviews.limited
                elif pull_request.review_comments_count > 0:
                    state.github_index_limited = True
                job.progress = 15 + 35 * (index + 1) / max(1, len(changed_pulls))
                state.progress = job.progress
                session.commit()
            pr_updates = [_datetime(item.get("updated_at")) for item in pull_page.items]
            valid_pr_updates = [item for item in pr_updates if item]
            if valid_pr_updates:
                state.last_pr_updated_at = max(valid_pr_updates)

            self._progress(session, state, job, "fetching_issues", 55)
            issue_params: dict[str, str | int] = {
                "state": "all",
                "sort": "updated",
                "direction": "desc",
            }
            if state.last_issue_updated_at:
                issue_params["since"] = state.last_issue_updated_at.isoformat()
            issue_page = await client.paginate(
                f"{base}/issues",
                params=issue_params,
                max_items=self.settings.max_github_issues,
            )
            state.github_index_limited = state.github_index_limited or issue_page.limited
            genuine_issues = [item for item in issue_page.items if "pull_request" not in item]
            for index, data in enumerate(genuine_issues):
                issue = self._issue(session, repository, data, state)
                if comment_budget > 0:
                    comments = await client.paginate(
                        f"{base}/issues/{issue.number}/comments", max_items=comment_budget
                    )
                    session.execute(
                        delete(GitHubComment).where(
                            GitHubComment.issue_id == issue.id,
                            GitHubComment.comment_type == "issue_comment",
                        )
                    )
                    for comment in comments.items:
                        self._comment(
                            session,
                            repository,
                            comment,
                            state,
                            comment_type="issue_comment",
                            issue_id=issue.id,
                        )
                    comment_budget -= len(comments.items)
                    state.github_index_limited = state.github_index_limited or comments.limited
                elif issue.comments_count > 0:
                    state.github_index_limited = True
                job.progress = 55 + 25 * (index + 1) / max(1, len(genuine_issues))
                state.progress = job.progress
                session.commit()
            issue_updates = [_datetime(item.get("updated_at")) for item in genuine_issues]
            valid_issue_updates = [item for item in issue_updates if item]
            if valid_issue_updates:
                state.last_issue_updated_at = max(valid_issue_updates)

            self._progress(session, state, job, "linking_development_context", 85)
            self.linking.rebuild(session, repository)
            state.pull_requests_indexed = (
                session.scalar(
                    select(func.count())
                    .select_from(GitHubPullRequest)
                    .where(GitHubPullRequest.repository_id == repository.id)
                )
                or 0
            )
            state.issues_indexed = (
                session.scalar(
                    select(func.count())
                    .select_from(GitHubIssue)
                    .where(GitHubIssue.repository_id == repository.id)
                )
                or 0
            )
            state.comments_indexed = (
                session.scalar(
                    select(func.count())
                    .select_from(GitHubComment)
                    .where(
                        GitHubComment.repository_id == repository.id,
                        GitHubComment.comment_type.in_(["issue_comment", "pr_comment"]),
                    )
                )
                or 0
            )
            state.review_comments_indexed = (
                session.scalar(
                    select(func.count())
                    .select_from(GitHubComment)
                    .where(
                        GitHubComment.repository_id == repository.id,
                        GitHubComment.comment_type == "review_comment",
                    )
                )
                or 0
            )
            state.rate_limit_remaining = client.rate_limit.remaining
            state.rate_limit_reset_at = client.rate_limit.reset_at
            state.last_synced_at = datetime.now(UTC)
            state.status = "limited" if state.github_index_limited else "ready"
            state.current_step = "ready"
            state.progress = None
            session.commit()


def index_github_repository(engine: Engine, repository_id: UUID, job_id: UUID) -> None:
    lock_key = int.from_bytes(repository_id.bytes[:8], signed=True)
    with engine.connect() as lock_connection:
        acquired = lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
        )
        lock_connection.commit()
        if not acquired:
            return
        try:
            with Session(engine, expire_on_commit=False) as session:
                job = session.get(AnalysisJob, job_id)
                repository = session.get(Repository, repository_id)
                if job is None or repository is None or job.repository_id != repository_id:
                    return
                state = GitHubIndexService()._state(session, repository_id)
                try:
                    job.status = JobStatus.running
                    job.started_at = job.started_at or datetime.now(UTC)
                    GitHubIndexService().run(session, repository, job)
                    job.status = JobStatus.completed
                    job.current_step = "completed"
                    job.progress = None
                    job.completed_at = datetime.now(UTC)
                    session.commit()
                except Exception as error:
                    session.rollback()
                    state = GitHubIndexService()._state(session, repository_id)
                    code = error.code if isinstance(error, IngestionError) else "GITHUB_SYNC_FAILED"
                    message = (
                        error.message
                        if isinstance(error, IngestionError)
                        else "GitHub context synchronization failed. Retry later."
                    )
                    state.status = "rate_limited" if code == "GITHUB_RATE_LIMITED" else "failed"
                    if isinstance(error, GitHubRateLimitedError):
                        state.rate_limit_remaining = error.remaining
                        state.rate_limit_reset_at = error.reset_at
                    state.current_step = None
                    state.progress = None
                    state.sync_error = message
                    job.status = JobStatus.failed
                    job.error_message = message
                    job.progress = None
                    job.completed_at = datetime.now(UTC)
                    session.commit()
                    logger.exception(
                        "github_sync_failed",
                        extra={
                            "repository_id": repository_id,
                            "job_id": job_id,
                            "error_code": code,
                        },
                    )
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            lock_connection.commit()
