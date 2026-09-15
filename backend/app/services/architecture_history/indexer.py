import logging
import time
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid5

from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AIAnswerCache,
    AnalysisJob,
    ArchitectureBaseline,
    ArchitectureEvolutionEvent,
    ArchitectureHistoryState,
    ArchitectureRule,
    ArchitectureSnapshot,
    ArchitectureSnapshotEdge,
    ArchitectureSnapshotNode,
    ArchitectureViolation,
    Commit,
    FileChange,
    JobStatus,
    Repository,
    Tag,
)
from app.parsers.registry import ParserRegistry
from app.services.architecture_history.builder import HistoricalArchitectureBuilder
from app.services.architecture_history.compare import compare_graphs, events_from_comparison
from app.services.architecture_history.models import HistoricalGraph
from app.services.architecture_history.rules import evaluate_rule
from app.services.git import GitService
from app.services.language_detector import LanguageDetector

logger = logging.getLogger("ctm")


def _architecture_path(path: str | None) -> bool:
    if not path:
        return False
    detection = LanguageDetector().detect(path)
    return not detection.excluded and (
        ParserRegistry().get(detection.language) is not None
        or PurePosixPath(path).suffix.lower() in {".html", ".htm", ".css"}
    )


def _select_commits(session: Session, repository_id: UUID, settings: Settings) -> tuple[list[Commit], bool]:
    commits = list(
        session.scalars(
            select(Commit)
            .where(Commit.repository_id == repository_id)
            .order_by(Commit.committed_at, Commit.sha)
        )
    )
    limited = len(commits) > settings.max_architecture_history_commits
    commits = commits[-settings.max_architecture_history_commits :]
    if settings.architecture_snapshot_strategy == "all" or len(commits) <= 2:
        selected = commits
    else:
        # Fetch paths once; an architecture snapshot is useful only after source changes.
        architecture_ids = {
            change.commit_id
            for change in session.scalars(
                select(FileChange).where(FileChange.repository_id == repository_id)
            )
            if _architecture_path(change.old_path) or _architecture_path(change.new_path)
        }
        if settings.architecture_snapshot_strategy == "interval":
            selected = [
                commit
                for index, commit in enumerate(commits)
                if index % settings.architecture_snapshot_interval_commits == 0
            ]
        else:
            selected = [commit for commit in commits if commit.id in architecture_ids]
    tags = set(
        session.scalars(select(Tag.target_sha).where(Tag.repository_id == repository_id))
    )
    required = {commits[0].sha, commits[-1].sha, *tags} if commits else set()
    selected_by_sha = {commit.sha: commit for commit in selected}
    selected_by_sha.update({commit.sha: commit for commit in commits if commit.sha in required})
    selected = sorted(selected_by_sha.values(), key=lambda item: (item.committed_at, item.sha))
    if len(selected) > settings.max_architecture_snapshots:
        limited = True
        keep = selected[-settings.max_architecture_snapshots :]
        if selected[0] not in keep:
            keep[0] = selected[0]
        selected = sorted(keep, key=lambda item: (item.committed_at, item.sha))
    return selected, limited


def _persist_graph(
    session: Session,
    repository: Repository,
    commit: Commit,
    graph: HistoricalGraph,
    tags: list[str],
) -> ArchitectureSnapshot:
    snapshot = ArchitectureSnapshot(
        id=uuid5(repository.id, f"architecture-snapshot:{commit.sha}"),
        repository_id=repository.id,
        commit_id=commit.id,
        commit_sha=commit.sha,
        committed_at=commit.committed_at,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        component_count=int(graph.metrics["component_count"]),
        module_count=int(graph.metrics["module_count"]),
        cycle_count=len(graph.cycles),
        metrics_json=graph.metrics,
        metadata_json={"cycles": graph.cycles, "tags": tags, "limited": graph.limited},
    )
    session.add(snapshot)
    node_models: dict[str, ArchitectureSnapshotNode] = {}
    for node in graph.nodes:
        model = ArchitectureSnapshotNode(
            id=uuid5(snapshot.id, f"node:{node.stable_key}"),
            snapshot_id=snapshot.id,
            stable_key=node.stable_key,
            node_type=node.node_type,
            name=node.name,
            path=node.path,
            component_type=node.component_type,
            layer=node.layer,
            confidence=node.confidence,
            metrics_json=node.metrics,
            metadata_json=node.metadata,
        )
        node_models[node.stable_key] = model
        session.add(model)
    session.flush()
    for edge in graph.edges:
        session.add(
            ArchitectureSnapshotEdge(
                id=uuid5(snapshot.id, f"edge:{edge.source}:{edge.target}:{edge.edge_type}"),
                snapshot_id=snapshot.id,
                source_node_id=node_models[edge.source].id,
                target_node_id=node_models[edge.target].id,
                edge_type=edge.edge_type,
                weight=edge.weight,
                confidence=edge.confidence,
                resolution_type=edge.resolution_type,
                metadata_json=edge.metadata,
            )
        )
    return snapshot


def rebuild_violations(
    session: Session,
    repository_id: UUID,
    snapshots: list[tuple[ArchitectureSnapshot, HistoricalGraph]] | None = None,
) -> int:
    from app.services.architecture_history.service import graph_from_snapshot

    session.execute(delete(ArchitectureViolation).where(ArchitectureViolation.repository_id == repository_id))
    rules = list(
        session.scalars(
            select(ArchitectureRule).where(
                ArchitectureRule.repository_id == repository_id,
                ArchitectureRule.enabled.is_(True),
            )
        )
    )
    if snapshots is None:
        snapshot_models = list(
            session.scalars(
                select(ArchitectureSnapshot)
                .where(ArchitectureSnapshot.repository_id == repository_id)
                .order_by(ArchitectureSnapshot.committed_at, ArchitectureSnapshot.commit_sha)
            )
        )
        snapshots = [(snapshot, graph_from_snapshot(session, snapshot)) for snapshot in snapshot_models]
    active: dict[tuple[UUID, str, str], ArchitectureViolation] = {}
    count = 0
    for snapshot, graph in snapshots:
        present: set[tuple[UUID, str, str]] = set()
        for rule in rules:
            findings = evaluate_rule(
                graph,
                rule.rule_type,
                rule.source_selector,
                rule.target_selector,
                get_settings().architecture_rule_min_edge_confidence,
            )
            for finding in findings:
                key = (rule.id, finding["source_stable_key"], finding["target_stable_key"])
                present.add(key)
                if key not in active:
                    violation = ArchitectureViolation(
                        repository_id=repository_id,
                        rule_id=rule.id,
                        introduced_snapshot_id=snapshot.id,
                        introduced_commit_id=snapshot.commit_id,
                        introduced_commit_sha=snapshot.commit_sha,
                        source_stable_key=key[1],
                        target_stable_key=key[2],
                        confidence=finding["confidence"],
                        evidence=finding["evidence"],
                    )
                    session.add(violation)
                    active[key] = violation
                    count += 1
        for key in set(active) - present:
            violation = active.pop(key)
            violation.status = "resolved"
            violation.resolved_snapshot_id = snapshot.id
            violation.resolved_commit_id = snapshot.commit_id
            violation.resolved_commit_sha = snapshot.commit_sha
    return count


class ArchitectureHistoryIndexer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(self, session: Session, repository: Repository, job: AnalysisJob) -> None:
        if not repository.head_sha or not GitService(self.settings).storage.path(repository.id).exists():
            raise IngestionError("ARCHITECTURE_HISTORY_NOT_READY", "The Git object cache is unavailable.", 409)
        state = session.get(ArchitectureHistoryState, repository.id)
        if state is None:
            state = ArchitectureHistoryState(repository_id=repository.id)
            session.add(state)
        state.status = "indexing"
        state.started_at = datetime.now(UTC)
        state.error = None
        state.job_id = job.id
        started = time.monotonic()
        commits, limited = _select_commits(session, repository.id, self.settings)
        if not commits:
            raise IngestionError("ARCHITECTURE_HISTORY_EMPTY", "No indexed commits are available.", 409)
        existing = list(
            session.scalars(
                select(ArchitectureSnapshot)
                .where(ArchitectureSnapshot.repository_id == repository.id)
                .order_by(ArchitectureSnapshot.committed_at, ArchitectureSnapshot.commit_sha)
            )
        )
        existing_shas = {snapshot.commit_sha for snapshot in existing}
        missing = [commit for commit in commits if commit.sha not in existing_shas]
        if (
            existing
            and not missing
            and state.last_indexed_sha == repository.head_sha
            and not repository.history_rewritten
        ):
            state.status = "limited" if limited else "ready"
            state.current_step = "ready"
            state.progress = None
            state.completed_at = datetime.now(UTC)
            state.job_id = job.id
            return
        incremental = bool(
            existing
            and missing
            and not repository.history_rewritten
            and all(commit.committed_at >= existing[-1].committed_at for commit in missing)
        )
        if incremental:
            commits_to_build = missing
        else:
            # Rebuild derived data atomically. Rules survive; linked rows cascade.
            session.execute(
                delete(ArchitectureSnapshot).where(
                    ArchitectureSnapshot.repository_id == repository.id
                )
            )
            session.flush()
            existing = []
            commits_to_build = commits
        tags_by_sha: dict[str, list[str]] = {}
        for tag in session.scalars(select(Tag).where(Tag.repository_id == repository.id)):
            tags_by_sha.setdefault(tag.target_sha, []).append(tag.name)
        builder = HistoricalArchitectureBuilder(self.settings)
        stored: list[tuple[ArchitectureSnapshot, HistoricalGraph]] = []
        previous: tuple[ArchitectureSnapshot, HistoricalGraph] | None = None
        event_count = int(
            session.scalar(
                select(func.count(ArchitectureEvolutionEvent.id)).where(
                    ArchitectureEvolutionEvent.repository_id == repository.id
                )
            )
            or 0
        )
        if incremental and existing:
            from app.services.architecture_history.service import graph_from_snapshot

            previous = (existing[-1], graph_from_snapshot(session, existing[-1]))
        for index, commit in enumerate(commits_to_build):
            if time.monotonic() - started > self.settings.max_architecture_history_build_seconds:
                raise IngestionError("ARCHITECTURE_HISTORY_LIMIT_REACHED", "Architecture indexing exceeded its time limit.", 413)
            state.current_step = f"snapshotting_{commit.short_sha}"
            state.progress = round((index / len(commits_to_build)) * 85, 2)
            job.current_step = state.current_step
            job.progress = state.progress
            graph = builder.build(repository.id, GitService(self.settings).storage.path(repository.id), commit.sha)
            snapshot = _persist_graph(session, repository, commit, graph, sorted(tags_by_sha.get(commit.sha, [])))
            session.flush()
            stored.append((snapshot, graph))
            if previous:
                comparison = compare_graphs(previous[1], graph)
                comparison_events = events_from_comparison(comparison)
                for change in session.scalars(
                    select(FileChange).where(FileChange.commit_id == commit.id)
                ):
                    if (
                        change.change_type in {"renamed", "moved"}
                        and _architecture_path(change.old_path)
                        and _architecture_path(change.new_path)
                    ):
                        comparison_events.append(
                            {
                                "event_type": "module_moved",
                                "value": {
                                    "source": f"module:{builder.module_path(change.old_path or '')}",
                                    "target": f"module:{builder.module_path(change.new_path or '')}",
                                    "similarity_score": change.similarity_score,
                                },
                            }
                        )
                for position, event in enumerate(comparison_events):
                    value = event["value"]
                    source_key = value.get("source") or value.get("stable_key")
                    target_key = value.get("target")
                    session.add(
                        ArchitectureEvolutionEvent(
                            id=uuid5(snapshot.id, f"event:{position}:{event['event_type']}:{source_key}:{target_key}"),
                            repository_id=repository.id,
                            commit_id=commit.id,
                            commit_sha=commit.sha,
                            committed_at=commit.committed_at,
                            event_type=event["event_type"],
                            source_snapshot_id=previous[0].id,
                            target_snapshot_id=snapshot.id,
                            source_stable_key=source_key,
                            target_stable_key=target_key,
                            old_value=value if event["event_type"].endswith(("removed", "resolved")) else None,
                            new_value=value if not event["event_type"].endswith(("removed", "resolved")) else None,
                            confidence=1.0,
                            metadata_json={"deterministic": True},
                        )
                    )
                    event_count += 1
            previous = (snapshot, graph)
        state.current_step = "evaluating_rules"
        state.progress = 90
        violation_count = rebuild_violations(session, repository.id)
        if not session.scalar(select(ArchitectureBaseline.id).where(ArchitectureBaseline.repository_id == repository.id)):
            first = self._first_snapshot(session, repository.id)
            session.add(
                ArchitectureBaseline(
                    repository_id=repository.id,
                    name="Initial indexed architecture",
                    snapshot_id=first.id,
                    is_default=True,
                    metadata_json={"automatic": True},
                )
            )
        state.status = "limited" if limited else "ready"
        state.progress = None
        state.current_step = "ready"
        state.commits_examined = len(commits)
        state.snapshots_created = len(existing) + len(stored)
        state.events_detected = event_count
        session.flush()
        state.cycles_detected = int(
            session.scalar(
                select(func.coalesce(func.sum(ArchitectureSnapshot.cycle_count), 0)).where(
                    ArchitectureSnapshot.repository_id == repository.id
                )
            )
            or 0
        )
        state.violations_detected = violation_count
        state.last_indexed_sha = repository.head_sha
        state.limited = limited
        state.completed_at = datetime.now(UTC)
        session.execute(
            delete(AIAnswerCache).where(AIAnswerCache.repository_id == repository.id)
        )

    @staticmethod
    def _first_snapshot(session: Session, repository_id: UUID) -> ArchitectureSnapshot:
        snapshot = session.scalar(
            select(ArchitectureSnapshot)
            .where(ArchitectureSnapshot.repository_id == repository_id)
            .order_by(ArchitectureSnapshot.committed_at, ArchitectureSnapshot.commit_sha)
            .limit(1)
        )
        assert snapshot is not None
        return snapshot


def index_architecture_history(engine: Engine, repository_id: UUID, job_id: UUID) -> None:
    lock_key = int.from_bytes(repository_id.bytes[:8], signed=True)
    with engine.connect() as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key})
        connection.commit()
        if not acquired:
            return
        try:
            with Session(engine, expire_on_commit=False) as session:
                job = session.get(AnalysisJob, job_id)
                repository = session.get(Repository, repository_id)
                if not job or not repository or job.repository_id != repository_id:
                    return
                try:
                    job.status = JobStatus.running
                    job.started_at = job.started_at or datetime.now(UTC)
                    ArchitectureHistoryIndexer().run(session, repository, job)
                    job.status = JobStatus.completed
                    job.current_step = "completed"
                    job.progress = None
                    job.completed_at = datetime.now(UTC)
                    session.commit()
                except Exception as error:
                    session.rollback()
                    state = session.get(ArchitectureHistoryState, repository_id)
                    if state is None:
                        state = ArchitectureHistoryState(repository_id=repository_id)
                        session.add(state)
                    message = error.message if isinstance(error, IngestionError) else "Architecture history indexing failed."
                    state.status = "failed"
                    state.error = message
                    state.progress = None
                    state.completed_at = datetime.now(UTC)
                    job.status = JobStatus.failed
                    job.error_message = message
                    job.progress = None
                    job.completed_at = datetime.now(UTC)
                    session.commit()
                    logger.exception("architecture_history_failed", extra={"repository_id": repository_id})
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            connection.commit()
