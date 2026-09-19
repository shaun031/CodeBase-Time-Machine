from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class InvestigationCreate(BaseModel):
    stack_trace: str | None = None
    error_message: str | None = Field(default=None, max_length=4000)
    known_good_commit: str | None = Field(default=None, min_length=40, max_length=40)
    known_bad_commit: str | None = Field(default=None, min_length=40, max_length=40)
    file_path: str | None = Field(default=None, max_length=2000)
    line: int | None = Field(default=None, ge=1)
    lineage_id: UUID | None = None

    @model_validator(mode="after")
    def useful_target(self) -> "InvestigationCreate":
        values = (
            self.stack_trace,
            self.error_message,
            self.file_path,
            self.lineage_id,
            self.known_good_commit,
            self.known_bad_commit,
        )
        if not any(value for value in values):
            raise ValueError("Provide a stack trace, error, file, symbol, or commit range.")
        if bool(self.known_good_commit) != bool(self.known_bad_commit):
            raise ValueError("Known-good and known-bad commits must be provided together.")
        if self.line is not None and not self.file_path:
            raise ValueError("A line number requires a repository file path.")
        return self


class SZZRequest(BaseModel):
    fix_commit_sha: str = Field(min_length=40, max_length=40)
    file_path: str | None = Field(default=None, max_length=2000)
    lineage_id: UUID | None = None


class BisectCreate(BaseModel):
    known_good: str = Field(min_length=40, max_length=40)
    known_bad: str = Field(min_length=40, max_length=40)


class BisectClassification(BaseModel):
    commit_sha: str = Field(min_length=40, max_length=40)
    result: Literal["good", "bad", "unknown"]


class CandidateFeedbackWrite(BaseModel):
    commit_sha: str = Field(min_length=40, max_length=40)
    result: Literal["relevant", "not_relevant", "unknown"]


class InvestigationExplain(BaseModel):
    question: str = Field(
        default="Explain the strongest regression candidates and their evidence.",
        min_length=2,
        max_length=2000,
    )
