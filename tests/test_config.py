"""Tests del módulo de configuración por entorno (``app.config``)."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings

ENV_KEYS = (
    "PROJECT_ID",
    "DEMO_SLOT",
    "APP_HOST",
    "APP_PORT",
    "OLLAMA_HOST",
    "LLM_MODEL",
    "MAX_OUTPUT_TOKENS",
    "EMBED_MODEL",
    "DB_DSN",
    "TOP_K",
    "SIMILARITY_THRESHOLD",
    "CHUNK_TOKENS",
    "CHUNK_OVERLAP",
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Aísla los tests del entorno real del proceso."""
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


def test_defaults():
    s = Settings(_env_file=None)
    assert s.app_host == "0.0.0.0"
    assert s.app_port == 8080
    assert s.top_k == 5
    assert s.llm_model == "qwen2.5:1.5b-instruct"
    assert s.embed_model == "paraphrase-multilingual-MiniLM-L12-v2"
    assert s.similarity_threshold == pytest.approx(0.32)


def test_env_override(monkeypatch):
    monkeypatch.setenv("TOP_K", "8")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b-instruct")
    monkeypatch.setenv("SIMILARITY_THRESHOLD", "0.5")
    monkeypatch.setenv("PROJECT_ID", "rag-demo")
    s = Settings(_env_file=None)
    assert s.top_k == 8
    assert isinstance(s.top_k, int)  # coerción str -> int
    assert s.llm_model == "qwen2.5:7b-instruct"
    assert s.similarity_threshold == pytest.approx(0.5)
    assert s.project_id == "rag-demo"


def test_types():
    s = Settings(_env_file=None)
    assert isinstance(s.app_port, int)
    assert isinstance(s.top_k, int)
    assert isinstance(s.similarity_threshold, float)
    assert isinstance(s.chunk_tokens, int)


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
