import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.config import get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    ArchitectureBaseline,
    ArchitectureEvolutionEvent,
    ArchitectureHistoryState,
    ArchitectureRule,
    ArchitectureSnapshot,
    ArchitectureSnapshotEdge,
    ArchitectureSnapshotNode,
    ArchitectureViolation,
    GitHubIssue,
    GitHubIssueReference,
    GitHubPRCommit,
    GitHubPullRequest,
    Repository,
    Tag,
)
from app.schemas.architecture_history import ArchitectureBaselineWrite, ArchitectureRuleWrite
from app.services.architecture_history.compare import compare_graphs, events_from_comparison
from app.services.architecture_history.models import HistoricalEdge, HistoricalGraph, HistoricalNode
from app.services.architecture_history.rules import evaluate_rule, matches_selector, validate_rule


def graph_from_snapshot(session: Session, snapshot: ArchitectureSnapshot) -> HistoricalGraph:
    node_models = list(
        session.scalars(
            select(ArchitectureSnapshotNode).where(ArchitectureSnapshotNode.snapshot_id == snapshot.id)
        )
    )
    by_id = {node.id: node for node in node_models}
    nodes = [
        HistoricalNode(
            stable_key=node.stable_key,
            node_type=node.node_type,
            name=node.name,
            path=node.path,
            layer=node.layer,
            confidence=node.confidence,
            component_type=node.component_type,
            metrics=node.metrics_json or {},
            metadata=node.metadata_json or {},
        )
        for node in node_models
    ]
    edges = [
        HistoricalEdge(
            source=by_id[edge.source_node_id].stable_key,
            target=by_id[edge.target_node_id].stable_key,
            edge_type=edge.edge_type,
            weight=edge.weight,
            confidence=edge.confidence,
            resolution_type=edge.resolution_type,
            metadata=edge.metadata_json or {},
        )
        for edge in session.scalars(
            select(ArchitectureSnapshotEdge).where(ArchitectureSnapshotEdge.snapshot_id == snapshot.id)
        )
    ]
    return HistoricalGraph(nodes, edges, (snapshot.metadata_json or {}).get("cycles", []), snapshot.metrics_json or {})


class ArchitectureHistoryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _repository(self, repository_id: UUID) -> Repository:
        repository = self.session.get(Repository, repository_id)
        if repository is None:
            raise IngestionError("REPOSITORY_NOT_FOUND", "Repository not found.", 404)
        return repository

    def _ready(self, repository_id: UUID) -> tuple[Repository, ArchitectureHistoryState]:
        repository = self._repository(repository_id)
        state = self.session.get(ArchitectureHistoryState, repository_id)
        if state is None or state.status not in {"ready", "limited"}:
            raise IngestionError("ARCHITECTURE_HISTORY_NOT_INDEXED", "Build architecture history first.", 409)
        return repository, state

    def status(self, repository_id: UUID) -> dict[str, Any]:
        repository = self._repository(repository_id)
        state = self.session.get(ArchitectureHistoryState, repository_id)
        if state is None:
            return {
                "status": "not_indexed", "progress": None, "current_step": None,
                "commits_examined": 0, "snapshots_created": 0, "events_detected": 0,
                "cycles_detected": 0, "violations_detected": 0, "last_indexed_sha": None,
                "stale": False, "limited": False, "error": None, "job_id": None,
                "completed_at": None,
            }
        return {
            "status": state.status,
            "progress": state.progress,
            "current_step": state.current_step,
            "commits_examined": state.commits_examined,
            "snapshots_created": state.snapshots_created,
            "events_detected": state.events_detected,
            "cycles_detected": state.cycles_detected,
            "violations_detected": state.violations_detected,
            "last_indexed_sha": state.last_indexed_sha,
            "stale": bool(repository.head_sha and state.last_indexed_sha != repository.head_sha),
            "limited": state.limited,
            "error": state.error,
            "job_id": state.job_id,
            "completed_at": state.completed_at,
        }

    def snapshots(
        self,
        repository_id: UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        tag: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self._ready(repository_id)
        query = select(ArchitectureSnapshot).where(ArchitectureSnapshot.repository_id == repository_id)
        if from_date:
            query = query.where(ArchitectureSnapshot.committed_at >= from_date)
        if to_date:
            query = query.where(ArchitectureSnapshot.committed_at <= to_date)
        if tag:
            target = self.session.scalar(
                select(Tag.target_sha).where(Tag.repository_id == repository_id, Tag.name == tag)
            )
            if target is None:
                raise IngestionError("TAG_NOT_FOUND", "Tag not found.", 404)
            query = query.where(ArchitectureSnapshot.commit_sha == target)
        models = list(self.session.scalars(query.order_by(ArchitectureSnapshot.committed_at).limit(limit)))
        return [self._summary(item) for item in models]

    @staticmethod
    def _summary(snapshot: ArchitectureSnapshot) -> dict[str, Any]:
        return {
            "id": snapshot.id,
            "commit_sha": snapshot.commit_sha,
            "short_sha": snapshot.commit_sha[:12],
            "committed_at": snapshot.committed_at,
            "tags": (snapshot.metadata_json or {}).get("tags", []),
            "node_count": snapshot.node_count,
            "edge_count": snapshot.edge_count,
            "module_count": snapshot.module_count,
            "component_count": snapshot.component_count,
            "cycle_count": snapshot.cycle_count,
            "metrics": snapshot.metrics_json or {},
        }

    def _snapshot(
        self,
        repository_id: UUID,
        *,
        commit_sha: str | None = None,
        snapshot_id: UUID | None = None,
        tag: str | None = None,
    ) -> ArchitectureSnapshot:
        self._ready(repository_id)
        if tag:
            commit_sha = self.session.scalar(
                select(Tag.target_sha).where(Tag.repository_id == repository_id, Tag.name == tag)
            )
            if commit_sha is None:
                raise IngestionError("TAG_NOT_FOUND", "Tag not found.", 404)
        query = select(ArchitectureSnapshot).where(ArchitectureSnapshot.repository_id == repository_id)
        if snapshot_id:
            query = query.where(ArchitectureSnapshot.id == snapshot_id)
        elif commit_sha:
            query = query.where(ArchitectureSnapshot.commit_sha == commit_sha)
        else:
            query = query.order_by(ArchitectureSnapshot.committed_at.desc()).limit(1)
        snapshot = self.session.scalar(query)
        if snapshot is None:
            raise IngestionError("ARCHITECTURE_SNAPSHOT_NOT_FOUND", "No indexed architecture snapshot matches this reference.", 404)
        return snapshot

    def graph_at(self, repository_id: UUID, commit_sha: str) -> dict[str, Any]:
        if re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha) is None:
            raise IngestionError("INVALID_COMMIT_SHA", "A full 40-character commit SHA is required.", 422)
        snapshot = self._snapshot(repository_id, commit_sha=commit_sha)
        return self._graph_response(snapshot)

    def _graph_response(self, snapshot: ArchitectureSnapshot) -> dict[str, Any]:
        graph = graph_from_snapshot(self.session, snapshot)
        return {
            "snapshot": self._summary(snapshot),
            "nodes": [node.as_dict() for node in graph.nodes],
            "edges": [edge.as_dict() for edge in graph.edges],
            "cycles": graph.cycles,
            "metrics": graph.metrics,
            "source": "deterministic_static_analysis",
        }

    def compare(
        self,
        repository_id: UUID,
        *,
        from_commit: str | None = None,
        to_commit: str | None = None,
        from_snapshot_id: UUID | None = None,
        to_snapshot_id: UUID | None = None,
        from_tag: str | None = None,
        to_tag: str | None = None,
    ) -> dict[str, Any]:
        if not (from_commit or from_snapshot_id or from_tag) or not (
            to_commit or to_snapshot_id or to_tag
        ):
            raise IngestionError(
                "ARCHITECTURE_COMPARE_REFS_REQUIRED",
                "Provide both from and to architecture references.",
                422,
            )
        before = self._snapshot(repository_id, commit_sha=from_commit, snapshot_id=from_snapshot_id, tag=from_tag)
        after = self._snapshot(repository_id, commit_sha=to_commit, snapshot_id=to_snapshot_id, tag=to_tag)
        result = compare_graphs(
            graph_from_snapshot(self.session, before),
            graph_from_snapshot(self.session, after),
        )
        result.update(
            {
                "from_snapshot": self._summary(before),
                "to_snapshot": self._summary(after),
                "evolution_events": events_from_comparison(result),
            }
        )
        return result

    def evolution(
        self,
        repository_id: UUID,
        event_type: str | None = None,
        module: str | None = None,
        component: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self._ready(repository_id)
        query = select(ArchitectureEvolutionEvent).where(ArchitectureEvolutionEvent.repository_id == repository_id)
        if event_type:
            query = query.where(ArchitectureEvolutionEvent.event_type == event_type)
        if module:
            module_key = module if module.startswith("module:") else f"module:{module}"
            query = query.where(
                or_(
                    ArchitectureEvolutionEvent.source_stable_key == module_key,
                    ArchitectureEvolutionEvent.target_stable_key == module_key,
                )
            )
        if component:
            component_key = (
                component if component.startswith("component:") else f"component:{component}"
            )
            query = query.where(
                or_(
                    ArchitectureEvolutionEvent.source_stable_key == component_key,
                    ArchitectureEvolutionEvent.target_stable_key == component_key,
                )
            )
        if from_date:
            query = query.where(ArchitectureEvolutionEvent.committed_at >= from_date)
        if to_date:
            query = query.where(ArchitectureEvolutionEvent.committed_at <= to_date)
        events = list(self.session.scalars(query.order_by(ArchitectureEvolutionEvent.committed_at.desc()).limit(limit)))
        prs_by_sha: dict[str, list[dict[str, Any]]] = {}
        issues_by_sha: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            rows = list(self.session.execute(
                select(
                    GitHubPullRequest.id,
                    GitHubPullRequest.number,
                    GitHubPullRequest.title,
                    GitHubPullRequest.html_url,
                )
                .join(GitHubPRCommit, GitHubPRCommit.pull_request_id == GitHubPullRequest.id)
                .where(GitHubPRCommit.repository_id == repository_id, GitHubPRCommit.commit_sha == event.commit_sha)
            ))
            prs_by_sha[event.commit_sha] = [
                {"number": number, "title": title, "html_url": url}
                for _, number, title, url in rows
            ]
            pull_request_ids = [pull_request_id for pull_request_id, _, _, _ in rows]
            if pull_request_ids:
                issue_rows = self.session.execute(
                    select(GitHubIssue.number, GitHubIssue.title, GitHubIssue.html_url)
                    .join(
                        GitHubIssueReference,
                        GitHubIssueReference.target_issue_id == GitHubIssue.id,
                    )
                    .where(
                        GitHubIssueReference.repository_id == repository_id,
                        GitHubIssueReference.source_type == "pull_request",
                        GitHubIssueReference.source_id.in_(pull_request_ids),
                    )
                    .distinct()
                )
                issues_by_sha[event.commit_sha] = [
                    {"number": number, "title": title, "html_url": url}
                    for number, title, url in issue_rows
                ]
            else:
                issues_by_sha[event.commit_sha] = []
        return [
            {
                "id": event.id, "event_type": event.event_type, "commit_sha": event.commit_sha,
                "committed_at": event.committed_at, "source": event.source_stable_key,
                "target": event.target_stable_key, "old_value": event.old_value,
                "new_value": event.new_value, "confidence": event.confidence,
                "development_context": {
                    "pull_requests": prs_by_sha[event.commit_sha],
                    "issues": issues_by_sha[event.commit_sha],
                },
            }
            for event in events
        ]

    def trends(self, repository_id: UUID, limit: int = 500) -> dict[str, Any]:
        snapshots = self.snapshots(repository_id, limit=limit)
        return {
            "points": [
                {"commit_sha": item["commit_sha"], "committed_at": item["committed_at"], **item["metrics"]}
                for item in snapshots
            ],
            "definitions": {
                "dependency_density": "directed module dependencies / (modules × (modules - 1))",
                "fan_in": "number of incoming module dependencies",
                "fan_out": "number of outgoing module dependencies",
            },
        }

    def baselines(self, repository_id: UUID) -> list[dict[str, Any]]:
        self._ready(repository_id)
        values = list(self.session.scalars(select(ArchitectureBaseline).where(ArchitectureBaseline.repository_id == repository_id).order_by(ArchitectureBaseline.created_at)))
        return [{"id": value.id, "name": value.name, "snapshot_id": value.snapshot_id, "is_default": value.is_default, "created_at": value.created_at} for value in values]

    def create_baseline(self, repository_id: UUID, payload: ArchitectureBaselineWrite) -> dict[str, Any]:
        snapshot = self._snapshot(repository_id, commit_sha=payload.commit_sha, snapshot_id=payload.snapshot_id)
        if payload.is_default:
            for current in self.session.scalars(select(ArchitectureBaseline).where(ArchitectureBaseline.repository_id == repository_id)):
                current.is_default = False
        value = ArchitectureBaseline(repository_id=repository_id, name=payload.name, snapshot_id=snapshot.id, is_default=payload.is_default)
        self.session.add(value)
        self.session.commit()
        return {"id": value.id, "name": value.name, "snapshot_id": value.snapshot_id, "is_default": value.is_default, "created_at": value.created_at}

    def delete_baseline(self, repository_id: UUID, baseline_id: UUID) -> None:
        existing = self.session.scalar(
            select(ArchitectureBaseline.id).where(
                ArchitectureBaseline.repository_id == repository_id,
                ArchitectureBaseline.id == baseline_id,
            )
        )
        if existing is None:
            raise IngestionError("ARCHITECTURE_BASELINE_NOT_FOUND", "Baseline not found.", 404)
        self.session.execute(
            delete(ArchitectureBaseline).where(ArchitectureBaseline.id == baseline_id)
        )
        self.session.commit()

    def drift(self, repository_id: UUID, baseline_id: UUID | None = None, commit_sha: str | None = None) -> dict[str, Any]:
        if baseline_id:
            baseline = self.session.scalar(select(ArchitectureBaseline).where(ArchitectureBaseline.repository_id == repository_id, ArchitectureBaseline.id == baseline_id))
        else:
            baseline = self.session.scalar(select(ArchitectureBaseline).where(ArchitectureBaseline.repository_id == repository_id, ArchitectureBaseline.is_default.is_(True)))
        if baseline is None:
            raise IngestionError("ARCHITECTURE_BASELINE_NOT_FOUND", "Select or create a baseline first.", 404)
        current = self._snapshot(repository_id, commit_sha=commit_sha)
        result = self.compare(repository_id, from_snapshot_id=baseline.snapshot_id, to_snapshot_id=current.id)
        result["baseline"] = {"id": baseline.id, "name": baseline.name, "snapshot_id": baseline.snapshot_id}
        result["policy_violations"] = self.violations(repository_id, status="active", limit=500)
        return result

    def rules(self, repository_id: UUID) -> list[ArchitectureRule]:
        self._repository(repository_id)
        return list(self.session.scalars(select(ArchitectureRule).where(ArchitectureRule.repository_id == repository_id).order_by(ArchitectureRule.created_at)))

    def save_rule(self, repository_id: UUID, payload: ArchitectureRuleWrite, rule_id: UUID | None = None) -> ArchitectureRule:
        from app.services.architecture_history.indexer import rebuild_violations

        self._ready(repository_id)
        source = payload.source_selector.model_dump()
        target = payload.target_selector.model_dump() if payload.target_selector else None
        validate_rule(payload.rule_type, source, target)
        rule = self.session.get(ArchitectureRule, rule_id) if rule_id else None
        if rule_id and (rule is None or rule.repository_id != repository_id):
            raise IngestionError("ARCHITECTURE_RULE_NOT_FOUND", "Architecture rule not found.", 404)
        if rule is None:
            rule = ArchitectureRule(repository_id=repository_id)
            self.session.add(rule)
        rule.name = payload.name
        rule.description = payload.description
        rule.rule_type = payload.rule_type
        rule.source_selector = source
        rule.target_selector = target
        rule.severity = payload.severity
        rule.enabled = payload.enabled
        self.session.flush()
        rebuild_violations(self.session, repository_id)
        self.session.commit()
        return rule

    def delete_rule(self, repository_id: UUID, rule_id: UUID) -> None:
        existing = self.session.scalar(
            select(ArchitectureRule.id).where(
                ArchitectureRule.repository_id == repository_id,
                ArchitectureRule.id == rule_id,
            )
        )
        if existing is None:
            raise IngestionError("ARCHITECTURE_RULE_NOT_FOUND", "Architecture rule not found.", 404)
        self.session.execute(delete(ArchitectureRule).where(ArchitectureRule.id == rule_id))
        self.session.commit()

    def validate_preview(self, repository_id: UUID, payload: ArchitectureRuleWrite, commit_sha: str | None = None, from_commit: str | None = None, to_commit: str | None = None) -> dict[str, Any]:
        snapshots = self.snapshots(repository_id, limit=500)
        selected = snapshots
        if from_commit:
            positions = [index for index, item in enumerate(snapshots) if item["commit_sha"] == from_commit]
            if not positions:
                raise IngestionError("ARCHITECTURE_SNAPSHOT_NOT_FOUND", "The range start is not indexed.", 404)
            selected = selected[positions[0] :]
        if to_commit:
            positions = [index for index, item in enumerate(selected) if item["commit_sha"] == to_commit]
            if not positions:
                raise IngestionError("ARCHITECTURE_SNAPSHOT_NOT_FOUND", "The range end is not indexed.", 404)
            selected = selected[: positions[0] + 1]
        if commit_sha:
            selected = [item for item in snapshots if item["commit_sha"] == commit_sha]
        findings = []
        for item in selected:
            snapshot = self._snapshot(repository_id, snapshot_id=item["id"])
            for finding in evaluate_rule(
                graph_from_snapshot(self.session, snapshot),
                payload.rule_type,
                payload.source_selector.model_dump(),
                payload.target_selector.model_dump() if payload.target_selector else None,
                get_settings().architecture_rule_min_edge_confidence,
            ):
                findings.append({"commit_sha": snapshot.commit_sha, "committed_at": snapshot.committed_at, **finding})
        preview_graph = None
        if selected:
            preview_snapshot = self._snapshot(repository_id, snapshot_id=selected[-1]["id"])
            preview_graph = graph_from_snapshot(self.session, preview_snapshot)
        threshold = get_settings().architecture_rule_min_edge_confidence
        source_matches = 0 if preview_graph is None else sum(
            matches_selector(node, payload.source_selector.model_dump(), threshold)
            for node in preview_graph.nodes
        )
        target_matches = 0
        if preview_graph is not None and payload.target_selector is not None:
            target_matches = sum(
                matches_selector(node, payload.target_selector.model_dump(), threshold)
                for node in preview_graph.nodes
            )
        return {
            "valid": True,
            "snapshots_evaluated": len(selected),
            "source_match_count": source_matches,
            "target_match_count": target_matches,
            "violation_count": len(findings),
            "violations": findings[:500],
        }

    def violations(
        self,
        repository_id: UUID,
        status: str | None = None,
        rule_id: UUID | None = None,
        severity: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self._ready(repository_id)
        introduced = aliased(ArchitectureSnapshot)
        resolved = aliased(ArchitectureSnapshot)
        query = (
            select(
                ArchitectureViolation,
                ArchitectureRule,
                introduced.committed_at,
                resolved.committed_at,
            )
            .join(ArchitectureRule, ArchitectureRule.id == ArchitectureViolation.rule_id)
            .join(introduced, introduced.id == ArchitectureViolation.introduced_snapshot_id)
            .outerjoin(resolved, resolved.id == ArchitectureViolation.resolved_snapshot_id)
            .where(ArchitectureViolation.repository_id == repository_id)
        )
        if status:
            query = query.where(ArchitectureViolation.status == status)
        if rule_id:
            query = query.where(ArchitectureViolation.rule_id == rule_id)
        if severity:
            query = query.where(ArchitectureRule.severity == severity)
        if from_date:
            query = query.where(introduced.committed_at >= from_date)
        if to_date:
            query = query.where(introduced.committed_at <= to_date)
        rows = self.session.execute(query.order_by(ArchitectureViolation.created_at.desc()).limit(limit))
        return [{
            "id": violation.id, "rule_id": rule.id, "rule_name": rule.name,
            "rule_type": rule.rule_type, "severity": rule.severity, "status": violation.status,
            "source": violation.source_stable_key, "target": violation.target_stable_key,
            "introduced_commit_sha": violation.introduced_commit_sha,
            "resolved_commit_sha": violation.resolved_commit_sha,
            "introduced_at": introduced_at,
            "resolved_at": resolved_at,
            "lifetime_days": (
                ((resolved_at or datetime.now(introduced_at.tzinfo)) - introduced_at).days
                if introduced_at else None
            ),
            "confidence": violation.confidence, "evidence": violation.evidence,
        } for violation, rule, introduced_at, resolved_at in rows]
