from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["codebase-time-machine"] = "codebase-time-machine"


class SystemStatus(BaseModel):
    backend: Literal["ok"] = "ok"
    database: Literal["ok", "unavailable"]
    redis: Literal["ok", "unavailable", "not_required"]
    ollama: Literal["ok", "unavailable"]
