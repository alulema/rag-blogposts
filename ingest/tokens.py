"""Contador de tokens para el chunking.

Prefiere el tokenizer del modelo de embeddings (cuenta exacta que verá el encoder). En el
entorno de autoría —sin ``transformers``/``torch``— cae a una heurística por palabras, suficiente
para validar la *lógica* de chunking; las fronteras exactas se materializan en el run real (NUC).
"""

from __future__ import annotations

import re
from collections.abc import Callable

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def heuristic_counter() -> Callable[[str], int]:
    """Aproxima subword tokens (~1.3x tokens tipo palabra)."""

    def count(text: str) -> int:
        return int(len(_TOKEN_RE.findall(text)) * 1.3) + 1

    return count


def model_counter(model_name: str) -> Callable[[str], int]:
    """Cuenta con el tokenizer real del modelo (requiere ``transformers``)."""
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_name)

    def count(text: str) -> int:
        return len(tok.encode(text, add_special_tokens=False))

    return count


def get_token_counter(model_name: str, prefer_model: bool = True) -> Callable[[str], int]:
    if prefer_model:
        try:
            return model_counter(model_name)
        except Exception:  # noqa: BLE001 - fallback si no hay transformers/torch/red
            pass
    return heuristic_counter()
