from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Codebase Time Machine"
    app_env: Literal["development", "test"] = "development"
    debug: bool = False
    database_url: SecretStr = SecretStr("")
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    repository_storage_path: Path = ROOT / "data" / "repositories"
    github_token: SecretStr = SecretStr("")
    llm_provider: Literal["ollama"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = ""
    ollama_embedding_model: str = ""
    ollama_request_timeout_seconds: float = Field(default=180.0, gt=0, le=600)
    ollama_health_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    ai_embedding_batch_size: int = Field(default=16, gt=0, le=128)
    rag_top_k_vector: int = Field(default=12, gt=0, le=50)
    rag_top_k_lexical: int = Field(default=12, gt=0, le=50)
    rag_top_k_final: int = Field(default=12, gt=0, le=50)
    rag_max_context_chars: int = Field(default=4000, gt=1000, le=200000)
    rag_max_evidence_items: int = Field(default=6, gt=0, le=100)
    rag_max_diff_chars: int = Field(default=8000, gt=500, le=50000)
    max_embedding_chunk_chars: int = Field(default=5000, gt=500, le=20000)
    max_diff_embedding_chunks_per_commit: int = Field(default=20, gt=0, le=200)
    ai_max_evidence_documents: int = Field(default=12000, gt=100, le=100000)
    ai_max_diff_commits: int = Field(default=250, ge=0, le=2000)
    ai_max_answer_chars: int = Field(default=12000, gt=500, le=50000)
    ai_debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    max_repository_size_mb: int = Field(default=500, gt=0)
    max_commits: int = Field(default=10000, gt=0)
    max_files: int = Field(default=50000, gt=0)
    max_file_size_bytes: int = Field(default=2000000, gt=0)
    max_source_file_size_bytes: int = Field(default=1000000, gt=0)
    max_repository_files: int = Field(default=50000, gt=0)
    max_parse_time_per_file_seconds: float = Field(default=2.0, gt=0)
    max_diff_size_bytes: int = Field(default=500000, gt=0)
    max_history_commits: int = Field(default=2000, gt=0)
    max_historical_files: int = Field(default=20000, gt=0)
    max_historical_symbol_source_bytes: int = Field(default=100000, gt=0)
    max_history_index_time_seconds: int = Field(default=900, gt=0)
    max_blame_lines: int = Field(default=500, gt=0)
    archaeology_recent_days: int = Field(default=180, gt=0, le=3650)
    symbol_rewrite_similarity_threshold: float = Field(default=0.5, ge=0.1, le=0.9)
    max_archaeology_files: int = Field(default=20000, gt=0)
    max_archaeology_symbols: int = Field(default=50000, gt=0)
    max_copy_candidates_per_symbol: int = Field(default=10, gt=0, le=100)
    max_rewrite_comparisons: int = Field(default=100000, gt=0)
    max_archaeology_search_results: int = Field(default=100, gt=0, le=1000)
    max_archaeology_build_seconds: int = Field(default=900, gt=0)
    architecture_snapshot_strategy: Literal["adaptive", "interval", "all"] = "adaptive"
    architecture_snapshot_interval_commits: int = Field(default=25, gt=0, le=10000)
    max_architecture_snapshots: int = Field(default=500, gt=1, le=10000)
    max_historical_graph_nodes: int = Field(default=5000, gt=1, le=50000)
    max_historical_graph_edges: int = Field(default=20000, gt=1, le=200000)
    max_architecture_history_commits: int = Field(default=2000, gt=0, le=10000)
    max_architecture_history_build_seconds: int = Field(default=900, gt=0, le=7200)
    architecture_rule_min_edge_confidence: float = Field(default=0.8, ge=0, le=1)
    max_stack_trace_chars: int = Field(default=50000, gt=0, le=500000)
    max_stack_frames: int = Field(default=100, gt=0, le=1000)
    max_regression_range_commits: int = Field(default=2000, gt=0, le=10000)
    max_szz_files: int = Field(default=100, gt=0, le=1000)
    max_szz_lines: int = Field(default=1000, gt=0, le=10000)
    max_investigation_candidates: int = Field(default=50, gt=0, le=500)
    max_investigation_build_seconds: int = Field(default=300, gt=0, le=3600)
    max_bisect_range_commits: int = Field(default=5000, gt=1, le=20000)
    max_github_pull_requests: int = Field(default=500, gt=0)
    max_github_issues: int = Field(default=1000, gt=0)
    max_github_comments: int = Field(default=5000, gt=0)
    max_github_review_comments: int = Field(default=5000, gt=0)
    max_github_body_length: int = Field(default=200000, gt=0)
    github_request_timeout_seconds: float = Field(default=15.0, gt=0)
    github_max_retries: int = Field(default=3, ge=0, le=10)
    max_graph_nodes: int = Field(default=50000, gt=0)
    max_graph_edges: int = Field(default=200000, gt=0)
    max_graph_response_nodes: int = Field(default=500, gt=0, le=5000)
    max_graph_depth: int = Field(default=5, gt=0, le=20)
    max_call_resolution_candidates: int = Field(default=20, gt=0, le=1000)
    max_files_per_commit_for_coupling: int = Field(default=100, gt=1)
    max_graph_build_time_seconds: int = Field(default=900, gt=0)
    symbol_match_threshold: float = Field(default=0.86, ge=0, le=1)
    symbol_rename_match_threshold: float = Field(default=0.9, ge=0, le=1)
    clone_timeout_seconds: int = Field(default=300, gt=0)
    fetch_timeout_seconds: int = Field(default=180, gt=0)
    git_command_timeout_seconds: int = Field(default=60, gt=0)
    git_output_limit_bytes: int = Field(default=16777216, gt=0)
    task_execution_mode: Literal["local", "celery"] = "local"

    @field_validator("database_url")
    @classmethod
    def validate_database(cls, value: SecretStr) -> SecretStr:
        url = value.get_secret_value()
        if url and not url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis(cls, value: SecretStr) -> SecretStr:
        if urlsplit(value.get_secret_value()).scheme not in {"redis", "rediss"}:
            raise ValueError("REDIS_URL must use redis:// or rediss://")
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            url = urlsplit(value)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or "*" in value
                or url.path
                or url.query
                or url.fragment
                or url.username
                or url.password
            ):
                raise ValueError("CORS origins must be explicit HTTP(S) origins without paths")
        return values

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_url(cls, value: str) -> str:
        url = urlsplit(value.rstrip("/"))
        allowed_hosts = {"localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama"}
        if (
            url.scheme != "http"
            or url.hostname not in allowed_hosts
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
            or url.username
            or url.password
        ):
            raise ValueError("OLLAMA_BASE_URL must be a credential-free local HTTP origin")
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
