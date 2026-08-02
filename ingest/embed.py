"""Embeddings multilingües (384-d) con ``sentence-transformers``.

El encoder ``paraphrase-multilingual-MiniLM-L12-v2`` trunca a ~128 tokens, pero los chunks son de
~600. Para que el vector represente el **chunk completo** (no solo su inicio) se promedian (mean-
pooling) los embeddings de ventanas de ≤128 tokens, con re-normalización L2. Requiere torch: corre
en la ingesta (CI/NUC), no en el entorno de autoría.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

WINDOW_STRIDE = 16  # solape entre ventanas al partir chunks largos para embeber


def load_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def _windows(text: str, tokenizer, max_len: int) -> list[str]:
    ids = tokenizer.encode(text, add_special_tokens=False)
    if len(ids) <= max_len:
        return [text]
    step = max(1, max_len - WINDOW_STRIDE)
    windows: list[str] = []
    for start in range(0, len(ids), step):
        windows.append(tokenizer.decode(ids[start : start + max_len]))
        if start + max_len >= len(ids):
            break
    return windows


def embed_texts(model, texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Devuelve una matriz (n, 384) float32 L2-normalizada (mean-pool de sub-ventanas)."""
    import numpy as np

    tokenizer = model.tokenizer
    max_len = min(int(model.max_seq_length), 128)
    vectors: list[np.ndarray] = []
    for text in texts:
        windows = _windows(text, tokenizer, max_len)
        win_vecs = model.encode(windows, normalize_embeddings=True, batch_size=batch_size)
        pooled = np.asarray(win_vecs, dtype=np.float32).mean(axis=0)
        norm = float(np.linalg.norm(pooled))
        vectors.append(pooled / norm if norm else pooled)
    return np.vstack(vectors).astype(np.float32)
