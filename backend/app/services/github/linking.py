from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    Commit,
    CommitPRLink,
    GitHubIssue,
    GitHubIssueReference,
    GitHubPRCommit,
    GitHubPullRequest,
)
from app.db.models.repository import Repository
from app.services.github.parser import extract_issue_references


class GitHubLinkingService:
    """Build reproducible links while retaining relationship strength and evidence."""

    def rebuild(self, session: Session, repository: Repository) -> None:
        session.execute(delete(CommitPRLink).where(CommitPRLink.repository_id == repository.id))
        session.execute(
            delete(GitHubIssueReference).where(GitHubIssueReference.repository_id == repository.id)
        )
        commits = list(session.scalars(select(Commit).where(Commit.repository_id == repository.id)))
        commits_by_sha = {item.sha: item for item in commits}
        issues = list(
            session.scalars(select(GitHubIssue).where(GitHubIssue.repository_id == repository.id))
        )
        issues_by_number = {item.number: item for item in issues}
        pull_requests = list(
            session.scalars(
                select(GitHubPullRequest).where(GitHubPullRequest.repository_id == repository.id)
            )
        )
        memberships = list(
            session.scalars(
                select(GitHubPRCommit).where(GitHubPRCommit.repository_id == repository.id)
            )
        )
        for membership in memberships:
            commit = commits_by_sha.get(membership.commit_sha)
            if commit:
                session.add(
                    CommitPRLink(
                        repository_id=repository.id,
                        commit_id=commit.id,
                        pull_request_id=membership.pull_request_id,
                        link_type="pr_commit",
                        confidence=0.99,
                        evidence={"source": "github_pull_request_commits"},
                    )
                )
        for pull_request in pull_requests:
            if pull_request.merge_commit_sha:
                commit = commits_by_sha.get(pull_request.merge_commit_sha)
                if commit:
                    session.add(
                        CommitPRLink(
                            repository_id=repository.id,
                            commit_id=commit.id,
                            pull_request_id=pull_request.id,
                            link_type="merge_commit",
                            confidence=0.98,
                            evidence={"source": "github_merge_commit_sha"},
                        )
                    )
            self._references(
                session,
                repository,
                "pull_request",
                pull_request.id,
                f"{pull_request.title}\n{pull_request.body or ''}",
                issues_by_number,
            )
        for commit in commits:
            self._references(
                session,
                repository,
                "commit",
                commit.id,
                commit.message,
                issues_by_number,
            )
        session.flush()

    @staticmethod
    def _references(
        session: Session,
        repository: Repository,
        source_type: str,
        source_id: UUID,
        text: str | None,
        issues_by_number: dict[int, GitHubIssue],
    ) -> None:
        for reference in extract_issue_references(text):
            owner = reference.owner or repository.owner
            name = reference.repository or repository.name
            local = (
                owner.lower() == repository.owner.lower()
                and name.lower() == repository.name.lower()
            )
            target = issues_by_number.get(reference.number) if local else None
            session.add(
                GitHubIssueReference(
                    repository_id=repository.id,
                    source_type=source_type,
                    source_id=source_id,
                    target_issue_id=target.id if target else None,
                    target_owner=owner,
                    target_repository=name,
                    target_number=reference.number,
                    reference_type=reference.reference_type,
                    raw_reference=reference.raw_reference,
                    confidence=reference.confidence,
                )
            )
