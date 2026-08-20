"""Núcleo RAG: armado de prompt grounded, citas, detección de idioma y rehúso.

Funciones puras (sin I/O) para poder testearlas sin DB/LLM.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from app.retrieval import RetrievedChunk

SYSTEM_PROMPT = (
    "You are a grounded assistant that answers ONLY using the provided context, which comes "
    "from Alexis Alulema's blog posts.\n"
    "Rules:\n"
    "- Reply in the SAME language as the user's question (English or Spanish).\n"
    "- Base every statement strictly on the context. Do NOT use outside knowledge.\n"
    "- If the context does not contain the answer, say —in the user's language— that you can "
    "only answer questions about Alexis Alulema's blog posts.\n"
    "- Cite the sources you use by their titles.\n"
    "- Be concise and accurate."
)

_REFUSAL = {
    "es": "Solo puedo responder preguntas sobre los posts del blog de Alexis Alulema.",
    "en": "I can only answer questions about Alexis Alulema's blog posts.",
}

_ES_CHARS = re.compile(r"[¿¡ñáéíóú]", re.IGNORECASE)
_ES_WORDS = {
    "que",
    "qué",
    "cómo",
    "como",
    "por",
    "para",
    "cuál",
    "cuales",
    "cuáles",
    "dónde",
    "donde",
    "cuándo",
    "cuando",
    "quién",
    "quien",
    "porque",
    "según",
    "el",
    "la",
    "los",
    "las",
    "una",
    "un",
    # Saludos/muletillas comunes sin tilde: sin estas palabras, un mensaje corto como "Hola" no
    # deja ninguna señal ES/EN y cae al default "en" (ver Devlog 2026-08-20, reporte de Verito).
    "hola",
    "buenas",
    "buenos",
    "tardes",
    "noches",
    "gracias",
    "adios",
    "saludos",
    "ayuda",
    "oye",
    "disculpa",
}
_EN_WORDS = {
    "the",
    "what",
    "how",
    "why",
    "is",
    "are",
    "which",
    "where",
    "when",
    "who",
    "because",
    "does",
    "do",
    "a",
    "an",
    "of",
    "hello",
    "hi",
    "hey",
    "thanks",
    "please",
}


def detect_lang(text: str) -> str:
    """Heurística ligera EN/ES para el rehúso (el LLM responde en el idioma vía system prompt)."""
    if _ES_CHARS.search(text):
        return "es"
    words = re.findall(r"[a-záéíóúñ]+", text.lower())
    es = sum(w in _ES_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    return "es" if es > en else "en"


def refusal_message(lang: str) -> str:
    return _REFUSAL.get(lang, _REFUSAL["en"])


def format_context(chunks: Sequence[RetrievedChunk]) -> str:
    return "\n\n".join(f"[{i}] {c.title} ({c.url})\n{c.content}" for i, c in enumerate(chunks, 1))


def contextualize_query(question: str, history: Sequence[dict]) -> str:
    """Antepone el turno de usuario anterior a la pregunta, para el *embed* de retrieval.

    Un follow-up que depende del contexto ("¿y en Python?", "dame un ejemplo") suele traer
    poca señal propia y no pasa el umbral grounded aunque el tema ya se venía tratando; el LLM
    sí recibe el historial completo vía ``build_messages``, pero si el retrieval no encuentra
    chunks, ``main.chat`` rehúsa antes de siquiera invocarlo. Esta función es el fallback: se
    usa solo para volver a intentar el retrieval con contexto, nunca se le manda tal cual al
    LLM (eso lo sigue haciendo ``build_messages`` con el historial real, turno a turno).
    """
    prior_user = next(
        (
            h.get("content")
            for h in reversed(list(history))
            if h.get("role") == "user" and h.get("content")
        ),
        None,
    )
    if not prior_user:
        return question
    return f"{prior_user} {question}"


def build_messages(
    question: str,
    history: Iterable[dict],
    chunks: Sequence[RetrievedChunk],
) -> list[dict]:
    """Ensambla ``system(grounded + contexto) + historial + pregunta`` para Ollama."""
    system = f"{SYSTEM_PROMPT}\n\nContext:\n{format_context(chunks)}"
    messages = [{"role": "system", "content": system}]
    for turn in history:
        role, content = turn.get("role"), turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    return messages


def citations(chunks: Sequence[RetrievedChunk]) -> list[dict]:
    """Posts fuente únicos (dedupe por URL, preservando el orden de relevancia)."""
    seen: dict[str, dict] = {}
    for c in chunks:
        if c.url not in seen:
            seen[c.url] = {
                "title": c.title,
                "url": c.url,
                "lang": c.lang,
                "published": c.published.isoformat() if c.published else None,
            }
    return list(seen.values())
