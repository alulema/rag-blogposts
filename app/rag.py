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
