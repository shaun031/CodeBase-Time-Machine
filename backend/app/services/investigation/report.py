import json
import re
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AnalysisJob,
    ArchitectureEvolutionEvent,
    Commit,
    DependencyEdge,
    DependencyNode,
    FileChange,
    GitHubIssue,
    GitHubIssueReference,
    GitHubPRCommit,
    GitHubPullRequest,
    Investigation,
    InvestigationCandidateFeedback,
    JobStatus,
    Repository,
    SymbolChangeEvent,
    SymbolLineage,
)
from app.schemas.ai import AskResponse, EvidenceRead, GroundedClaim
from app.schemas.investigation import InvestigationCreate
from app.services.ai.archaeology import SoftwareArchaeologyService, validated_claims
from app.services.ai.context import RAGContextBuilder
from app.services.git import GitService
from app.services.investigation.error_search import ErrorSearchService
from app.services.investigation.regression import RegressionAnalysisService
from app.services.investigation.resolver import StackFrameResolver
from app.services.investigation.stacktrace import StackTraceParser

SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|token|secret|authorization|api[_-]?key)\b\s*[:=]\s*([^\s,;]+)"
)
AUTHORIZATION_PATTERN = re.compile(
    r"(?i)\bauthorization\b\s*[:=]\s*[^\r\n,;]+"
)


def sanitize_failure_text(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = AUTHORIZATION_PATTERN.sub("Authorization=[REDACTED]", value)
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)


class InvestigationReportService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.git = GitService(self.settings)
        self.resolver = StackFrameResolver(session)
        self.regression = RegressionAnalysisService(session, self.settings)

    def _repository(self, repository_id: UUID) -> Repository:
        repository = self.session.get(Repository, repository_id)
        if repository is None or not repository.local_path:
            raise IngestionError("REPOSITORY_NOT_FOUND", "Repository is not available.", 404)
        if repository.history_index_status not in {"ready", "limited"}:
            raise IngestionError(
                "INVESTIGATION_HISTORY_NOT_READY",
                "Historical indexing must be ready before an investigation.",
                409,
            )
        return repository

    @staticmethod
    def _input_type(payload: InvestigationCreate) -> str:
        kinds = []
        if payload.stack_trace:
            kinds.append("stack_trace")
        if payload.file_path:
            kinds.append("line" if payload.line else "file")
        if payload.lineage_id:
            kinds.append("symbol")
        if payload.known_good_commit:
            kinds.append("regression_range")
        if payload.error_message:
            kinds.append("error_message")
        return "+".join(kinds) or "unknown"

    def create(self, repository_id: UUID, payload: InvestigationCreate) -> dict[str, Any]:
        repository = self.session.scalar(
            select(Repository)
            .where(Repository.id == repository_id)
            .with_for_update()
        )
        if repository is None or not repository.local_path:
            raise IngestionError("REPOSITORY_NOT_FOUND", "Repository is not available.", 404)
        if repository.history_index_status not in {"ready", "limited"}:
            raise IngestionError(
                "INVESTIGATION_HISTORY_NOT_READY",
                "Historical indexing must be ready before an investigation.",
                409,
            )
        active = self.session.scalar(
            select(AnalysisJob).where(
                AnalysisJob.repository_id == repository_id,
                AnalysisJob.status.in_((JobStatus.queued, JobStatus.running)),
            )
        )
        if active is not None:
            raise IngestionError(
                "REPOSITORY_JOB_IN_PROGRESS",
                "Another analysis is already running for this repository.",
                409,
            )
        stack_trace = sanitize_failure_text(payload.stack_trace)
        if stack_trace and len(stack_trace) > self.settings.max_stack_trace_chars:
            raise IngestionError("STACK_TRACE_LIMIT_REACHED", "The stack trace is too large.", 413)
        job = AnalysisJob(
            repository_id=repository_id,
            job_type="bug_investigation",
            current_step="queued",
        )
        model = Investigation(
            repository_id=repository_id,
            status="pending",
            input_type=self._input_type(payload),
            stack_trace=stack_trace,
            error_message=sanitize_failure_text(payload.error_message),
            known_good_commit_sha=payload.known_good_commit,
            known_bad_commit_sha=payload.known_bad_commit,
            file_path=payload.file_path,
            line=payload.line,
            lineage_id=payload.lineage_id,
        )
        self.session.add_all([job, model])
        self.session.flush()
        model.job_id = job.id
        self.session.commit()
        try:
            from app.services.task_executor import task_executor

            task_executor.submit("build_investigation", repository_id, job.id)
        except Exception:
            model.status = "failed"
            model.error = "The investigation worker could not be started."
            job.status = JobStatus.failed
            job.error_message = model.error
            job.completed_at = datetime.now(UTC)
            self.session.commit()
            raise IngestionError(
                "INVESTIGATION_EXECUTOR_UNAVAILABLE",
                "The investigation worker could not be started.",
                503,
            ) from None
        return self.read(repository_id, model.id)

    def read(self, repository_id: UUID, investigation_id: UUID) -> dict[str, Any]:
        model = self.session.scalar(
            select(Investigation).where(
                Investigation.id == investigation_id,
                Investigation.repository_id == repository_id,
            )
        )
        if model is None:
            raise IngestionError("INVESTIGATION_NOT_FOUND", "Investigation not found.", 404)
        return {
            "id": model.id,
            "repository_id": model.repository_id,
            "job_id": model.job_id,
            "status": model.status,
            "input_type": model.input_type,
            "created_at": model.created_at,
            "completed_at": model.completed_at,
            "error": model.error,
            "result": model.result_summary,
        }

    def analyze(self, model: Investigation) -> dict[str, Any]:
        started = time.monotonic()
        repository = self._repository(model.repository_id)
        parser = StackTraceParser(
            self.settings.max_stack_trace_chars, self.settings.max_stack_frames
        )
        failure = parser.parse(model.stack_trace or "")
        if model.error_message:
            failure["error_message"] = model.error_message
        frames = list(failure["frames"])
        if model.file_path:
            frames.append(
                {
                    "index": len(frames),
                    "raw_text": f"{model.file_path}:{model.line or ''}",
                    "language": None,
                    "file_path": model.file_path,
                    "line": model.line,
                    "column": None,
                    "function_name": None,
                    "module": None,
                    "is_repository_frame": False,
                    "resolution_status": "unresolved",
                }
            )
        if model.lineage_id:
            lineage = self.session.scalar(
                select(SymbolLineage).where(
                    SymbolLineage.id == model.lineage_id,
                    SymbolLineage.repository_id == model.repository_id,
                )
            )
            if lineage is None:
                raise IngestionError("LINEAGE_NOT_FOUND", "Symbol lineage not found.", 404)
            if lineage.current_file_path:
                frames.append(
                    {
                        "index": len(frames),
                        "raw_text": lineage.current_qualified_name
                        or lineage.current_name
                        or "symbol",
                        "language": None,
                        "file_path": lineage.current_file_path,
                        "line": None,
                        "column": None,
                        "function_name": lineage.current_name,
                        "module": None,
                        "is_repository_frame": False,
                        "resolution_status": "unresolved",
                    }
                )
        resolved = self.resolver.resolve(model.repository_id, frames)
        target_sha = model.known_bad_commit_sha or repository.head_sha
        if not target_sha:
            raise IngestionError(
                "INVESTIGATION_COMMIT_NOT_INDEXED",
                "Repository HEAD is unavailable.",
                409,
            )

        regression_range = None
        range_shas: list[str] = []
        if model.known_good_commit_sha and model.known_bad_commit_sha:
            regression_range = self.regression.range(
                model.repository_id,
                model.known_good_commit_sha,
                model.known_bad_commit_sha,
            )
            range_shas = [item["sha"] for item in regression_range["commits"]]

        signals: dict[str, dict[str, float]] = defaultdict(dict)
        reasons: dict[str, set[str]] = defaultdict(set)
        evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
        files: dict[str, set[str]] = defaultdict(set)
        symbols: dict[str, set[str]] = defaultdict(set)
        recent_changes: list[dict[str, Any]] = []
        affected_symbols: dict[str, dict[str, Any]] = {}
        for frame in resolved:
            path = frame.get("resolved_path")
            symbol = frame.get("symbol")
            if symbol:
                affected_symbols[str(symbol["id"])] = {**symbol, "file_path": path}
            if path and isinstance(frame.get("line"), int):
                try:
                    blamed = self.git.get_blame(
                        self.git.storage.path(model.repository_id),
                        target_sha,
                        path,
                        int(frame["line"]),
                        int(frame["line"]),
                    )
                except IngestionError:
                    blamed = []
                for item in blamed:
                    signals[item.commit_sha]["blame"] = 1.0
                    reasons[item.commit_sha].add("blamed_failing_line")
                    files[item.commit_sha].add(path)
                    evidence[item.commit_sha].append(
                        {
                            "type": "blame",
                            "path": path,
                            "line": item.line,
                            "original_path": item.original_path,
                            "original_line": item.original_line,
                            "source": item.source[:500],
                        }
                    )
            if path:
                changes = self.session.execute(
                    select(Commit, FileChange)
                    .join(FileChange, FileChange.commit_id == Commit.id)
                    .where(
                        Commit.repository_id == model.repository_id,
                        or_(FileChange.old_path == path, FileChange.new_path == path),
                    )
                    .order_by(Commit.committed_at.desc())
                    .limit(20)
                )
                for commit, change in changes:
                    signals[commit.sha]["file_match"] = 1.0
                    reasons[commit.sha].add("changed_failing_file")
                    files[commit.sha].add(path)
                    recent_changes.append(
                        {
                            "commit_sha": commit.sha,
                            "message": commit.message,
                            "path": path,
                            "change_type": change.change_type,
                            "committed_at": commit.committed_at.isoformat(),
                        }
                    )
            if symbol and symbol.get("lineage_id"):
                rows = self.session.execute(
                    select(Commit, SymbolChangeEvent)
                    .join(SymbolChangeEvent, SymbolChangeEvent.commit_id == Commit.id)
                    .where(SymbolChangeEvent.lineage_id == UUID(symbol["lineage_id"]))
                )
                for commit, event in rows:
                    signals[commit.sha]["symbol_match"] = 1.0
                    reasons[commit.sha].add("changed_failing_symbol")
                    symbols[commit.sha].add(symbol["qualified_name"])
                    evidence[commit.sha].append(
                        {
                            "type": "symbol_history",
                            "event_type": event.event_type,
                            "lineage_id": symbol["lineage_id"],
                        }
                    )
        for sha in range_shas:
            signals[sha]["range_match"] = 1.0
            reasons[sha].add("inside_regression_range")

        error_results = ErrorSearchService(self.session, self.settings).search(
            model.repository_id, failure.get("error_message")
        )
        for search_result in error_results:
            matched_sha = search_result.get("commit_sha")
            if isinstance(matched_sha, str):
                signals[matched_sha]["error_text_match"] = 1.0
                reasons[matched_sha].add("error_text_match")
                evidence[matched_sha].append(search_result)

        candidates = self._rank_candidates(
            model.repository_id, signals, reasons, evidence, files, symbols
        )
        related_prs = {
            item["number"]: item
            for candidate in candidates
            for item in candidate.get("pull_requests", [])
        }
        related_issues = {
            item["number"]: item
            for candidate in candidates
            for item in candidate.get("issues", [])
        }
        candidate_shas = [item["commit_sha"] for item in candidates]
        dependency_context = self._dependency_context(model.repository_id, resolved)
        architecture_context = self._architecture_context(
            model.repository_id, sorted(set(range_shas + candidate_shas))
        )
        elapsed = time.monotonic() - started
        if elapsed > self.settings.max_investigation_build_seconds:
            raise IngestionError(
                "INVESTIGATION_TIME_LIMIT_REACHED",
                "The investigation exceeded its configured build time.",
                413,
            )
        return {
            "failure": failure,
            "resolved_frames": resolved,
            "affected_symbols": list(affected_symbols.values()),
            "regression_range": regression_range,
            "top_candidates": candidates,
            "related_prs": list(related_prs.values()),
            "related_issues": list(related_issues.values()),
            "recent_changes": recent_changes[:100],
            "error_search_results": error_results,
            "dependency_context": dependency_context,
            "architecture_context": architecture_context,
            "score_formula": (
                "0.45 blame + 0.25 symbol + 0.15 file + 0.10 range + "
                "0.05 exact error-text match"
            ),
            "score_meaning": (
                "The score orders investigation work; it is not a probability "
                "that a commit caused the bug."
            ),
            "facts": [
                (
                    "Repository frames and blame data were resolved from indexed "
                    "files and immutable Git objects."
                ),
                "No repository code, tests, scripts, or package managers were executed.",
            ],
            "limitations": [
                "Git history and blame do not prove causation.",
                (
                    "Blame identifies the last modifying commit and can be distorted "
                    "by refactors or formatting."
                ),
                "Static dependency analysis may miss dynamic runtime behavior.",
                "Squashed or incomplete history can hide intermediate changes.",
            ],
        }

    def _rank_candidates(
        self,
        repository_id: UUID,
        signals: dict[str, dict[str, float]],
        reasons: dict[str, set[str]],
        evidence: dict[str, list[dict[str, Any]]],
        files: dict[str, set[str]],
        symbols: dict[str, set[str]],
    ) -> list[dict[str, Any]]:
        weights = {
            "blame": 0.45,
            "symbol_match": 0.25,
            "file_match": 0.15,
            "range_match": 0.10,
            "error_text_match": 0.05,
        }
        commits = {
            item.sha: item
            for item in self.session.scalars(
                select(Commit).where(
                    Commit.repository_id == repository_id,
                    Commit.sha.in_(list(signals)),
                )
            )
        }
        items: list[dict[str, Any]] = []
        for sha, components in signals.items():
            commit = commits.get(sha)
            if commit is None:
                continue
            score = sum(weights.get(name, 0) * value for name, value in components.items())
            if commit.is_merge_commit or commit.files_changed > 100:
                components["mechanical_penalty"] = 0.4
                score *= 0.6
                reasons[sha].add("large_or_merge_commit_down_ranked")
            prs, issues = self._github_context(repository_id, sha)
            items.append(
                {
                    "commit_sha": sha,
                    "commit_id": str(commit.id),
                    "message": commit.message,
                    "committed_at": commit.committed_at.isoformat(),
                    "score": round(min(score, 1.0), 4),
                    "confidence": (
                        "strong candidate"
                        if score >= 0.7
                        else "moderate candidate"
                        if score >= 0.4
                        else "weak candidate"
                    ),
                    "reasons": sorted(reasons[sha]),
                    "signals": components,
                    "evidence": evidence[sha],
                    "files": sorted(files[sha]),
                    "symbols": sorted(symbols[sha]),
                    "pull_requests": prs,
                    "issues": issues,
                    "pr_numbers": [item["number"] for item in prs],
                    "issue_numbers": [item["number"] for item in issues],
                }
            )
        items.sort(
            key=lambda candidate: (
                -float(candidate["score"]),
                str(candidate["committed_at"]),
                str(candidate["commit_sha"]),
            )
        )
        for rank, candidate in enumerate(
            items[: self.settings.max_investigation_candidates], 1
        ):
            candidate["rank"] = rank
        return items[: self.settings.max_investigation_candidates]

    def _github_context(
        self, repository_id: UUID, sha: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        prs = list(
            self.session.scalars(
                select(GitHubPullRequest)
                .join(GitHubPRCommit, GitHubPRCommit.pull_request_id == GitHubPullRequest.id)
                .where(
                    GitHubPRCommit.repository_id == repository_id,
                    GitHubPRCommit.commit_sha == sha,
                )
            )
        )
        issues: dict[int, GitHubIssue] = {}
        if prs:
            for issue in self.session.scalars(
                select(GitHubIssue)
                .join(GitHubIssueReference, GitHubIssueReference.target_issue_id == GitHubIssue.id)
                .where(
                    GitHubIssueReference.repository_id == repository_id,
                    GitHubIssueReference.source_type == "pull_request",
                    GitHubIssueReference.source_id.in_([item.id for item in prs]),
                )
            ):
                issues[issue.number] = issue
        return (
            [
                {"number": item.number, "title": item.title, "html_url": item.html_url}
                for item in prs
            ],
            [
                {"number": item.number, "title": item.title, "html_url": item.html_url}
                for item in issues.values()
            ],
        )

    def _dependency_context(
        self, repository_id: UUID, frames: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        file_ids = [UUID(item["file_id"]) for item in frames if item.get("file_id")]
        symbol_ids = [UUID(item["symbol"]["id"]) for item in frames if item.get("symbol")]
        if not file_ids and not symbol_ids:
            return []
        targets = list(
            self.session.scalars(
                select(DependencyNode).where(
                    DependencyNode.repository_id == repository_id,
                    or_(
                        DependencyNode.file_id.in_(file_ids),
                        DependencyNode.symbol_id.in_(symbol_ids),
                    ),
                )
            )
        )
        all_nodes = {
            item.id: item
            for item in self.session.scalars(
                select(DependencyNode).where(
                    DependencyNode.repository_id == repository_id
                )
            )
        }
        target_ids = {item.id for item in targets}
        edges = self.session.scalars(
            select(DependencyEdge)
            .where(
                DependencyEdge.repository_id == repository_id,
                or_(
                    DependencyEdge.source_node_id.in_(target_ids),
                    DependencyEdge.target_node_id.in_(target_ids),
                ),
            )
            .limit(100)
        )
        return [
            {
                "source": all_nodes[edge.source_node_id].qualified_name,
                "target": all_nodes[edge.target_node_id].qualified_name,
                "edge_type": edge.edge_type,
                "confidence": edge.confidence,
                "relationship": "context only; this does not establish causation",
            }
            for edge in edges
            if edge.source_node_id in all_nodes and edge.target_node_id in all_nodes
        ]

    def _architecture_context(self, repository_id: UUID, shas: list[str]) -> list[dict[str, Any]]:
        if not shas:
            return []
        events = self.session.scalars(
            select(ArchitectureEvolutionEvent)
            .where(
                ArchitectureEvolutionEvent.repository_id == repository_id,
                ArchitectureEvolutionEvent.commit_sha.in_(shas),
            )
            .order_by(ArchitectureEvolutionEvent.committed_at)
            .limit(100)
        )
        return [
            {
                "event_type": item.event_type,
                "commit_sha": item.commit_sha,
                "source": item.source_stable_key,
                "target": item.target_stable_key,
                "confidence": item.confidence,
                "relationship": "investigation context only; this does not establish causation",
            }
            for item in events
        ]

    def line_history(
        self, repository_id: UUID, file_path: str, line: int, commit_sha: str | None
    ) -> dict[str, Any]:
        repository = self._repository(repository_id)
        target = self.git.validate_sha(commit_sha or repository.head_sha or "")
        indexed = self.session.scalar(
            select(Commit.id).where(
                Commit.repository_id == repository_id, Commit.sha == target
            )
        )
        if indexed is None:
            raise IngestionError("INVESTIGATION_COMMIT_NOT_INDEXED", "Commit is not indexed.", 404)
        frame = self.resolver.resolve(
            repository_id,
            [{"index": 0, "raw_text": f"{file_path}:{line}", "file_path": file_path, "line": line}],
        )[0]
        path = frame.get("resolved_path")
        if not path:
            return {
                "resolution": frame,
                "blame": None,
                "recent_commits": [],
                "historical_line_evidence": [],
            }
        blamed = self.git.get_blame(self.git.storage.path(repository_id), target, path, line, line)
        history = self.git.get_file_history(self.git.storage.path(repository_id), path)[:20]
        return {
            "resolution": frame,
            "blame": (
                {
                    "commit_sha": blamed[0].commit_sha,
                    "author": blamed[0].author,
                    "author_time": datetime.fromtimestamp(blamed[0].author_time, UTC),
                    "line": blamed[0].line,
                    "original_line": blamed[0].original_line,
                    "original_path": blamed[0].original_path,
                    "source": blamed[0].source,
                }
                if blamed else None
            ),
            "recent_commits": [
                {"sha": item.sha, "message": item.message, "committed_at": item.committed_at}
                for item in history
            ],
            "historical_line_evidence": (
                [
                    {
                        "type": "line_origin",
                        "commit_sha": blamed[0].commit_sha,
                        "path": blamed[0].original_path or path,
                        "line": blamed[0].original_line or line,
                    }
                ]
                if blamed else []
            ),
            "limitations": ["Line identity is approximate after substantial rewrites."],
        }

    def candidates(
        self,
        repository_id: UUID,
        investigation_id: UUID,
        file: str | None,
        symbol: str | None,
        min_score: float,
        limit: int,
    ) -> list[dict[str, Any]]:
        report = self.read(repository_id, investigation_id)
        result = report.get("result") or {}
        items = list(result.get("top_candidates") or [])
        if file:
            items = [item for item in items if file in item.get("files", [])]
        if symbol:
            items = [item for item in items if symbol in item.get("symbols", [])]
        return [item for item in items if float(item.get("score", 0)) >= min_score][:limit]

    def feedback(
        self, repository_id: UUID, investigation_id: UUID, commit_sha: str, result: str
    ) -> dict[str, Any]:
        self.read(repository_id, investigation_id)
        sha = self.git.validate_sha(commit_sha)
        model = self.session.scalar(
            select(InvestigationCandidateFeedback).where(
                InvestigationCandidateFeedback.investigation_id == investigation_id,
                InvestigationCandidateFeedback.commit_sha == sha,
            )
        )
        if model is None:
            model = InvestigationCandidateFeedback(
                investigation_id=investigation_id, commit_sha=sha, result=result
            )
            self.session.add(model)
        else:
            model.result = result
        self.session.commit()
        return {"investigation_id": investigation_id, "commit_sha": sha, "result": result}

    def explain(
        self, repository_id: UUID, investigation_id: UUID, question: str
    ) -> dict[str, Any]:
        investigation = self.read(repository_id, investigation_id)
        result = investigation.get("result")
        if investigation["status"] != "ready" or not isinstance(result, dict):
            raise IngestionError(
                "INVESTIGATION_NOT_READY",
                "The deterministic investigation report is not ready.",
                409,
            )
        evidence: list[EvidenceRead] = []
        for candidate in result.get("top_candidates", [])[:10]:
            sha = str(candidate.get("commit_sha") or "")
            evidence.append(
                EvidenceRead(
                    id=f"candidate:{sha}",
                    type="regression_candidate",
                    title=f"Ranked regression candidate {sha[:12]}",
                    text=json.dumps(
                        {
                            "candidate_status": "candidate, not confirmed cause",
                            "score": candidate.get("score"),
                            "reasons": candidate.get("reasons", []),
                            "signals": candidate.get("signals", {}),
                            "message": candidate.get("message"),
                            "files": candidate.get("files", []),
                            "symbols": candidate.get("symbols", []),
                        },
                        ensure_ascii=False,
                    ),
                    source_id=str(candidate.get("commit_id") or sha),
                    source_url=f"/repos/{repository_id}/commits/{sha}",
                    commit_sha=sha or None,
                    score=float(candidate.get("score") or 0),
                    relationship="direct",
                    retrieval_reason="deterministic_investigation_ranking",
                )
            )
        for index, frame in enumerate(result.get("resolved_frames", [])[:10]):
            evidence.append(
                EvidenceRead(
                    id=f"frame:{index}",
                    type="stack_frame",
                    title=f"Resolved stack frame {index}",
                    text=json.dumps(frame, ensure_ascii=False, default=str),
                    source_id=str(frame.get("file_id") or index),
                    file_path=frame.get("resolved_path"),
                    symbol_lineage_id=(frame.get("symbol") or {}).get("lineage_id"),
                    score=1.0 if frame.get("is_repository_frame") else 0.4,
                    relationship="direct",
                    retrieval_reason="resolved_stack_frame",
                )
            )
        context = RAGContextBuilder(self.settings).build(evidence)
        if not context.items:
            raise IngestionError(
                "INVESTIGATION_EVIDENCE_UNAVAILABLE",
                "The report has no evidence for a grounded explanation.",
                409,
            )
        ai = SoftwareArchaeologyService(self.session, self.settings)
        generated = ai._generate(question, [], context.text, context.sufficiency)
        claims = validated_claims(
            generated.claims, {item.id for item in context.items}
        )
        numbers = {item.id: index + 1 for index, item in enumerate(context.items)}
        answer = " ".join(
            f"{claim.text} "
            + "".join(f"[{numbers[item]}]" for item in claim.evidence_ids)
            for claim in claims
        ).strip()
        if not answer:
            answer = "The local model did not return claims grounded in the supplied report."
        confidence_by_sufficiency: dict[str, Literal["high", "medium", "low"]] = {
            "weak": "low",
            "moderate": "medium",
            "strong": "high",
        }
        maximum_confidence = confidence_by_sufficiency.get(context.sufficiency, "low")
        confidence_order = {"low": 0, "medium": 1, "high": 2}
        confidence = generated.confidence if claims else "low"
        if confidence_order[confidence] > confidence_order[maximum_confidence]:
            confidence = maximum_confidence
        response = AskResponse(
            answer=answer,
            claims=[
                GroundedClaim(text=claim.text, evidence_ids=claim.evidence_ids)
                for claim in claims
            ],
            confidence=confidence,
            evidence_sufficiency=context.sufficiency,
            evidence=context.items,
            limitations=list(
                dict.fromkeys(
                    [
                        *generated.limitations,
                        "Candidate ranking is investigation priority, not proof of causation.",
                    ]
                )
            ),
        )
        return response.model_dump(mode="json")


def build_investigation(engine: Engine, repository_id: UUID, job_id: UUID) -> None:
    with Session(engine, expire_on_commit=False) as session:
        job = session.get(AnalysisJob, job_id)
        model = session.scalar(select(Investigation).where(Investigation.job_id == job_id))
        if job is None or model is None or model.repository_id != repository_id:
            return
        job.status = JobStatus.running
        job.started_at = datetime.now(UTC)
        job.current_step = "resolving_failure_evidence"
        job.progress = 10
        model.status = "analyzing"
        session.commit()
        try:
            model.result_summary = InvestigationReportService(session).analyze(model)
            model.status = "ready"
            model.completed_at = datetime.now(UTC)
            job.status = JobStatus.completed
            job.progress = 100
            job.current_step = "ready"
            job.completed_at = model.completed_at
            session.commit()
        except Exception as error:
            session.rollback()
            job = session.get(AnalysisJob, job_id)
            model = session.scalar(select(Investigation).where(Investigation.job_id == job_id))
            if job and model:
                safe_message = (
                    str(error)
                    if isinstance(error, IngestionError)
                    else "Investigation analysis failed safely."
                )
                model.status = "failed"
                model.error = safe_message
                model.completed_at = datetime.now(UTC)
                job.status = JobStatus.failed
                job.error_message = safe_message
                job.completed_at = model.completed_at
                session.commit()
            raise
