import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AIAnswerCache,
    AIIndexState,
    AnalysisJob,
    EvidenceDocument,
    EvidenceEmbedding,
    JobStatus,
    Repository,
    RepositoryStatus,
)
from app.services.ai.evidence import EvidenceDocumentBuilder, NormalizedEvidence
from app.services.ai.ollama import OllamaService

logger = logging.getLogger("ctm")
EMBEDDING_VERSION = "evidence-v1"


class EmbeddingIndexService:
    def __init__(
        self,
        settings: Settings | None = None,
        ollama: OllamaService | None = None,
        builder: EvidenceDocumentBuilder | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ollama = ollama or OllamaService(self.settings)
        self.builder = builder or EvidenceDocumentBuilder(self.settings)

    @property
    def version_identifier(self) -> str:
        value = f"{EMBEDDING_VERSION}:{self.settings.ollama_embedding_model}"
        return hashlib.sha256(value.encode()).hexdigest()[:32]

    @staticmethod
    def _update_progress(
        session: Session, state: AIIndexState, job: AnalysisJob, step: str, progress: float
    ) -> None:
        state.current_step = step
        state.progress = progress
        job.current_step = step
        job.progress = progress
        session.commit()

    def _sync_documents(
        self, session: Session, repository_id: UUID, items: list[NormalizedEvidence]
    ) -> list[EvidenceDocument]:
        existing = {
            item.document_key: item
            for item in session.scalars(
                select(EvidenceDocument).where(EvidenceDocument.repository_id == repository_id)
            )
        }
        keys: set[str] = set()
        result: list[EvidenceDocument] = []
        for item in items:
            keys.add(item.document_key)
            row = existing.get(item.document_key)
            if row is None:
                row = EvidenceDocument(repository_id=repository_id, document_key=item.document_key)
                session.add(row)
            row.evidence_type = item.evidence_type
            row.source_table = item.source_table
            row.source_id = item.source_id
            row.title = item.title
            row.content = item.content
            row.metadata_json = item.metadata
            row.commit_sha = item.commit_sha
            row.file_path = item.file_path
            row.symbol_lineage_id = item.symbol_lineage_id
            row.pull_request_number = item.pull_request_number
            row.issue_number = item.issue_number
            row.created_source_at = item.created_source_at
            row.content_hash = item.hash
            result.append(row)
        stale_ids = [item.id for key, item in existing.items() if key not in keys]
        if stale_ids:
            session.execute(delete(EvidenceDocument).where(EvidenceDocument.id.in_(stale_ids)))
        session.flush()
        return result

    def run(self, session: Session, repository: Repository, job: AnalysisJob) -> None:
        if repository.status != RepositoryStatus.ready or not repository.head_sha:
            raise IngestionError(
                "CODE_INDEX_NOT_READY", "Repository indexing must finish before AI indexing.", 409
            )
        model = self.settings.ollama_embedding_model
        if not model:
            raise IngestionError(
                "EMBEDDING_MODEL_NOT_FOUND", "Configure OLLAMA_EMBEDDING_MODEL first.", 409
            )
        if not self.ollama.check_model(model):
            raise IngestionError(
                "EMBEDDING_MODEL_NOT_FOUND", "The configured embedding model is not installed.", 409
            )
        state = session.get(AIIndexState, repository.id)
        if state is None:
            state = AIIndexState(repository_id=repository.id)
            session.add(state)
        state.status = "indexing"
        state.error = None
        state.started_at = datetime.now(UTC)
        state.completed_at = None
        state.job_id = job.id
        self._update_progress(session, state, job, "Collecting evidence", 5)
        normalized = self.builder.build(session, repository)
        self._update_progress(session, state, job, "Building chunks", 20)
        documents = self._sync_documents(session, repository.id, normalized)
        state.documents = len(documents)
        session.execute(delete(AIAnswerCache).where(AIAnswerCache.repository_id == repository.id))
        session.commit()

        version = self.version_identifier
        embeddings = {
            item.evidence_document_id: item
            for item in session.scalars(
                select(EvidenceEmbedding).where(
                    EvidenceEmbedding.repository_id == repository.id,
                    EvidenceEmbedding.embedding_model == model,
                )
            )
        }
        document_hashes = {document.id: document.content_hash for document in documents}
        pending = [
            document
            for document in documents
            if document.id not in embeddings
            or embeddings[document.id].content_hash != document.content_hash
            or embeddings[document.id].embedding_version != version
        ]
        expected_dimensions = {
            item.embedding_dimension
            for item in embeddings.values()
            if item.content_hash == document_hashes.get(item.evidence_document_id, "")
            and item.embedding_version == version
        }
        probe = self.ollama.embed(["CodeChronicle embedding dimension probe"])
        dimension = len(probe[0])
        if expected_dimensions and expected_dimensions != {dimension}:
            session.execute(
                delete(EvidenceEmbedding).where(
                    EvidenceEmbedding.repository_id == repository.id,
                    EvidenceEmbedding.embedding_model == model,
                )
            )
            session.flush()
            embeddings = {}
            pending = documents[:]

        self._update_progress(session, state, job, "Generating embeddings", 30)
        batch_size = self.settings.ai_embedding_batch_size
        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            vectors = self.ollama.embed([f"{item.title}\n{item.content}" for item in batch])
            batch_dimension = len(vectors[0]) if vectors else 0
            if dimension is not None and batch_dimension != dimension:
                raise IngestionError(
                    "EMBEDDING_FAILED", "Embedding model dimension changed during indexing.", 409
                )
            dimension = batch_dimension
            for document, vector in zip(batch, vectors, strict=True):
                row = embeddings.get(document.id)
                if row is None:
                    row = EvidenceEmbedding(
                        repository_id=repository.id,
                        evidence_document_id=document.id,
                        embedding_model=model,
                    )
                    session.add(row)
                row.embedding = vector
                row.embedding_dimension = batch_dimension
                row.embedding_version = version
                row.content_hash = document.content_hash
            state.embedded_documents = len(documents) - len(pending) + start + len(batch)
            progress = 30 + 60 * (start + len(batch)) / max(1, len(pending))
            self._update_progress(session, state, job, "Saving vectors", min(90, progress))

        session.execute(
            delete(EvidenceEmbedding).where(
                EvidenceEmbedding.repository_id == repository.id,
                EvidenceEmbedding.embedding_model != model,
            )
        )
        self._update_progress(session, state, job, "Finalizing retrieval index", 95)
        state.status = "ready"
        state.progress = None
        state.current_step = "ready"
        state.documents = len(documents)
        state.embedded_documents = len(documents)
        state.embedding_model = model
        state.embedding_dimension = dimension
        state.embedding_version = version
        state.last_indexed_sha = repository.head_sha
        state.completed_at = datetime.now(UTC)
        session.commit()


def index_ai_repository(engine: Engine, repository_id: UUID, job_id: UUID) -> None:
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
                try:
                    job.status = JobStatus.running
                    job.started_at = job.started_at or datetime.now(UTC)
                    EmbeddingIndexService().run(session, repository, job)
                    job.status = JobStatus.completed
                    job.current_step = "completed"
                    job.progress = None
                    job.completed_at = datetime.now(UTC)
                    session.commit()
                    logger.info("ai_index_completed", extra={"repository_id": repository_id})
                except Exception as error:
                    session.rollback()
                    state = session.get(AIIndexState, repository_id)
                    if state is None:
                        state = AIIndexState(repository_id=repository_id)
                        session.add(state)
                    message = (
                        error.message
                        if isinstance(error, IngestionError)
                        else "AI indexing failed. Check Ollama and retry."
                    )
                    state.status = "failed"
                    state.progress = None
                    state.current_step = None
                    state.error = message
                    state.completed_at = datetime.now(UTC)
                    job.status = JobStatus.failed
                    job.error_message = message
                    job.progress = None
                    job.completed_at = datetime.now(UTC)
                    session.commit()
                    logger.exception("ai_index_failed", extra={"repository_id": repository_id})
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            lock_connection.commit()
