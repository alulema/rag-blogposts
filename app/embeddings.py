"""Embeddings de la query en runtime (mismo modelo multilingüe que la ingesta).

Se hornea en la imagen ``app`` y se carga una vez al arranque. ``sentence-transformers`` (torch)
se importa de forma perezosa para no exigir la dependencia pesada solo por importar el módulo.
"""

from __future__ import annotations


class Embedder:
    """Codifica la query a un vector 384-d L2-normalizado (para similitud coseno)."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed_query(self, text: str) -> list[float]:
        vec = self._model.encode([text], normalize_embeddings=True)[0]
        return [float(x) for x in vec]
