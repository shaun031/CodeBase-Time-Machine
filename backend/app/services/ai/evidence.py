import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import (
    ArchitectureComponent,
    CodeSymbol,
    Commit,
    DependencyNode,
    FileChange,
    GitHubComment,
    GitHubIssue,
    GitHubPullRequest,
    Repository,
    RepositoryFile,
    SymbolChangeEvent,
    SymbolVersion,
)
from app.services.git import GitService

SECRET_NAMES = {
    "credentials.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore")
SECRET_VALUE = re.compile(
    r"(?i)((?:password|passwd|token|secret|api[_-]?key)\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|\S+)"
)
TOKEN_VALUE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b")
PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
    re.DOTALL,
)
ABSOLUTE_PATH = re.compile(r"(?i)(?:[A-Z]:\\|/(?:home|users)/)[^\s\"']+")


def is_sensitive_path(path: str | None) -> bool:
    if not path:
        return False
    name = PurePosixPath(path.replace("\\", "/")).name.lower()
    return (
        name == ".env"
        or name.startswith(".env.")
        or name == "secrets"
        or name.startswith("secrets.")
        or name in SECRET_NAMES
        or name.endswith(SECRET_SUFFIXES)
    )


def normalize_text(value: str | None, limit: int = 20000) -> str:
    text = (value or "").replace("\x00", "").replace("\r\n", "\n").strip()
    text = PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    text = SECRET_VALUE.sub(r"\1[REDACTED]", text)
    text = TOKEN_VALUE.sub("[REDACTED TOKEN]", text)
    text = ABSOLUTE_PATH.sub("[REDACTED LOCAL PATH]", text)
    return text[:limit]


def content_hash(title: str, content: str, metadata: dict[str, Any] | None = None) -> str:
    canonical = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{title}\n{content}\n{canonical}".encode()).hexdigest()


def chunk_text(text: str, max_characters: int) -> list[str]:
    value = normalize_text(text, max_characters * 100)
    if not value:
        return []
    paragraphs = re.split(r"\n(?=(?:diff --git|@@|\s*$))", value)
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_characters:
            lines = paragraph.splitlines(keepends=True)
            for line in lines:
                if current and len(current) + len(line) > max_characters:
                    chunks.append(current.strip())
                    current = ""
                if len(line) > max_characters:
                    if current:
                        chunks.append(current.strip())
                        current = ""
                    chunks.extend(
                        line[index : index + max_characters].strip()
                        for index in range(0, len(line), max_characters)
                    )
                else:
                    current += line
        elif current and len(current) + len(paragraph) + 1 > max_characters:
            chunks.append(current.strip())
            current = paragraph
        else:
            current = f"{current}\n{paragraph}" if current else paragraph
    if current.strip():
        chunks.append(current.strip())
    return [item for item in chunks if item]


@dataclass(frozen=True)
class NormalizedEvidence:
    document_key: str
    evidence_type: str
    source_table: str
    source_id: UUID | None
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    commit_sha: str | None = None
    file_path: str | None = None
    symbol_lineage_id: UUID | None = None
    pull_request_number: int | None = None
    issue_number: int | None = None
    created_source_at: datetime | None = None

    @property
    def hash(self) -> str:
        return content_hash(self.title, self.content, self.metadata)


class EvidenceDocumentBuilder:
    def __init__(self, settings: Settings | None = None, git: GitService | None = None) -> None:
        self.settings = settings or get_settings()
        self.git = git or GitService(self.settings)

    def build(self, session: Session, repository: Repository) -> list[NormalizedEvidence]:
        documents: list[NormalizedEvidence] = []

        def add(item: NormalizedEvidence) -> None:
            if item.content.strip():
                documents.append(item)

        changes: dict[UUID, list[FileChange]] = {}
        for change in session.scalars(
            select(FileChange)
            .where(FileChange.repository_id == repository.id)
            .order_by(FileChange.commit_id, FileChange.change_order)
        ):
            changes.setdefault(change.commit_id, []).append(change)
        commits = list(
            session.scalars(
                select(Commit)
                .where(Commit.repository_id == repository.id)
                .order_by(Commit.committed_at.desc(), Commit.id)
            )
        )
        commit_by_id = {commit.id: commit for commit in commits}
        for commit in commits:
            paths = [
                f"{item.change_type}: {item.new_path or item.old_path} (+{item.additions or 0}/-{item.deletions or 0})"
                for item in changes.get(commit.id, [])
                if not is_sensitive_path(item.new_path or item.old_path)
            ]
            body = (
                f"Commit {commit.sha}\nAuthor: {commit.author_name}\nDate: {commit.committed_at.isoformat()}\n"
                f"Message:\n{normalize_text(commit.message, 10000)}\n"
                f"Changes ({len(paths)}):\n" + "\n".join(paths[:100])
            )
            add(
                NormalizedEvidence(
                    f"commit:{commit.id}",
                    "commit",
                    "commits",
                    commit.id,
                    f"Commit {commit.short_sha}: {commit.message.splitlines()[0] if commit.message else '(no message)'}",
                    body,
                    {"author": commit.author_name, "files_changed": commit.files_changed},
                    commit_sha=commit.sha,
                    created_source_at=commit.committed_at,
                )
            )

        files = {
            item.id: item
            for item in session.scalars(
                select(RepositoryFile).where(RepositoryFile.repository_id == repository.id)
            )
        }
        for symbol in session.scalars(
            select(CodeSymbol)
            .where(CodeSymbol.repository_id == repository.id)
            .order_by(CodeSymbol.file_id, CodeSymbol.start_line)
        ):
            file = files.get(symbol.file_id)
            if file is None or is_sensitive_path(file.path):
                continue
            text = (
                f"Current {symbol.kind}: {symbol.qualified_name}\nFile: {file.path}\n"
                f"Lines: {symbol.start_line}-{symbol.end_line}\n"
                f"Signature: {normalize_text(symbol.signature, 3000)}\n"
                f"Documentation: {normalize_text(symbol.documentation, 5000)}"
            )
            add(
                NormalizedEvidence(
                    f"symbol-current:{symbol.id}",
                    "symbol_current",
                    "code_symbols",
                    symbol.id,
                    f"Current symbol {symbol.qualified_name}",
                    text,
                    {
                        "kind": symbol.kind,
                        "start_line": symbol.start_line,
                        "end_line": symbol.end_line,
                    },
                    commit_sha=file.indexed_commit_sha,
                    file_path=file.path,
                    symbol_lineage_id=symbol.lineage_id,
                )
            )

        versions = list(
            session.scalars(
                select(SymbolVersion)
                .where(SymbolVersion.repository_id == repository.id)
                .order_by(SymbolVersion.created_at.desc(), SymbolVersion.id)
            )
        )
        for version in versions:
            if is_sensitive_path(version.file_path):
                continue
            version_commit = commit_by_id.get(version.commit_id)
            header = (
                f"Historical {version.kind}: {version.qualified_name}\nFile: {version.file_path}\n"
                f"Lines: {version.start_line}-{version.end_line}\nSignature: {normalize_text(version.signature, 3000)}"
            )
            pieces = chunk_text(version.source_text or "", self.settings.max_embedding_chunk_chars)
            for index, piece in enumerate(pieces or [""]):
                add(
                    NormalizedEvidence(
                        f"symbol-version:{version.id}:{index}",
                        "symbol_version",
                        "symbol_versions",
                        version.id,
                        f"{version.qualified_name} at {(version_commit.short_sha if version_commit else 'unknown commit')} ({index + 1}/{max(1, len(pieces))})",
                        f"{header}\nSource:\n{piece}",
                        {"kind": version.kind, "match_type": version.match_type, "chunk": index},
                        commit_sha=version_commit.sha if version_commit else None,
                        file_path=version.file_path,
                        symbol_lineage_id=version.lineage_id,
                        created_source_at=version_commit.committed_at if version_commit else None,
                    )
                )

        events = list(
            session.scalars(
                select(SymbolChangeEvent)
                .where(SymbolChangeEvent.repository_id == repository.id)
                .order_by(SymbolChangeEvent.created_at.desc(), SymbolChangeEvent.id)
            )
        )
        for event in events:
            event_commit = commit_by_id.get(event.commit_id)
            summary = json.dumps(event.summary_data or {}, sort_keys=True, default=str)
            add(
                NormalizedEvidence(
                    f"symbol-change:{event.id}",
                    "symbol_change",
                    "symbol_change_events",
                    event.id,
                    f"Symbol {event.event_type} at {(event_commit.short_sha if event_commit else 'unknown commit')}",
                    f"Event: {event.event_type}\nCommit: {event_commit.sha if event_commit else 'unknown'}\nDetails: {summary}\nCommit message: {normalize_text(event_commit.message if event_commit else '', 6000)}",
                    {"event_type": event.event_type},
                    commit_sha=event_commit.sha if event_commit else None,
                    symbol_lineage_id=event.lineage_id,
                    created_source_at=event_commit.committed_at if event_commit else None,
                )
            )

        for pull in session.scalars(
            select(GitHubPullRequest)
            .where(GitHubPullRequest.repository_id == repository.id)
            .order_by(GitHubPullRequest.created_at.desc(), GitHubPullRequest.id)
        ):
            header = (
                f"Pull request #{pull.number}: {pull.title}\nState: {pull.state}\n"
                f"Author: {pull.author_login or 'unknown'}\nDescription:\n"
            )
            pieces = chunk_text(
                normalize_text(pull.body, self.settings.max_github_body_length),
                max(500, self.settings.max_embedding_chunk_chars - len(header)),
            ) or ["No description was provided."]
            for index, piece in enumerate(pieces):
                add(
                    NormalizedEvidence(
                        f"pull-request:{pull.id}:{index}",
                        "pull_request",
                        "github_pull_requests",
                        pull.id,
                        f"PR #{pull.number}: {pull.title} ({index + 1}/{len(pieces)})",
                        f"{header}{piece}",
                        {
                            "state": pull.state,
                            "merged": pull.merged,
                            "html_url": pull.html_url,
                            "chunk": index,
                        },
                        commit_sha=pull.merge_commit_sha,
                        pull_request_number=pull.number,
                        created_source_at=pull.created_at,
                    )
                )
        for issue in session.scalars(
            select(GitHubIssue)
            .where(GitHubIssue.repository_id == repository.id)
            .order_by(GitHubIssue.created_at.desc(), GitHubIssue.id)
        ):
            header = (
                f"Issue #{issue.number}: {issue.title}\nState: {issue.state}\n"
                f"Author: {issue.author_login or 'unknown'}\nDescription:\n"
            )
            pieces = chunk_text(
                normalize_text(issue.body, self.settings.max_github_body_length),
                max(500, self.settings.max_embedding_chunk_chars - len(header)),
            ) or ["No description was provided."]
            for index, piece in enumerate(pieces):
                add(
                    NormalizedEvidence(
                        f"issue:{issue.id}:{index}",
                        "issue",
                        "github_issues",
                        issue.id,
                        f"Issue #{issue.number}: {issue.title} ({index + 1}/{len(pieces)})",
                        f"{header}{piece}",
                        {"state": issue.state, "html_url": issue.html_url, "chunk": index},
                        issue_number=issue.number,
                        created_source_at=issue.created_at,
                    )
                )
        pulls_by_id = {
            item.id: item
            for item in session.scalars(
                select(GitHubPullRequest).where(GitHubPullRequest.repository_id == repository.id)
            )
        }
        issues_by_id = {
            item.id: item
            for item in session.scalars(
                select(GitHubIssue).where(GitHubIssue.repository_id == repository.id)
            )
        }
        for comment in session.scalars(
            select(GitHubComment)
            .where(GitHubComment.repository_id == repository.id)
            .order_by(GitHubComment.created_at.desc(), GitHubComment.id)
        ):
            if is_sensitive_path(comment.path):
                continue
            comment_pull = (
                pulls_by_id.get(comment.pull_request_id) if comment.pull_request_id else None
            )
            comment_issue = issues_by_id.get(comment.issue_id) if comment.issue_id else None
            kind = (
                "review_comment"
                if comment.comment_type == "review_comment"
                else ("pr_comment" if comment_pull else "issue_comment")
            )
            header = f"Untrusted GitHub comment data by {comment.author_login or 'unknown'}:\n"
            comment_text = normalize_text(comment.body, self.settings.max_github_body_length)
            diff_hunk = normalize_text(comment.diff_hunk, 5000)
            if diff_hunk:
                comment_text += f"\nDiff hunk:\n{diff_hunk}"
            pieces = chunk_text(
                comment_text,
                max(500, self.settings.max_embedding_chunk_chars - len(header)),
            ) or ["Empty comment."]
            for index, piece in enumerate(pieces):
                add(
                    NormalizedEvidence(
                        f"comment:{comment.id}:{index}",
                        kind,
                        "github_comments",
                        comment.id,
                        f"{kind.replace('_', ' ').title()} by {comment.author_login or 'unknown'} "
                        f"({index + 1}/{len(pieces)})",
                        f"{header}{piece}",
                        {
                            "comment_type": comment.comment_type,
                            "html_url": comment.html_url,
                            "chunk": index,
                        },
                        commit_sha=comment.commit_sha,
                        file_path=comment.path,
                        pull_request_number=comment_pull.number if comment_pull else None,
                        issue_number=comment_issue.number if comment_issue else None,
                        created_source_at=comment.created_at,
                    )
                )

        for component in session.scalars(
            select(ArchitectureComponent).where(
                ArchitectureComponent.repository_id == repository.id
            )
        ):
            add(
                NormalizedEvidence(
                    f"architecture:{component.id}",
                    "architecture_component",
                    "architecture_components",
                    component.id,
                    f"Architecture component {component.name}",
                    f"Component: {component.name}\nPath: {component.path}\nLayer: {component.layer or 'unknown'}\nMetadata: {json.dumps(component.metadata_json or {}, sort_keys=True, default=str)}",
                    {"layer": component.layer, "confidence": component.confidence},
                    file_path=component.path,
                )
            )
        for node in session.scalars(
            select(DependencyNode)
            .where(DependencyNode.repository_id == repository.id)
            .order_by(DependencyNode.node_type, DependencyNode.qualified_name)
        ):
            if node.node_type == "external" or is_sensitive_path(node.qualified_name):
                continue
            add(
                NormalizedEvidence(
                    f"dependency:{node.id}",
                    "dependency_context",
                    "dependency_nodes",
                    node.id,
                    f"Dependency context for {node.qualified_name}",
                    f"Node type: {node.node_type}\nName: {node.qualified_name}\nMetrics: {json.dumps(node.metrics_json or {}, sort_keys=True, default=str)}",
                    {
                        "node_type": node.node_type,
                        "symbol_id": str(node.symbol_id) if node.symbol_id else None,
                    },
                )
            )

        if repository.local_path and self.git.storage.path(repository.id).exists():
            diff_commit_ids = []
            for event in events:
                if event.commit_id not in diff_commit_ids:
                    diff_commit_ids.append(event.commit_id)
                if len(diff_commit_ids) >= self.settings.ai_max_diff_commits:
                    break
            for commit_id in diff_commit_ids:
                diff_commit = commit_by_id.get(commit_id)
                if not diff_commit:
                    continue
                try:
                    diff, truncated = self.git.get_commit_diff(
                        self.git.storage.path(repository.id), diff_commit.sha
                    )
                except Exception:
                    continue
                pieces = chunk_text(diff, self.settings.max_embedding_chunk_chars)[
                    : self.settings.max_diff_embedding_chunks_per_commit
                ]
                for index, piece in enumerate(pieces):
                    header_paths = re.findall(r"^diff --git a/(.+?) b/(.+?)$", piece, re.MULTILINE)
                    if any(
                        is_sensitive_path(old) or is_sensitive_path(new)
                        for old, new in header_paths
                    ):
                        continue
                    add(
                        NormalizedEvidence(
                            f"commit-diff:{diff_commit.id}:{index}",
                            "commit_diff",
                            "commits",
                            diff_commit.id,
                            f"Diff for {diff_commit.short_sha} ({index + 1})",
                            piece,
                            {"chunk": index, "truncated": truncated},
                            commit_sha=diff_commit.sha,
                            file_path=header_paths[0][1] if len(header_paths) == 1 else None,
                            created_source_at=diff_commit.committed_at,
                        )
                    )
        priority = {
            "symbol_change": 0,
            "commit_diff": 1,
            "pull_request": 2,
            "issue": 3,
            "review_comment": 4,
            "pr_comment": 4,
            "issue_comment": 4,
            "commit": 5,
            "symbol_current": 6,
            "symbol_version": 7,
            "architecture_component": 8,
            "dependency_context": 9,
        }
        documents.sort(key=lambda item: priority.get(item.evidence_type, 10))
        return documents[: self.settings.ai_max_evidence_documents]
