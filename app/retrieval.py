"""Retrieval top-k en pgvector (similitud coseno) con umbral *grounded*.

Opera sobre un pool de conexiones inyectado (creado en el arranque de la app), así que este
módulo no importa ``psycopg`` y es testeable con un pool falso. El vector de la query se envía
como literal ``::vector`` (no requiere adaptador de pgvector en Python).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

_QUERY = """
SELECT url, title, lang, published, chunk_index, content,
       1 - (embedding <=> %(vec)s::vector) AS score
FROM chunks
ORDER BY embedding <=> %(vec)s::vector
LIMIT %(k)s
"""


@dataclass(frozen=True)
class RetrievedChunk:
    url: str
    title: str
    lang: str
    published: date | None
    chunk_index: int
    content: str
    score: float


def vector_literal(vec: Iterable[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


class Retriever:
    def __init__(self, pool, embedder, top_k: int, threshold: float) -> None:
        self._pool = pool
        self._embedder = embedder
        self._top_k = top_k
        self._threshold = threshold

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        """Embed de la query -> top-k por coseno -> filtra por umbral grounded."""
        vec = self._embedder.embed_query(query)
        params = {"vec": vector_literal(vec), "k": self._top_k}
        with self._pool.connection() as conn:
            rows = conn.execute(_QUERY, params).fetchall()
        chunks = [RetrievedChunk(*row) for row in rows]
        return [c for c in chunks if c.score >= self._threshold]
