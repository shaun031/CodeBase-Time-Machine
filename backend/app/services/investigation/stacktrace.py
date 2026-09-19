import re
from typing import Any

from app.core.ingestion_errors import IngestionError
from app.services.investigation.models import StackFrame


class StackTraceParser:
    PYTHON = re.compile(
        r'^\s*File\s+["\'](?P<path>.+?)["\'],\s+line\s+(?P<line>\d+)'
        r"(?:,\s+in\s+(?P<function>.+))?\s*$"
    )
    JAVASCRIPT = re.compile(
        r"^\s*at\s+(?:(?P<function>.+?)\s+\()?"
        r"((?P<path>[^()]+?):(?P<line>\d+)(?::(?P<column>\d+))?)\)?\s*$"
    )
    JAVA = re.compile(
        r"^\s*at\s+(?P<module>[\w.$]+)\.(?P<function>[\w$<>]+)"
        r"\((?P<path>[^():]+\.java):(?P<line>\d+)\)\s*$"
    )
    NATIVE = re.compile(
        r"^\s*(?:(?P<function>[^\s(]+).*?\s+)?"
        r"(?P<path>[^\s:()]+\.(?:c|cc|cpp|cxx|h|hpp|go)):"
        r"(?P<line>\d+)(?::(?P<column>\d+))?\s*$",
        re.IGNORECASE,
    )
    EXCEPTION = re.compile(
        r"^(?P<type>[A-Za-z_$][\w.$]*(?:Error|Exception|Panic|Fault)?):\s*"
        r"(?P<message>.+)$"
    )

    def __init__(self, max_chars: int, max_frames: int) -> None:
        self.max_chars = max_chars
        self.max_frames = max_frames

    def parse(self, value: str) -> dict[str, Any]:
        if len(value) > self.max_chars:
            raise IngestionError(
                "STACK_TRACE_LIMIT_REACHED",
                "The stack trace exceeds the configured character limit.",
                413,
            )
        frames: list[StackFrame] = []
        exception_type: str | None = None
        error_message: str | None = None
        for raw_line in value.splitlines():
            line = raw_line.rstrip()
            exception = self.EXCEPTION.match(line.strip())
            if exception and not exception_type:
                exception_type = exception.group("type")
                error_message = exception.group("message")
            parsed: StackFrame | None = None
            python = self.PYTHON.match(line)
            java = self.JAVA.match(line)
            javascript = self.JAVASCRIPT.match(line) if not java else None
            native = self.NATIVE.match(line) if not (python or java or javascript) else None
            match = python or java or javascript or native
            if match:
                groups = match.groupdict()
                if python:
                    language = "python"
                elif java:
                    language = "java"
                elif javascript:
                    language = "javascript"
                elif str(groups.get("path", "")).lower().endswith(".go"):
                    language = "go"
                else:
                    language = "c_cpp"
                parsed = StackFrame(
                    index=len(frames),
                    raw_text=line,
                    language=language,
                    file_path=groups.get("path"),
                    line=int(groups["line"]) if groups.get("line") else None,
                    column=int(groups["column"]) if groups.get("column") else None,
                    function_name=(groups.get("function") or "").strip() or None,
                    module=groups.get("module"),
                )
            if parsed:
                frames.append(parsed)
                if len(frames) >= self.max_frames:
                    break
        nonempty = [line.strip() for line in value.splitlines() if line.strip()]
        if not error_message and nonempty:
            candidate = next(
                (line for line in nonempty if not line.startswith(("at ", "File ", "Traceback"))),
                nonempty[0],
            )
            error_message = candidate[:4000]
        quoted = sorted(set(re.findall(r"['\"]([^'\"]{2,120})['\"]", value)))[:20]
        tokens = sorted(
            {
                token.lower()
                for token in re.findall(r"[A-Za-z_$][A-Za-z0-9_.$-]{2,100}", error_message or "")
                if token.lower()
                not in {"error", "exception", "traceback", "undefined", "null", "none"}
            }
        )[:30]
        return {
            "exception_type": exception_type,
            "error_message": error_message,
            "error_tokens": tokens,
            "quoted_identifiers": quoted,
            "frames": [frame.as_dict() for frame in frames],
            "truncated": len(frames) >= self.max_frames,
        }
