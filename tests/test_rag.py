"""Tests del núcleo RAG (``app.rag``): prompt, citas, idioma, rehúso."""

from __future__ import annotations

from datetime import date

from app import rag
from app.retrieval import RetrievedChunk


def _c(url, title, score=0.7, lang="en", pub=date(2021, 1, 1), idx=0, content="body"):
    return RetrievedChunk(url, title, lang, pub, idx, content, score)


def test_detect_lang():
    assert rag.detect_lang("¿Cómo funcionan los transformadores?") == "es"
    assert rag.detect_lang("How do transformers work?") == "en"
    assert rag.detect_lang("Qué es softmax") == "es"


def test_detect_lang_greeting_without_accents():
    # Reporte real (Devlog 2026-08-20): "Hola" sin tilde no dejaba señal ES/EN y caía al
    # default "en" -> rehúso en el idioma equivocado.
    assert rag.detect_lang("Hola") == "es"
    assert rag.detect_lang("Buenas, gracias!") == "es"
    assert rag.detect_lang("Hi") == "en"


def test_refusal_message():
    assert "Alexis" in rag.refusal_message("es")
    assert rag.refusal_message("en").startswith("I can only")
    assert rag.refusal_message("xx") == rag.refusal_message("en")  # fallback


def test_is_greeting():
    # Saludos puros (sin pregunta)
    assert rag.is_greeting("Hola") is True
    assert rag.is_greeting("Hi") is True
    assert rag.is_greeting("Buenas") is True
    assert rag.is_greeting("Hey, hello") is True
    # No son saludos puros: tienen contenido adicional
    assert rag.is_greeting("Hola, ¿cómo estás?") is False
    assert rag.is_greeting("Hi, what is RAG?") is False
    # Casos extremos
    assert rag.is_greeting("") is False
    assert rag.is_greeting("   ") is False


def test_greeting_response():
    # ES
    msg_es = rag.greeting_response("es")
    assert "Hola" in msg_es or "hola" in msg_es
    assert "Alexis Alulema" in msg_es or "blog" in msg_es
    # EN
    msg_en = rag.greeting_response("en")
    assert "Hi" in msg_en or "hello" in msg_en.lower()
    assert "Alexis Alulema" in msg_en or "blog" in msg_en


def test_build_messages_structure():
    chunks = [_c("u1", "T1"), _c("u2", "T2")]
    history = [
        {"role": "user", "content": "prev q"},
        {"role": "assistant", "content": "prev a"},
        {"role": "system", "content": "ignore"},  # debe filtrarse
    ]
    msgs = rag.build_messages("current q", history, chunks)
    assert msgs[0]["role"] == "system"
    assert "T1" in msgs[0]["content"] and "u1" in msgs[0]["content"]  # contexto incluido
    assert msgs[1] == {"role": "user", "content": "prev q"}
    assert msgs[2] == {"role": "assistant", "content": "prev a"}
    assert all(m["content"] != "ignore" for m in msgs)
    assert msgs[-1] == {"role": "user", "content": "current q"}


def test_contextualize_query_prepends_prior_user_turn():
    history = [
        {"role": "user", "content": "What is DDD?"},
        {"role": "assistant", "content": "Domain-Driven Design is..."},
    ]
    assert rag.contextualize_query("and in Python?", history) == "What is DDD? and in Python?"


def test_contextualize_query_skips_system_and_uses_most_recent_user_turn():
    history = [
        {"role": "user", "content": "older question"},
        {"role": "assistant", "content": "older answer"},
        {"role": "system", "content": "ignore"},
        {"role": "user", "content": "latest question"},
        {"role": "assistant", "content": "latest answer"},
    ]
    assert rag.contextualize_query("follow-up", history) == "latest question follow-up"


def test_contextualize_query_without_prior_user_turn_returns_question_unchanged():
    assert rag.contextualize_query("first question", []) == "first question"
    assert rag.contextualize_query("q", [{"role": "assistant", "content": "a"}]) == "q"


def test_citations_dedupe_by_url():
    chunks = [_c("u1", "T1"), _c("u1", "T1", score=0.6), _c("u2", "T2")]
    cites = rag.citations(chunks)
    assert [c["url"] for c in cites] == ["u1", "u2"]  # dedupe, orden preservado
    assert cites[0]["published"] == "2021-01-01"
