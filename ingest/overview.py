"""Posts sintéticos de *resumen del blog* para preguntas meta.

Preguntas como «¿de qué temas habla el blog?» / «what is this blog about?» no recuperan bien:
ningún chunk **real** resume el corpus (cada uno es un fragmento de un post concreto), así que el
retrieval no supera el umbral *grounded* y la app rehúsa. Este módulo crea, en build-time, un
``Post`` sintético por idioma cuyo texto enumera los **títulos** de los posts (que *son* los temas)
con un encuadre explícito. Fluyen por el pipeline normal (chunk → embed → dump), de modo que el
retrieval los recupera para preguntas meta y el LLM responde fundamentado. La cita apunta al índice
del blog (``/blog/`` o ``/es/blog/``).

El texto es determinista (títulos ordenados) para no ensuciar el diff del refresh de corpus:
solo cambia cuando se añaden/renombran/eliminan posts —justo cuando el resumen debe actualizarse—.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from ingest.clean import Post

# Índice del blog por idioma: destino natural de la cita para una pregunta «de qué trata el blog».
OVERVIEW_URLS = {
    "en": "https://alexisalulema.com/blog/",
    "es": "https://alexisalulema.com/es/blog/",
}
OVERVIEW_TITLES = {
    "en": "Topics covered in Alexis Alulema's blog",
    "es": "Temas del blog de Alexis Alulema",
}
# Encuadre con sinónimos (topics/subjects/areas · temas/asuntos/áreas) para maximizar el recall
# ante formulaciones variadas de la pregunta meta.
_LEAD = {
    "en": (
        "This is an overview of Alexis Alulema's blog. It summarizes what the blog is about "
        "and the topics, subjects and areas Alexis Alulema writes about. "
        "Alexis Alulema writes about the following topics:"
    ),
    "es": (
        "Este es un resumen del blog de Alexis Alulema. Describe de qué trata el blog y los "
        "temas, asuntos y áreas sobre los que escribe Alexis Alulema. "
        "Alexis Alulema escribe sobre los siguientes temas:"
    ),
}
# Cada título como una oración propia: el chunker las empaqueta y cada segmento queda temático
# (contiene el encuadre «escribe sobre …»), incluso en chunks de desborde si el blog crece mucho.
_ITEM = {
    "en": "Alexis Alulema writes about «{title}».",
    "es": "Alexis Alulema escribe sobre «{title}».",
}
_CLOSING = {
    "en": "These are the main topics and areas covered by the blog.",
    "es": "Estos son los principales temas y áreas que cubre el blog.",
}


def _titles_for_lang(posts: Sequence[Post], lang: str) -> list[str]:
    """Títulos únicos de ese idioma, del más reciente al más antiguo (orden determinista)."""
    items = [p for p in posts if p.lang == lang and p.title.strip()]
    items.sort(key=lambda p: p.title)  # desempate secundario: título asc (estable)
    items.sort(key=lambda p: p.published or date.min, reverse=True)  # primario: fecha desc
    seen: set[str] = set()
    titles: list[str] = []
    for p in items:
        title = p.title.strip()
        if title.lower() not in seen:
            seen.add(title.lower())
            titles.append(title)
    return titles


def _overview_text(lang: str, titles: Sequence[str]) -> str:
    parts = [_LEAD[lang], *(_ITEM[lang].format(title=t) for t in titles), _CLOSING[lang]]
    return " ".join(parts)


def build_overview_posts(posts: Sequence[Post]) -> list[Post]:
    """Un ``Post`` de resumen por idioma presente (en/es) que enumera los temas del blog."""
    result: list[Post] = []
    for lang in sorted({p.lang for p in posts}):
        if lang not in OVERVIEW_URLS:
            continue
        titles = _titles_for_lang(posts, lang)
        if not titles:
            continue
        result.append(
            Post(
                url=OVERVIEW_URLS[lang],
                title=OVERVIEW_TITLES[lang],
                lang=lang,
                published=None,
                text=_overview_text(lang, titles),
            )
        )
    return result
