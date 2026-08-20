"""Tests de la espera de arranque a la DB (``app.main._wait_for_db``).

Inyecta un ``psycopg`` falso vía ``sys.modules`` para ejercitar la lógica de reintento/raise
sin la dependencia real (ni una DB).
"""

from __future__ import annotations

import sys
import types

import pytest

from app import main


def _fake_psycopg(fail_times: int):
    state = {"calls": 0}

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, _query):
            return None

    def connect(_dsn, connect_timeout=None):
        if state["calls"] < fail_times:
            state["calls"] += 1
            raise OSError("db not ready")
        state["calls"] += 1
        return _FakeConn()

    mod = types.ModuleType("psycopg")
    mod.connect = connect
    return mod, state


def test_wait_for_db_succeeds_after_retries(monkeypatch):
    mod, state = _fake_psycopg(fail_times=3)
    monkeypatch.setitem(sys.modules, "psycopg", mod)
    monkeypatch.setattr(main.time, "sleep", lambda _s: None)

    main._wait_for_db("dsn", retries=10, delay=0)
    assert state["calls"] == 4  # 3 fallos + 1 éxito


def test_wait_for_db_raises_after_exhausting(monkeypatch):
    mod, _state = _fake_psycopg(fail_times=999)
    monkeypatch.setitem(sys.modules, "psycopg", mod)
    monkeypatch.setattr(main.time, "sleep", lambda _s: None)

    with pytest.raises(RuntimeError, match="DB no disponible"):
        main._wait_for_db("dsn", retries=5, delay=0)


def _fake_httpx_async_client(fail_times: int):
    """``httpx.AsyncClient`` falso: falla ``fail_times`` POSTs y luego responde 200."""
    state = {"calls": 0}

    class _FakeResponse:
        def raise_for_status(self):
            return None

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, _url, json=None):
            if state["calls"] < fail_times:
                state["calls"] += 1
                raise OSError("ollama not ready")
            state["calls"] += 1
            return _FakeResponse()

    def make_client(*args, **kwargs):
        return _FakeClient()

    return make_client, state


def test_warm_up_llm_succeeds_after_retries(monkeypatch):
    make_client, state = _fake_httpx_async_client(fail_times=2)
    monkeypatch.setattr(main.httpx, "AsyncClient", make_client)

    import asyncio

    asyncio.run(
        main._warm_up_llm("http://localhost:11434", "qwen2.5:0.5b-instruct", retries=5, delay=0)
    )
    assert state["calls"] == 3  # 2 fallos + 1 éxito


def test_warm_up_llm_raises_after_exhausting(monkeypatch):
    make_client, _state = _fake_httpx_async_client(fail_times=999)
    monkeypatch.setattr(main.httpx, "AsyncClient", make_client)

    import asyncio

    with pytest.raises(RuntimeError, match="Ollama no cargó el modelo"):
        asyncio.run(
            main._warm_up_llm("http://localhost:11434", "qwen2.5:0.5b-instruct", retries=3, delay=0)
        )
