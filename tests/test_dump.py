"""Tests del generador de ``dump.sql`` (``ingest.dump``) con embeddings falsos."""

from __future__ import annotations

from datetime import date

from ingest.chunk import Chunk
from ingest.clean import Post
from ingest.dump import render_dump, write_snapshot

_SCHEMA = "CREATE EXTENSION IF NOT EXISTS vector;\nCREATE TABLE chunks (...);"


def _chunk(**kw) -> Chunk:
    base = dict(
        url="https://alexisalulema.com/blog/x/",
        title="Alex's Post",  # apóstrofo -> debe escaparse a ''
        lang="en",
        published=date(2021, 5, 4),
        chunk_index=0,
        content="Hello 'world'",
    )
    base.update(kw)
    return Chunk(**base)


def test_render_dump_structure_and_escaping():
    sql = render_dump([_chunk()], [[0.1, 0.2, 0.3]], _SCHEMA)
    assert sql.startswith("CREATE EXTENSION IF NOT EXISTS vector;")
    assert (
        "INSERT INTO chunks (url, title, lang, published, chunk_index, content, embedding)" in sql
    )
    assert "'Alex''s Post'" in sql
    assert "'Hello ''world'''" in sql
    assert "'2021-05-04'" in sql
    assert "'[0.100000,0.200000,0.300000]'::vector" in sql
    assert "USING hnsw (embedding vector_cosine_ops)" in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_render_dump_null_published():
    sql = render_dump([_chunk(published=None)], [[0.0, 0.0, 0.0]], _SCHEMA)
    assert ", NULL, " in sql


def test_write_snapshot_jsonl(tmp_path):
    import json

    post = Post(
        url="https://alexisalulema.com/es/blog/y/",
        title="Título",
        lang="es",
        published=date(2020, 1, 2),
        text="Cuerpo con acento é.",
    )
    out = tmp_path / "snap.jsonl"
    write_snapshot(str(out), [post])
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "url": "https://alexisalulema.com/es/blog/y/",
            "title": "Título",
            "lang": "es",
            "published": "2020-01-02",
            "text": "Cuerpo con acento é.",
        }
    ]
