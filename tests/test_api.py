"""Tests de integración del endpoint SSE (``app.main``) con retriever/ollama falsos.

No se ejecuta el ``lifespan`` (TestClient sin context manager), así que no se requiere
torch/psycopg/Ollama: las dependencias se sustituyen vía ``dependency_overrides``.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

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

    async def stream_chat(self, messages):
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


def test_chat_grounded_refusal_without_context():
    client = _client([], ["should-not-be-used"])
    r = client.post(
        "/chat", json={"messages": [{"role": "user", "content": "¿Quién ganó el mundial 2022?"}]}
    )
    body = r.text
    assert "event: sources\ndata: []" in body  # sin citas
    assert "Solo " in body and "Alulema" in body  # rehúso en español (streamed por palabras)
    assert "should-not-be-used" not in body  # el LLM no se invoca sin contexto


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


def test_chat_refuses_followup_without_prior_context_match():
    """Si ni siquiera el reintento con contexto encuentra chunks, rehúsa igual (sin loops)."""
    retriever = _FakeContextualRetriever([], needle="nunca-matchea")
    app.dependency_overrides[get_retriever] = lambda: retriever
    app.dependency_overrides[get_ollama] = lambda: _FakeOllama(["should-not-be-used"])
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
    assert "Solo " in body and "Alulema" in body
    assert "should-not-be-used" not in body


def test_chat_rejects_non_user_last_message():
    client = _client([_CHUNK], ["x"])
    r = client.post("/chat", json={"messages": [{"role": "assistant", "content": "hi"}]})
    assert r.status_code == 400


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
