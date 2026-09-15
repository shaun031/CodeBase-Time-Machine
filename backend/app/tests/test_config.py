from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import ROOT, Settings


def test_load_environment(monkeypatch):
    monkeypatch.setenv("MAX_COMMITS", "123")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-test-token")
    settings = Settings(_env_file=None)
    assert settings.max_commits == 123
    assert settings.debug is False
    assert "secret-test-token" not in repr(settings)


def test_env_file_location():
    assert (Path(__file__).resolve().parents[2] / "pyproject.toml").exists()
    assert Settings.model_config["env_file"] == ROOT / ".env"


def test_dotenv(tmp_path):
    env = tmp_path / ".env"
    env.write_text("MAX_FILES=456\nOLLAMA_LLM_MODEL=\n", encoding="utf-8")
    assert Settings(_env_file=env).max_files == 456


@pytest.mark.parametrize(
    "values",
    [
        {"max_commits": 0},
        {"max_files": -1},
        {"database_url": "sqlite:///wrong.db"},
        {"cors_origins": ["*"]},
        {"cors_origins": ["http://localhost:3000/path"]},
        {"redis_url": "http://localhost"},
    ],
)
def test_invalid_settings(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_no_ollama_required():
    settings = Settings(_env_file=None, ollama_llm_model="", ollama_embedding_model="")
    assert settings.ollama_llm_model == ""
