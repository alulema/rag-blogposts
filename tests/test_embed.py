"""Tests de la lógica de ventanas para embeddings (``ingest.embed._windows``).

Valida el sub-windowing (para mean-pooling de chunks > cap del encoder) sin torch, usando un
tokenizer falso a nivel de carácter.
"""

from __future__ import annotations

from ingest.embed import _windows


class _FakeTokenizer:
    """1 carácter = 1 token; decode reconstruye un texto del mismo largo que los ids."""

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return list(range(len(text)))

    def decode(self, ids: list[int]) -> str:
        return "".join(chr(97 + (i % 26)) for i in ids)


def test_short_text_single_window():
    assert _windows("abc", _FakeTokenizer(), max_len=10) == ["abc"]


def test_long_text_splits_into_bounded_windows():
    windows = _windows("x" * 100, _FakeTokenizer(), max_len=20)
    assert len(windows) > 1
    assert all(len(w) <= 20 for w in windows)  # ninguna ventana excede el cap


def test_long_text_covers_the_end():
    # Con 100 tokens, max_len=20 y stride=16 (paso=4), la última ventana llega al final.
    windows = _windows("y" * 100, _FakeTokenizer(), max_len=20)
    assert len(windows[-1]) == 20
