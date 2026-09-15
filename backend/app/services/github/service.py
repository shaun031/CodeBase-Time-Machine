from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.ingestion_errors import IngestionError
from app.db.models import (
    Commit,
    CommitPRLink,
    GitHubComment,
    GitHubIssue,
    GitHubIssueLabel,
    GitHubIssueReference,
    GitHubLabel,
    GitHubPRCommit,
    GitHubPRLabel,
    GitHubPullRequest,
    GitHubSyncState,
    Repository,
    SymbolChangeEvent,
    SymbolLineage,
)
from app.schemas.git import CommitSummary
from app.schemas.github import (
    AffectedSymbol,
    CommitContext,
    GitHubCommentRead,
    GitHubLabelRead,
    GitHubStatus,
    IssueDetail,
    IssuePage,
    IssueReferenceRead,
    IssueSummary,
    PullRequestDetail,
    PullRequestPage,
    PullRequestSummary,
    RelatedPullRequest,
    SymbolContext,
    SymbolContextEvent,
)
from app.services.github.models import HistoricalEvidence
from app.services.history import HistoryService
from app.services.repositories import active_job, get_repository


class GitHubService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _repository(self, repository_id: UUID, *, require_context: bool = True) -> Repository:
        repository = get_repository(self.session, repository_id)
        state = self.session.get(GitHubSyncState, repository_id)
        if require_context and (state is None or state.status not in {"ready", "limited"}):
            raise IngestionError(
                "GITHUB_CONTEXT_NOT_READY",
                "GitHub context is unavailable. Start or retry GitHub synchronization.",
                409,
            )
        return repository

    def status(self, repository_id: UUID) -> GitHubStatus:
        self._repository(repository_id, require_context=False)
        state = self.session.get(GitHubSyncState, repository_id)
        job = active_job(self.session, repository_id)
        if state is None:
            return GitHubStatus(
                status="not_synced",
                progress=None,
                current_step=None,
                last_synced_at=None,
                pull_requests_indexed=0,
                issues_indexed=0,
                comments_indexed=0,
                review_comments_indexed=0,
                rate_limit_remaining=None,
                rate_limit_reset_at=None,
                sync_error=None,
                github_index_limited=False,
            )
        github_job = job if job and job.job_type == "github_sync" else None
        return GitHubStatus(
            status=state.status,
            progress=github_job.progress if github_job else state.progress,
            current_step=github_job.current_step if github_job else state.current_step,
            last_synced_at=state.last_synced_at,
            pull_requests_indexed=state.pull_requests_indexed,
            issues_indexed=state.issues_indexed,
            comments_indexed=state.comments_indexed,
            review_comments_indexed=state.review_comments_indexed,
            rate_limit_remaining=state.rate_limit_remaining,
            rate_limit_reset_at=state.rate_limit_reset_at,
            sync_error=state.sync_error,
            github_index_limited=state.github_index_limited,
            job_id=github_job.id if github_job else None,
        )

    def _labels(self, owner_type: str, owner_id: UUID) -> list[GitHubLabelRead]:
        association = GitHubPRLabel if owner_type == "pull_request" else GitHubIssueLabel
        owner_column = (
            GitHubPRLabel.pull_request_id
            if owner_type == "pull_request"
            else GitHubIssueLabel.issue_id
        )
        rows = self.session.scalars(
            select(GitHubLabel)
            .join(association, association.label_id == GitHubLabel.id)
            .where(owner_column == owner_id)
            .order_by(func.lower(GitHubLabel.name))
        )
        return [
            GitHubLabelRead(name=row.name, description=row.description, color=row.color)
            for row in rows
        ]

    def _pr_summary(self, item: GitHubPullRequest) -> PullRequestSummary:
        return PullRequestSummary(
            id=item.id,
            number=item.number,
            title=item.title,
            state=item.state,
            draft=item.draft,
            merged=item.merged,
            author_login=item.author_login,
            created_at=item.created_at,
            updated_at=item.updated_at,
            merged_at=item.merged_at,
            closed_at=item.closed_at,
            html_url=item.html_url,
            commits_count=item.commits_count,
            labels=self._labels("pull_request", item.id),
        )

    def _issue_summary(self, item: GitHubIssue) -> IssueSummary:
        return IssueSummary(
            id=item.id,
            number=item.number,
            title=item.title,
            state=item.state,
            author_login=item.author_login,
            created_at=item.created_at,
            updated_at=item.updated_at,
            closed_at=item.closed_at,
            html_url=item.html_url,
            milestone=item.milestone,
            labels=self._labels("issue", item.id),
        )

    @staticmethod
    def _comment(item: GitHubComment) -> GitHubCommentRead:
        return GitHubCommentRead(
            id=item.id,
            comment_type=item.comment_type,
            author_login=item.author_login,
            body=item.body,
            created_at=item.created_at,
            updated_at=item.updated_at,
            html_url=item.html_url,
            path=item.path,
            commit_sha=item.commit_sha,
            original_commit_sha=item.original_commit_sha,
            line=item.line,
            original_line=item.original_line,
            side=item.side,
            diff_hunk=item.diff_hunk,
        )

    def pull_requests(
        self,
        repository_id: UUID,
        state: str | None,
        search: str | None,
        author: str | None,
        label: str | None,
        page: int,
        page_size: int,
    ) -> PullRequestPage:
        self._repository(repository_id)
        query = select(GitHubPullRequest).where(GitHubPullRequest.repository_id == repository_id)
        if state and state != "all":
            query = query.where(GitHubPullRequest.state == state)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(GitHubPullRequest.title.ilike(pattern), GitHubPullRequest.body.ilike(pattern))
            )
        if author:
            query = query.where(GitHubPullRequest.author_login.ilike(author))
        if label:
            query = query.join(
                GitHubPRLabel, GitHubPRLabel.pull_request_id == GitHubPullRequest.id
            ).join(GitHubLabel, GitHubPRLabel.label_id == GitHubLabel.id)
            query = query.where(GitHubLabel.name.ilike(label))
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self.session.scalars(
            query.order_by(GitHubPullRequest.updated_at.desc(), GitHubPullRequest.number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return PullRequestPage(
            items=[self._pr_summary(item) for item in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    def issues(
        self,
        repository_id: UUID,
        state: str | None,
        search: str | None,
        author: str | None,
        label: str | None,
        page: int,
        page_size: int,
    ) -> IssuePage:
        self._repository(repository_id)
        query = select(GitHubIssue).where(GitHubIssue.repository_id == repository_id)
        if state and state != "all":
            query = query.where(GitHubIssue.state == state)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(GitHubIssue.title.ilike(pattern), GitHubIssue.body.ilike(pattern))
            )
        if author:
            query = query.where(GitHubIssue.author_login.ilike(author))
        if label:
            query = query.join(GitHubIssueLabel, GitHubIssueLabel.issue_id == GitHubIssue.id).join(
                GitHubLabel, GitHubIssueLabel.label_id == GitHubLabel.id
            )
            query = query.where(GitHubLabel.name.ilike(label))
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self.session.scalars(
            query.order_by(GitHubIssue.updated_at.desc(), GitHubIssue.number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return IssuePage(
            items=[self._issue_summary(item) for item in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    def _pr(self, repository_id: UUID, number: int) -> GitHubPullRequest:
        self._repository(repository_id)
        item = self.session.scalar(
            select(GitHubPullRequest).where(
                GitHubPullRequest.repository_id == repository_id,
                GitHubPullRequest.number == number,
            )
        )
        if item is None:
            raise IngestionError("PULL_REQUEST_NOT_FOUND", "Pull request not found.", 404)
        return item

    def _issue(self, repository_id: UUID, number: int) -> GitHubIssue:
        self._repository(repository_id)
        item = self.session.scalar(
            select(GitHubIssue).where(
                GitHubIssue.repository_id == repository_id, GitHubIssue.number == number
            )
        )
        if item is None:
            raise IngestionError("ISSUE_NOT_FOUND", "Issue not found.", 404)
        return item

    def _issue_reference(self, item: GitHubIssueReference) -> IssueReferenceRead:
        issue = (
            self.session.get(GitHubIssue, item.target_issue_id) if item.target_issue_id else None
        )
        return IssueReferenceRead(
            issue=self._issue_summary(issue) if issue else None,
            owner=item.target_owner,
            repository=item.target_repository,
            number=item.target_number,
            reference_type=item.reference_type,
            raw_reference=item.raw_reference,
            confidence=item.confidence,
            external=issue is None,
        )

    def _affected_symbols_for_pr(self, pull_request_id: UUID) -> list[AffectedSymbol]:
        rows = self.session.execute(
            select(SymbolChangeEvent, SymbolLineage, Commit)
            .join(CommitPRLink, CommitPRLink.commit_id == SymbolChangeEvent.commit_id)
            .join(SymbolLineage, SymbolLineage.id == SymbolChangeEvent.lineage_id)
            .join(Commit, Commit.id == SymbolChangeEvent.commit_id)
            .where(CommitPRLink.pull_request_id == pull_request_id)
            .distinct(SymbolChangeEvent.id)
            .order_by(SymbolChangeEvent.id)
        )
        return [
            AffectedSymbol(
                lineage_id=event.lineage_id,
                name=lineage.current_qualified_name or lineage.current_name or "Deleted symbol",
                symbol_kind=lineage.symbol_kind,
                file_path=lineage.current_file_path,
                event_type=event.event_type,
                commit_sha=commit.sha,
            )
            for event, lineage, commit in rows
        ]

    def pull_request(self, repository_id: UUID, number: int) -> PullRequestDetail:
        item = self._pr(repository_id, number)
        summary = self._pr_summary(item)
        memberships = list(
            self.session.scalars(
                select(GitHubPRCommit)
                .where(GitHubPRCommit.pull_request_id == item.id)
                .order_by(GitHubPRCommit.created_at, GitHubPRCommit.commit_sha)
            )
        )
        commit_shas = [row.commit_sha for row in memberships]
        commits = (
            list(
                self.session.scalars(
                    select(Commit)
                    .where(
                        Commit.repository_id == repository_id,
                        Commit.sha.in_(commit_shas),
                    )
                    .order_by(Commit.committed_at, Commit.sha)
                )
            )
            if commit_shas
            else []
        )
        references = self.session.scalars(
            select(GitHubIssueReference).where(
                GitHubIssueReference.source_type == "pull_request",
                GitHubIssueReference.source_id == item.id,
            )
        )
        comments = list(
            self.session.scalars(
                select(GitHubComment)
                .where(GitHubComment.pull_request_id == item.id)
                .order_by(GitHubComment.created_at, GitHubComment.id)
            )
        )
        return PullRequestDetail(
            **summary.model_dump(),
            body=item.body,
            base_branch=item.base_branch,
            head_branch=item.head_branch,
            merge_commit_sha=item.merge_commit_sha,
            additions=item.additions,
            deletions=item.deletions,
            changed_files=item.changed_files,
            comments_count=item.comments_count,
            review_comments_count=item.review_comments_count,
            commits=[
                CommitSummary.model_validate(commit, from_attributes=True) for commit in commits
            ],
            commit_shas=commit_shas,
            linked_issues=[self._issue_reference(reference) for reference in references],
            comments=[
                self._comment(comment)
                for comment in comments
                if comment.comment_type == "pr_comment"
            ],
            review_comments=[
                self._comment(comment)
                for comment in comments
                if comment.comment_type == "review_comment"
            ],
            affected_symbols=self._affected_symbols_for_pr(item.id),
        )

    def issue(self, repository_id: UUID, number: int) -> IssueDetail:
        item = self._issue(repository_id, number)
        summary = self._issue_summary(item)
        references = list(
            self.session.scalars(
                select(GitHubIssueReference).where(
                    GitHubIssueReference.target_issue_id == item.id,
                    GitHubIssueReference.source_type == "pull_request",
                )
            )
        )
        related: list[RelatedPullRequest] = []
        prs: list[GitHubPullRequest] = []
        for reference in references:
            pull_request = self.session.get(GitHubPullRequest, reference.source_id)
            if pull_request:
                prs.append(pull_request)
                related.append(
                    RelatedPullRequest(
                        pull_request=self._pr_summary(pull_request),
                        relationship=reference.reference_type,
                        confidence=reference.confidence,
                    )
                )
        pr_ids = [row.id for row in prs]
        commits = (
            list(
                self.session.scalars(
                    select(Commit)
                    .join(CommitPRLink, CommitPRLink.commit_id == Commit.id)
                    .where(CommitPRLink.pull_request_id.in_(pr_ids))
                    .distinct()
                    .order_by(Commit.committed_at, Commit.sha)
                )
            )
            if pr_ids
            else []
        )
        direct_commit_ids = list(
            self.session.scalars(
                select(GitHubIssueReference.source_id).where(
                    GitHubIssueReference.target_issue_id == item.id,
                    GitHubIssueReference.source_type == "commit",
                )
            )
        )
        if direct_commit_ids:
            known = {row.id for row in commits}
            commits.extend(
                row
                for row in self.session.scalars(
                    select(Commit).where(Commit.id.in_(direct_commit_ids))
                )
                if row.id not in known
            )
        affected: dict[tuple[UUID, str, str], AffectedSymbol] = {}
        for pull_request in prs:
            for symbol in self._affected_symbols_for_pr(pull_request.id):
                affected[(symbol.lineage_id, symbol.event_type, symbol.commit_sha)] = symbol
        comments = self.session.scalars(
            select(GitHubComment)
            .where(GitHubComment.issue_id == item.id)
            .order_by(GitHubComment.created_at, GitHubComment.id)
        )
        return IssueDetail(
            **summary.model_dump(),
            body=item.body,
            comments_count=item.comments_count,
            comments=[self._comment(comment) for comment in comments],
            related_pull_requests=related,
            related_commits=[
                CommitSummary.model_validate(row, from_attributes=True) for row in commits
            ],
            affected_symbols=list(affected.values()),
        )

    def _issues_for_commit_and_prs(
        self, commit_id: UUID, pull_request_ids: list[UUID]
    ) -> list[IssueReferenceRead]:
        conditions = [
            and_(
                GitHubIssueReference.source_type == "commit",
                GitHubIssueReference.source_id == commit_id,
            )
        ]
        if pull_request_ids:
            conditions.append(
                and_(
                    GitHubIssueReference.source_type == "pull_request",
                    GitHubIssueReference.source_id.in_(pull_request_ids),
                )
            )
        rows = self.session.scalars(select(GitHubIssueReference).where(or_(*conditions)))
        unique: dict[tuple[str, str, int, str], IssueReferenceRead] = {}
        for row in rows:
            value = self._issue_reference(row)
            key = (value.owner, value.repository, value.number, value.reference_type)
            unique[key] = value
        return list(unique.values())

    def commit_context(self, repository_id: UUID, sha: str) -> CommitContext:
        self._repository(repository_id)
        commit = self.session.scalar(
            select(Commit).where(Commit.repository_id == repository_id, Commit.sha == sha)
        )
        if commit is None:
            raise IngestionError("COMMIT_NOT_FOUND", "Commit not found.", 404)
        pull_requests = list(
            self.session.scalars(
                select(GitHubPullRequest)
                .join(CommitPRLink, CommitPRLink.pull_request_id == GitHubPullRequest.id)
                .where(CommitPRLink.commit_id == commit.id)
                .distinct()
                .order_by(GitHubPullRequest.number)
            )
        )
        events = HistoryService(self.session).commit_events(repository_id, sha)
        return CommitContext(
            commit=CommitSummary.model_validate(commit, from_attributes=True),
            associated_pull_requests=[self._pr_summary(item) for item in pull_requests],
            referenced_issues=self._issues_for_commit_and_prs(
                commit.id, [item.id for item in pull_requests]
            ),
            symbol_changes=events,
        )

    def symbol_context(self, repository_id: UUID, lineage_id: UUID) -> SymbolContext:
        self._repository(repository_id)
        lineage = self.session.scalar(
            select(SymbolLineage).where(
                SymbolLineage.repository_id == repository_id, SymbolLineage.id == lineage_id
            )
        )
        if lineage is None:
            raise IngestionError("LINEAGE_NOT_FOUND", "Symbol lineage not found.", 404)
        history = HistoryService(self.session)
        rows = self.session.scalars(
            select(SymbolChangeEvent)
            .join(Commit, Commit.id == SymbolChangeEvent.commit_id)
            .where(SymbolChangeEvent.lineage_id == lineage_id)
            .order_by(Commit.committed_at, Commit.sha)
        )
        result: list[SymbolContextEvent] = []
        for event in rows:
            commit = self.session.get(Commit, event.commit_id)
            assert commit is not None
            pull_requests = list(
                self.session.scalars(
                    select(GitHubPullRequest)
                    .join(CommitPRLink, CommitPRLink.pull_request_id == GitHubPullRequest.id)
                    .where(CommitPRLink.commit_id == commit.id)
                    .distinct()
                )
            )
            pr_ids = [item.id for item in pull_requests]
            comments = (
                list(
                    self.session.scalars(
                        select(GitHubComment)
                        .where(GitHubComment.pull_request_id.in_(pr_ids))
                        .order_by(GitHubComment.created_at)
                    )
                )
                if pr_ids
                else []
            )
            result.append(
                SymbolContextEvent(
                    event=history._event_read(event),
                    commit=CommitSummary.model_validate(commit, from_attributes=True),
                    pull_requests=[self._pr_summary(item) for item in pull_requests],
                    issues=self._issues_for_commit_and_prs(commit.id, pr_ids),
                    comments=[self._comment(item) for item in comments],
                )
            )
        return SymbolContext(lineage_id=lineage_id, events=result)

    def evidence_for_symbol(
        self, repository_id: UUID, lineage_id: UUID
    ) -> list[HistoricalEvidence]:
        context = self.symbol_context(repository_id, lineage_id)
        evidence: list[HistoricalEvidence] = []
        for item in context.events:
            evidence.append(
                HistoricalEvidence(
                    type="commit",
                    source_id=item.commit.sha,
                    source_url=None,
                    title=item.commit.message.splitlines()[0] if item.commit.message else None,
                    body=item.commit.message,
                    author=item.commit.author_name,
                    created_at=item.commit.committed_at,
                    relationship=item.event.event_type,
                    confidence=1.0,
                )
            )
            evidence.extend(
                HistoricalEvidence(
                    type="pull_request",
                    source_id=str(pull_request.number),
                    source_url=pull_request.html_url,
                    title=pull_request.title,
                    body=None,
                    author=pull_request.author_login,
                    created_at=pull_request.created_at,
                    relationship="commit_pull_request",
                    confidence=0.99,
                )
                for pull_request in item.pull_requests
            )
        return evidence
