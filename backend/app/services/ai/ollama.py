import logging
import time
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError

logger = logging.getLogger("ctm")


class AIServiceError(IngestionError):
    pass


class OllamaService:
    def __init__(
        self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self._transport = transport

    @property
    def base_url_safe(self) -> str:
        parsed = urlsplit(self.settings.ollama_base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        timeout = kwargs.pop("timeout", self.settings.ollama_request_timeout_seconds)
        try:
            with httpx.Client(
                base_url=self.settings.ollama_base_url,
                timeout=timeout,
                transport=self._transport,
            ) as client:
                response = client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise AIServiceError("OLLAMA_TIMEOUT", "The local AI request timed out.", 504) from exc
        except httpx.RequestError as exc:
            raise AIServiceError("OLLAMA_UNAVAILABLE", "Ollama is not running.", 503) from exc
        if response.status_code == 404:
            raise AIServiceError(
                "OLLAMA_MODEL_NOT_FOUND", "The configured Ollama model is not installed.", 409
            )
        if response.status_code >= 400:
            detail = ""
            try:
                detail = str(response.json().get("error", ""))
            except (ValueError, AttributeError):
                pass
            if "model" in detail.lower() and (
                "not found" in detail.lower() or "pull" in detail.lower()
            ):
                raise AIServiceError(
                    "OLLAMA_MODEL_NOT_FOUND", "The configured Ollama model is not installed.", 409
                )
            raise AIServiceError(
                "OLLAMA_GENERATION_FAILED", "Ollama could not complete the request.", 502
            )
        return response

    def list_models(self) -> set[str]:
        response = self._request(
            "GET", "/api/tags", timeout=self.settings.ollama_health_timeout_seconds
        )
        try:
            models = response.json().get("models", [])
            return {
                str(item.get("name") or item.get("model"))
                for item in models
                if item.get("name") or item.get("model")
            }
        except (ValueError, AttributeError, TypeError) as exc:
            raise AIServiceError(
                "OLLAMA_INVALID_RESPONSE", "Ollama returned an invalid health response.", 502
            ) from exc

    def is_available(self) -> bool:
        try:
            self.list_models()
            return True
        except AIServiceError:
            return False

    @staticmethod
    def _model_matches(configured: str, installed: set[str]) -> bool:
        if not configured:
            return False
        return configured in installed or f"{configured}:latest" in installed

    def check_model(self, model_name: str) -> bool:
        return self._model_matches(model_name, self.list_models())

    def status(self) -> dict[str, Any]:
        try:
            models = self.list_models()
            available = True
            message = None
        except AIServiceError:
            models = set()
            available = False
            message = "AI features unavailable — Ollama is not running."
        llm = self.settings.ollama_llm_model
        embedding = self.settings.ollama_embedding_model
        if available and (not llm or not embedding):
            message = "Configure both Ollama models to enable AI features."
        return {
            "provider": "ollama",
            "available": available,
            "base_url_safe": self.base_url_safe,
            "llm_model": llm,
            "llm_model_available": self._model_matches(llm, models),
            "embedding_model": embedding,
            "embedding_model_available": self._model_matches(embedding, models),
            "message": message,
        }

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self.settings.ollama_embedding_model
        if not model:
            raise AIServiceError(
                "EMBEDDING_MODEL_NOT_FOUND", "Configure OLLAMA_EMBEDDING_MODEL first.", 409
            )
        started = time.perf_counter()
        try:
            response = self._request(
                "POST", "/api/embed", json={"model": model, "input": list(texts)}
            )
            vectors = response.json().get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(texts):
                raise ValueError("embedding count mismatch")
            result = [[float(value) for value in vector] for vector in vectors]
            dimension = len(result[0]) if result else 0
            if dimension == 0 or any(len(vector) != dimension for vector in result):
                raise ValueError("invalid embedding dimension")
        except AIServiceError as exc:
            if exc.code == "OLLAMA_MODEL_NOT_FOUND":
                raise AIServiceError(
                    "EMBEDDING_MODEL_NOT_FOUND",
                    "The configured embedding model is not installed.",
                    409,
                ) from exc
            if exc.code == "OLLAMA_GENERATION_FAILED":
                raise AIServiceError(
                    "EMBEDDING_FAILED", "Ollama could not generate embeddings.", 502
                ) from exc
            raise
        except (ValueError, TypeError, AttributeError) as exc:
            raise AIServiceError(
                "EMBEDDING_FAILED", "Ollama returned invalid embeddings.", 502
            ) from exc
        logger.info(
            "ai_embedding_completed",
            extra={
                "model": model,
                "documents": len(texts),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "dimension": dimension,
            },
        )
        return result

    def generate(
        self,
        messages: Sequence[dict[str, str]],
        options: dict[str, Any] | None = None,
        format_schema: dict[str, Any] | None = None,
    ) -> str:
        model = self.settings.ollama_llm_model
        if not model:
            raise AIServiceError("OLLAMA_MODEL_NOT_FOUND", "Configure OLLAMA_LLM_MODEL first.", 409)
        started = time.perf_counter()
        generation_options = {"temperature": 0.1, "num_predict": 384}
        if options:
            generation_options.update(options)
        response = self._request(
            "POST",
            "/api/chat",
            json={
                "model": model,
                "messages": list(messages),
                "stream": False,
                "format": format_schema or "json",
                "think": False,
                "options": generation_options,
            },
        )
        try:
            content = response.json()["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty generation")
        except (ValueError, KeyError, TypeError) as exc:
            raise AIServiceError(
                "OLLAMA_GENERATION_FAILED", "Ollama returned an invalid response.", 502
            ) from exc
        logger.info(
            "ai_generation_completed",
            extra={
                "model": model,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "success": True,
            },
        )
        return content
