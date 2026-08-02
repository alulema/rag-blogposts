"""Tests del retrieval (``app.retrieval``) con pool/embedder falsos (sin psycopg/torch)."""

from __future__ import annotations

from datetime import date

from app.retrieval import RetrievedChunk, Retriever, vector_literal


class _FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows, capture):
        self._rows = rows
        self._capture = capture

    def execute(self, sql, params=None):
        self._capture["sql"] = sql
        self._capture["params"] = params
        return _FakeCursor(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, rows, capture):
        self._rows = rows
        self._capture = capture

    def connection(self):
        return _FakeConn(self._rows, self._capture)


def _row(url, score):
    return (url, "T", "en", date(2020, 1, 1), 0, "body", score)


def test_retrieve_filters_by_threshold():
    rows = [_row("u1", 0.9), _row("u2", 0.5), _row("u3", 0.2)]
    capture: dict = {}
    retriever = Retriever(_FakePool(rows, capture), _FakeEmbedder(), top_k=5, threshold=0.3)
    out = retriever.retrieve("q")
    assert [c.url for c in out] == ["u1", "u2"]  # 0.2 < umbral -> descartado
    assert all(isinstance(c, RetrievedChunk) for c in out)
    assert capture["params"]["k"] == 5
    assert capture["params"]["vec"].startswith("[") and capture["params"]["vec"].endswith("]")


def test_empty_when_all_below_threshold():
    rows = [_row("u1", 0.1)]
    retriever = Retriever(_FakePool(rows, {}), _FakeEmbedder(), top_k=5, threshold=0.3)
    assert retriever.retrieve("q") == []


def test_vector_literal():
    assert vector_literal([0.1, 0.2]) == "[0.100000,0.200000]"
