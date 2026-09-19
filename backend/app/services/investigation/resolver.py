from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CodeSymbol, RepositoryFile


class StackFrameResolver:
    EXTERNAL_MARKERS = ("node_modules/", "site-packages/", "python/lib/", "jdk/", "<anonymous>")

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = value.strip().strip('"\'').replace("\\", "/")
        for prefix in ("file://", "webpack://", "webpack-internal://"):
            normalized = normalized.removeprefix(prefix)
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized

    def resolve(self, repository_id: UUID, frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
        files = list(
            self.session.scalars(
                select(RepositoryFile)
                .where(RepositoryFile.repository_id == repository_id)
                .order_by(RepositoryFile.path)
            )
        )
        by_path = {item.path.replace("\\", "/"): item for item in files}
        by_filename: dict[str, list[RepositoryFile]] = {}
        for item in files:
            by_filename.setdefault(item.filename.lower(), []).append(item)
        result: list[dict[str, Any]] = []
        for frame in frames:
            resolved = dict(frame)
            raw_path = str(frame.get("file_path") or "")
            normalized = self._normalize(raw_path)
            lower = normalized.lower()
            if any(marker in lower for marker in self.EXTERNAL_MARKERS):
                resolved.update({"resolution_status": "external", "is_repository_frame": False})
                result.append(resolved)
                continue
            candidates: list[RepositoryFile] = []
            status = "unresolved"
            if normalized in by_path:
                candidates = [by_path[normalized]]
                status = "exact"
            else:
                suffix = [
                    item
                    for path, item in by_path.items()
                    if lower.endswith("/" + path.lower())
                ]
                if len(suffix) == 1:
                    candidates, status = suffix, "path_match"
                elif len(suffix) > 1:
                    candidates, status = suffix, "ambiguous"
                else:
                    filename = PurePosixPath(normalized).name.lower()
                    matches = by_filename.get(filename, [])
                    if len(matches) == 1:
                        candidates, status = matches, "path_match"
                    elif len(matches) > 1:
                        candidates, status = matches, "ambiguous"
            resolved["resolution_status"] = status
            resolved["is_repository_frame"] = len(candidates) == 1
            resolved["candidate_paths"] = [item.path for item in candidates[:20]]
            if len(candidates) == 1:
                file = candidates[0]
                resolved.update({"file_id": str(file.id), "resolved_path": file.path})
                symbols = []
                line_number = frame.get("line")
                if isinstance(line_number, int):
                    symbols = list(
                        self.session.scalars(
                            select(CodeSymbol)
                            .where(
                                CodeSymbol.repository_id == repository_id,
                                CodeSymbol.file_id == file.id,
                                CodeSymbol.start_line <= line_number,
                                CodeSymbol.end_line >= line_number,
                            )
                            .order_by(
                                CodeSymbol.end_line - CodeSymbol.start_line,
                                CodeSymbol.start_line,
                            )
                        )
                    )
                function = str(frame.get("function_name") or "").split(".")[-1]
                symbol = next((item for item in symbols if item.name == function), None)
                symbol = symbol or (symbols[0] if symbols else None)
                if symbol:
                    confidence = 1.0 if symbol.name == function and function else 0.9
                    resolved["symbol"] = {
                        "id": str(symbol.id),
                        "lineage_id": str(symbol.lineage_id) if symbol.lineage_id else None,
                        "name": symbol.name,
                        "qualified_name": symbol.qualified_name,
                        "kind": symbol.kind,
                        "start_line": symbol.start_line,
                        "end_line": symbol.end_line,
                        "confidence": confidence,
                    }
                    resolved["resolution_status"] = "symbol_match" if status != "exact" else "exact"
            result.append(resolved)
        return result
