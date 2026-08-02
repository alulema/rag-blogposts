"""FastAPI app del demo RAG: ``POST /chat`` (SSE) + ``/`` placeholder + ``/healthz``.

Sin auth (la hace el gateway), sin TLS (lo termina ACA + gateway), ingress interno en el puerto
de ``config``. Diseñada para teardown abrupto: estado solo en memoria + DB efímera co-localizada.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from app import rag
from app.config import get_settings
from app.ollama_client import OllamaClient
from app.retrieval import Retriever

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS chunks_embedding_idx "
    "ON chunks USING hnsw (embedding vector_cosine_ops)"
)

_PLACEHOLDER = (
    "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
    "<title>RAG · alexisalulema.com</title></head>"
    "<body><h1>RAG demo</h1><p>API activa. La UI de chat llega en la Fase 3. "
    "Endpoint: <code>POST /chat</code> (SSE).</p></body></html>"
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    from psycopg_pool import ConnectionPool

    from app.embeddings import Embedder

    pool = ConnectionPool(settings.db_dsn, min_size=1, max_size=4, open=True)
    _ensure_schema(pool, _SCHEMA_PATH.read_text(encoding="utf-8"))
    app.state.pool = pool
    app.state.retriever = Retriever(
        pool, Embedder(settings.embed_model), settings.top_k, settings.similarity_threshold
    )
    app.state.ollama = OllamaClient(
        settings.ollama_host, settings.llm_model, settings.max_output_tokens
    )
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="rag-blogposts", lifespan=lifespan)


def get_retriever(request: Request) -> Retriever:
    return request.app.state.retriever


def get_ollama(request: Request) -> OllamaClient:
    return request.app.state.ollama


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def root():
    return _PLACEHOLDER


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
