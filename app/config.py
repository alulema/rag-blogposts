"""Configuración por variables de entorno (estilo 12-factor).

Fuente única de verdad para los parámetros del demo RAG. **Sin secretos**: todos los valores
tienen defaults seguros y el runtime efímero los sobreescribe por env. Los nombres de env son
los del atributo en MAYÚSCULAS (pydantic-settings hace el mapeo case-insensitive), p.ej.
``TOP_K`` -> ``top_k``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parámetros del demo, leídos de entorno (con ``.env`` opcional para dev local)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Infra / demo (inyectadas en provisión por el gateway efímero) ---
    project_id: str = ""  # PROJECT_ID
    demo_slot: str = ""  # DEMO_SLOT

    # --- Servidor de la app (ingress interno, sin TLS: lo terminan ACA + gateway) ---
    app_host: str = "0.0.0.0"  # APP_HOST
    app_port: int = 8080  # APP_PORT

    # --- LLM local (Ollama) — $0 API, sin llamadas externas en prod ---
    ollama_host: str = "http://localhost:11434"  # OLLAMA_HOST
    llm_model: str = "qwen2.5:1.5b-instruct"  # LLM_MODEL (opción 7B por env)
    max_output_tokens: int = 512  # MAX_OUTPUT_TOKENS

    # --- Embeddings multilingües (384-d), horneados en la imagen app ---
    embed_model: str = "paraphrase-multilingual-MiniLM-L12-v2"  # EMBED_MODEL

    # --- Vector store (Postgres + pgvector, co-localizado y efímero) ---
    db_dsn: str = "postgresql://rag:rag@localhost:5432/rag"  # DB_DSN

    # --- Retrieval RAG ---
    top_k: int = 5  # TOP_K
    similarity_threshold: float = 0.32  # SIMILARITY_THRESHOLD (grounded-only; calibrado 2026-08-12)

    # --- Ingesta (build-time): chunking ---
    chunk_tokens: int = 600  # CHUNK_TOKENS
    chunk_overlap: int = 80  # CHUNK_OVERLAP


@lru_cache
def get_settings() -> Settings:
    """Devuelve el ``Settings`` cacheado (una sola lectura de entorno por proceso)."""
    return Settings()
