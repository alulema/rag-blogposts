"""Tests de integración del endpoint SSE (``app.main``) con retriever/ollama falsos.

No se ejecuta el ``lifespan`` (TestClient sin context manager), así que no se requiere
torch/psycopg/Ollama: las dependencias se sustituyen vía ``dependency_overrides``.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app import rag
from app.main import app, get_ollama, get_retriever
from app.retrieval import RetrievedChunk

_CHUNK = RetrievedChunk(
    url="https://alexisalulema.com/blog/x/",
    title="X Post",
    lang="en",
    published=date(2020, 1, 1),
    chunk_index=0,
    content="content about X",
    score=0.8,
)


class _FakeRetriever:
    def __init__(self, chunks):
        self._chunks = chunks

    def retrieve(self, query):
        return self._chunks


class _FakeContextualRetriever:
    """Solo devuelve chunks si la query trae el contexto del turno anterior (para probar el
    fallback de retrieval en ``main.chat`` cuando la pregunta sola no alcanza el umbral)."""

    def __init__(self, chunks, needle):
        self._chunks = chunks
        self._needle = needle
        self.queries = []

    def retrieve(self, query):
        self.queries.append(query)
        return self._chunks if self._needle in query else []


class _FakeOllama:
    def __init__(self, tokens):
        self._tokens = tokens
        self.calls = []  # [(messages, max_tokens), ...] -- una entrada por invocación

    async def stream_chat(self, messages, max_tokens=None):
        self.calls.append((messages, max_tokens))
        for tok in self._tokens:
            yield tok


def _client(chunks, tokens):
    app.dependency_overrides[get_retriever] = lambda: _FakeRetriever(chunks)
    app.dependency_overrides[get_ollama] = lambda: _FakeOllama(tokens)
    return TestClient(app)


def teardown_function(_):
    app.dependency_overrides.clear()


def test_chat_streams_sources_tokens_done():
    client = _client([_CHUNK], ["Hello", " world"])
    r = client.post("/chat", json={"messages": [{"role": "user", "content": "What is X?"}]})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    assert "event: sources" in body
    assert "https://alexisalulema.com/blog/x/" in body  # cita
    assert "event: token" in body
    assert "Hello" in body and "world" in body
    assert "event: done" in body


def test_chat_no_context_gets_friendly_llm_redirect_not_canned_refusal():
    """Sin contexto grounded, se llama al LLM con un prompt de redirección amable (Opción B,
    reporte del dueño 2026-08-20) en vez del rehúso enlatado -- misma frase siempre, sensación
    robótica."""
    ollama = _FakeOllama(["No tengo esa información, pero puedo ayudarte con Python o RAG."])
    app.dependency_overrides[get_retriever] = lambda: _FakeRetriever([])
    app.dependency_overrides[get_ollama] = lambda: ollama
    client = TestClient(app)

    r = client.post(
        "/chat", json={"messages": [{"role": "user", "content": "¿Quién ganó el mundial 2022?"}]}
    )
    body = r.text
    assert "event: sources\ndata: []" in body  # sin citas
    assert "No tengo esa información" in body  # respuesta del LLM, no el rehúso enlatado

    assert len(ollama.calls) == 1
    messages, max_tokens = ollama.calls[0]
    assert messages[0]["role"] == "system"
    assert "blog" in messages[0]["content"].lower()  # system prompt de redirección, no el grounded
    assert messages[-1] == {"role": "user", "content": "¿Quién ganó el mundial 2022?"}
    assert max_tokens == rag.NO_CONTEXT_MAX_TOKENS  # respuesta corta, no el presupuesto completo


def test_chat_retries_retrieval_with_context_on_followup():
    """Follow-up sin señal propia ("¿y en Python?"): reintenta con el turno anterior antes de
    rehusar, en vez de cortar directo al mensaje enlatado."""
    retriever = _FakeContextualRetriever([_CHUNK], needle="DDD")
    app.dependency_overrides[get_retriever] = lambda: retriever
    app.dependency_overrides[get_ollama] = lambda: _FakeOllama(["ok"])
    client = TestClient(app)

    r = client.post(
        "/chat",
        json={
            "messages": [
                {"role": "user", "content": "What is DDD?"},
                {"role": "assistant", "content": "Domain-Driven Design is..."},
                {"role": "user", "content": "and in Python?"},
            ]
        },
    )
    body = r.text
    assert "https://alexisalulema.com/blog/x/" in body  # encontró la cita en el reintento
    assert retriever.queries == ["and in Python?", "What is DDD? and in Python?"]


def test_chat_followup_without_context_match_gets_friendly_llm_redirect():
    """Si ni siquiera el reintento con contexto encuentra chunks, se llama al LLM con el prompt
    de redirección (no un rehúso enlatado) -- sin loops de retrieval, y el historial se preserva
    para que el LLM tenga la conversación completa."""
    retriever = _FakeContextualRetriever([], needle="nunca-matchea")
    ollama = _FakeOllama(["No encuentro eso en el blog, pero sí puedo hablarte de Python."])
    app.dependency_overrides[get_retriever] = lambda: retriever
    app.dependency_overrides[get_ollama] = lambda: ollama
    client = TestClient(app)

    r = client.post(
        "/chat",
        json={
            "messages": [
                {"role": "user", "content": "¿Quién ganó el mundial 2022?"},
                {"role": "assistant", "content": "Solo puedo responder..."},
                {"role": "user", "content": "¿y el de 2018?"},
            ]
        },
    )
    body = r.text
    assert "No encuentro eso en el blog" in body

    assert len(ollama.calls) == 1  # sin loops: un solo intento de generación tras el retry
    messages, max_tokens = ollama.calls[0]
    assert messages[0]["role"] == "system"
    assert {"role": "user", "content": "¿Quién ganó el mundial 2022?"} in messages
    assert {"role": "assistant", "content": "Solo puedo responder..."} in messages
    assert max_tokens == rag.NO_CONTEXT_MAX_TOKENS


def test_chat_rejects_non_user_last_message():
    client = _client([_CHUNK], ["x"])
    r = client.post("/chat", json={"messages": [{"role": "assistant", "content": "hi"}]})
    assert r.status_code == 400


def test_chat_greeting_returns_welcome_message():
    """Un saludo puro (sin pregunta) devuelve un mensaje de bienvenida sin retrieval/LLM."""
    # El retriever y ollama no deben ser invocados si is_greeting es True.
    # Las dependencias se setean como dummy pero no se usan en este flujo.
    client = _client([], ["should-not-be-used"])

    r = client.post("/chat", json={"messages": [{"role": "user", "content": "Hola"}]})
    assert r.status_code == 200
    body = r.text
    # Debe contener el mensaje de bienvenida en español
    assert "event: sources" in body
    assert "event: token" in body
    assert "event: done" in body
    # No debe haber citas (source list vacía)
    assert "[]" in body  # sources: []
    # El mensaje debe mencionar blog/Alexis o hola
    assert "Hola" in body or "blog" in body.lower()
    # El LLM dummy no debe ser usado
    assert "should-not-be-used" not in body


def test_chat_greeting_en():
    """Un saludo en inglés devuelve bienvenida en inglés."""
    client = _client([], ["should-not-be-used"])

    r = client.post("/chat", json={"messages": [{"role": "user", "content": "Hi"}]})
    assert r.status_code == 200
    body = r.text
    assert "event: sources" in body
    assert "event: done" in body
    # El LLM dummy no debe ser usado
    assert "should-not-be-used" not in body


def test_healthz():
    assert TestClient(app).get("/healthz").json() == {"status": "ok"}


def test_root_serves_chat_ui():
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "demo-theme.css" in r.text  # tema del sitio enlazado en vivo
    assert 'id="composer"' in r.text  # UI de chat (no el placeholder)


def test_static_assets_served():
    client = TestClient(app)
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
