"""FastAPI app del demo RAG: ``POST /chat`` (SSE) + ``/`` placeholder + ``/healthz``.

Sin auth (la hace el gateway), sin TLS (lo termina ACA + gateway), ingress interno en el puerto
de ``config``. Diseñada para teardown abrupto: estado solo en memoria + DB efímera co-localizada.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import rag
from app.config import get_settings
from app.ollama_client import OllamaClient
from app.retrieval import Retriever

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS chunks_embedding_idx "
    "ON chunks USING hnsw (embedding vector_cosine_ops)"
)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


def _ensure_schema(pool, schema_sql: str) -> None:
    statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
    with pool.connection() as conn:
        for stmt in statements:
            conn.execute(stmt)
        conn.execute(_INDEX_SQL)


def _wait_for_db(dsn: str, retries: int = 60, delay: float = 2.0) -> None:
    """Espera a que la DB efímera acepte conexiones (los 3 contenedores arrancan juntos en ACA)."""
    import psycopg

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            return
        except Exception as err:  # noqa: BLE001 - reintenta hasta que Postgres esté listo
            last_err = err
            if attempt < retries - 1:
                time.sleep(delay)
    raise RuntimeError(f"DB no disponible tras {retries} intentos: {last_err}")


async def _warm_up_llm(host: str, model: str, retries: int = 30, delay: float = 2.0) -> None:
    """Precarga el modelo en la memoria de Ollama antes de reportar ``/healthz`` OK.

    El healthcheck de Ollama (``ollama list``, en ``docker-compose.yml``) solo confirma que el
    server responde; el peso del modelo se carga de forma perezosa en la PRIMERA llamada de
    inferencia (``/api/generate`` o ``/api/chat``). Sin este warm-up, esa primera carga (varios
    segundos, no reflejados en las mediciones de TTFT "caliente" del Devlog) la paga el primer
    usuario real del demo, en medio de un stream SSE que el gateway puede cortar por su propio
    timeout de sesión antes de que el modelo termine de cargar y generar. Se dispara un
    ``/api/generate`` sin ``prompt`` — patrón documentado por Ollama para precargar el modelo sin
    generar texto (ver Devlog 2026-08-20, reporte de Verito).
    """
    url = f"{host.rstrip('/')}/api/generate"
    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
        for attempt in range(retries):
            try:
                resp = await client.post(url, json={"model": model})
                resp.raise_for_status()
                return
            except Exception as err:  # noqa: BLE001 - reintenta hasta que Ollama cargue el modelo
                last_err = err
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
    raise RuntimeError(f"Ollama no cargó el modelo tras {retries} intentos: {last_err}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    from psycopg_pool import ConnectionPool

    from app.embeddings import Embedder

    db_retries = int(os.environ.get("DB_WAIT_RETRIES", "60"))
    await run_in_threadpool(_wait_for_db, settings.db_dsn, db_retries)

    pool = ConnectionPool(settings.db_dsn, min_size=1, max_size=4, open=True)
    _ensure_schema(pool, _SCHEMA_PATH.read_text(encoding="utf-8"))
    app.state.pool = pool
    app.state.retriever = Retriever(
        pool, Embedder(settings.embed_model), settings.top_k, settings.similarity_threshold
    )
    app.state.ollama = OllamaClient(
        settings.ollama_host, settings.llm_model, settings.max_output_tokens
    )
    llm_retries = int(os.environ.get("LLM_WARMUP_RETRIES", "30"))
    await _warm_up_llm(settings.ollama_host, settings.llm_model, llm_retries)
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="rag-blogposts", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


def get_retriever(request: Request) -> Retriever:
    return request.app.state.retriever


def get_ollama(request: Request) -> OllamaClient:
    return request.app.state.ollama


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/", response_class=FileResponse)
async def root():
    return FileResponse(_STATIC_DIR / "index.html")


@app.post("/chat")
async def chat(
    req: ChatRequest,
    retriever: Annotated[Retriever, Depends(get_retriever)],
    ollama: Annotated[OllamaClient, Depends(get_ollama)],
):
    if not req.messages or req.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="last message must be from 'user'")
    question = req.messages[-1].content
    history = [m.model_dump() for m in req.messages[:-1]]

    chunks = await run_in_threadpool(retriever.retrieve, question)
    if not chunks and history:
        # Follow-up dependiente de contexto (p.ej. "¿y en Python?"): la pregunta sola no trae
        # señal suficiente para el umbral grounded. Segunda oportunidad con el turno de
        # usuario anterior como contexto antes de rehusar (ver Devlog: memoria/ventana de
        # contexto). No afecta el caso normal (primera pregunta, o pregunta ya autocontenida).
        contextual_query = rag.contextualize_query(question, history)
        if contextual_query != question:
            chunks = await run_in_threadpool(retriever.retrieve, contextual_query)
    cites = rag.citations(chunks)

    async def event_stream():
        yield _sse("sources", cites)
        if not chunks:
            # Grounded-only: sin contexto no se llama al LLM; rehúso en el idioma de la pregunta.
            for word in rag.refusal_message(rag.detect_lang(question)).split(" "):
                yield _sse("token", {"text": word + " "})
        else:
            messages = rag.build_messages(question, history, chunks)
            try:
                async for token in ollama.stream_chat(messages):
                    yield _sse("token", {"text": token})
            except Exception as exc:  # noqa: BLE001 - degradación elegante si Ollama falla
                yield _sse("error", {"message": str(exc)})
        yield _sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
