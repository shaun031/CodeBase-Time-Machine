from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class StackFrame:
    index: int
    raw_text: str
    language: str | None = None
    file_path: str | None = None
    line: int | None = None
    column: int | None = None
    function_name: str | None = None
    module: str | None = None
    is_repository_frame: bool = False
    resolution_status: str = "unresolved"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

