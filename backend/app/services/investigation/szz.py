import re
from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.ingestion_errors import IngestionError
from app.db.models import Commit, Repository, SymbolLineage
from app.services.git import GitService


class SZZAnalysisService:
    HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")
    EXCLUDED_PARTS = {"node_modules", "vendor", "dist", "build", ".min.js", "package-lock.json"}

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.git = GitService(settings)

    @staticmethod
    def _candidate_lines(diff: str) -> list[int]:
        lines: list[int] = []
        old_line = 0
        hunk_start = 0
        hunk_count = 0
        deleted_in_hunk = False
        for row in diff.splitlines():
            match = SZZAnalysisService.HUNK.match(row)
            if match:
                if hunk_start and not deleted_in_hunk:
                    lines.extend(range(max(1, hunk_start - 1), max(1, hunk_start) + 2))
                hunk_start = int(match.group(1))
                hunk_count = int(match.group(2) or "1")
                old_line = hunk_start
                deleted_in_hunk = False
            elif row.startswith("-") and not row.startswith("---"):
                content = row[1:].strip()
                if content and not content.startswith(("#", "//", "/*", "*")):
                    lines.append(old_line)
                    deleted_in_hunk = True
                old_line += 1
            elif row.startswith("+") and not row.startswith("+++"):
                continue
            elif hunk_start:
                old_line += 1
        if hunk_start and not deleted_in_hunk:
            end = max(1, hunk_start + max(hunk_count, 1))
            lines.extend(range(max(1, hunk_start - 1), end + 2))
        return sorted(set(lines))

    def analyze(
        self,
        repository_id: UUID,
        fix_commit_sha: str,
        file_path: str | None = None,
        lineage_id: UUID | None = None,
    ) -> dict[str, Any]:
        repository = self.session.get(Repository, repository_id)
        if repository is None or not repository.local_path:
            raise IngestionError("REPOSITORY_NOT_FOUND", "Repository is not available.", 404)
        if lineage_id and not file_path:
            lineage = self.session.scalar(
                select(SymbolLineage).where(
                    SymbolLineage.id == lineage_id,
                    SymbolLineage.repository_id == repository_id,
                )
            )
            if lineage is None or not lineage.current_file_path:
                raise IngestionError("LINEAGE_NOT_FOUND", "Symbol lineage was not found.", 404)
            file_path = lineage.current_file_path
        fix_sha = self.git.validate_sha(fix_commit_sha)
        fix = self.session.scalar(
            select(Commit).where(Commit.repository_id == repository_id, Commit.sha == fix_sha)
        )
        if fix is None:
            raise IngestionError(
                "INVESTIGATION_COMMIT_NOT_INDEXED", "Fix commit is not indexed.", 404
            )
        path = self.git.storage.path(repository_id)
        git_commit = self.git.get_commit(path, fix_sha)
        if not git_commit.parents:
            return {
                "fix_commit_sha": fix_sha,
                "candidates": [],
                "excluded": [{"reason": "root_commit_has_no_parent"}],
                "limitations": ["SZZ requires a parent revision."],
            }
        parent = git_commit.parents[0]
        excluded: list[dict[str, Any]] = []
        if len(git_commit.parents) > 1:
            excluded.append({"commit_sha": fix_sha, "reason": "merge_commit_first_parent_analysis"})
        changes = self.git.get_changed_files(path, git_commit)
        if file_path:
            safe = self.git.validate_path(file_path)
            changes = [item for item in changes if item.old_path == safe or item.new_path == safe]
        evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
        files_used = 0
        lines_used = 0
        for change in changes[: self.settings.max_szz_files]:
            old_path = change.old_path
            display_path = change.new_path or old_path
            if not old_path or not display_path:
                excluded.append({"path": display_path, "reason": "added_file_has_no_parent_lines"})
                continue
            lowered = display_path.lower()
            if any(part in lowered for part in self.EXCLUDED_PARTS):
                excluded.append({"path": display_path, "reason": "generated_or_vendor_path"})
                continue
            diff, truncated = self.git.get_zero_context_file_diff(
                path, parent, fix_sha, display_path
            )
            line_numbers = self._candidate_lines(diff)
            if not line_numbers:
                excluded.append(
                    {"path": display_path, "reason": "whitespace_or_comment_only_change"}
                )
                continue
            if truncated:
                excluded.append({"path": display_path, "reason": "diff_truncated"})
            line_numbers = line_numbers[: max(0, self.settings.max_szz_lines - lines_used)]
            if not line_numbers:
                break
            files_used += 1
            lines_used += len(line_numbers)
            for line_number in line_numbers:
                try:
                    blamed = self.git.get_blame(path, parent, old_path, line_number, line_number)
                except IngestionError:
                    continue
                for blame_line in blamed:
                    if not blame_line.source.strip() or blame_line.source.strip().startswith(
                        ("#", "//", "/*", "*")
                    ):
                        continue
                    evidence[blame_line.commit_sha].append(
                        {
                            "path": old_path,
                            "line": blame_line.line,
                            "original_path": blame_line.original_path,
                            "original_line": blame_line.original_line,
                            "source": blame_line.source[:500],
                            "reason": "blamed_changed_line",
                        }
                    )
            if lines_used >= self.settings.max_szz_lines:
                excluded.append({"reason": "szz_line_limit_reached"})
                break
        models = {
            item.sha: item
            for item in self.session.scalars(
                select(Commit).where(
                    Commit.repository_id == repository_id,
                    Commit.sha.in_(list(evidence)),
                )
            )
        }
        maximum = max((len(items) for items in evidence.values()), default=1)
        candidates: list[dict[str, Any]] = []
        for sha, items in evidence.items():
            model = models.get(sha)
            mechanical = bool(model and (model.files_changed > 100 or model.is_merge_commit))
            score = min(1.0, 0.75 + 0.25 * len(items) / maximum)
            if mechanical:
                score = round(score * 0.55, 4)
                excluded.append({"commit_sha": sha, "reason": "large_or_merge_commit_down_ranked"})
            candidates.append(
                {
                    "commit_sha": sha,
                    "commit_id": str(model.id) if model else None,
                    "score": round(score, 4),
                    "confidence": "strong candidate" if score >= 0.8 else "moderate candidate",
                    "reasons": ["blamed_changed_line", "fix_commit_history"],
                    "signals": {
                        "blame": 1.0,
                        "fix_commit_history": 1.0,
                        "mechanical_penalty": 0.45 if mechanical else 0.0,
                    },
                    "evidence": items,
                    "files": sorted({item["path"] for item in items}),
                    "symbols": [],
                    "pr_numbers": [],
                    "issue_numbers": [],
                    "message": model.message if model else None,
                }
            )
        candidates.sort(
            key=lambda candidate: (
                -float(candidate["score"]),
                str(candidate["commit_sha"]),
            )
        )
        for rank, candidate in enumerate(
            candidates[: self.settings.max_investigation_candidates], 1
        ):
            candidate["rank"] = rank
        return {
            "fix_commit_sha": fix_sha,
            "parent_commit_sha": parent,
            "candidates": candidates[: self.settings.max_investigation_candidates],
            "excluded": excluded,
            "files_examined": files_used,
            "lines_examined": lines_used,
            "score_definition": (
                "Investigation priority derived from blamed parent lines; "
                "it is not a probability of causation."
            ),
            "limitations": [
                "SZZ produces candidates, not confirmed bug-introducing commits.",
                "First-parent analysis is used for merge commits.",
                "Formatting, refactors, and squashed history can reduce blame accuracy.",
            ],
        }
