"""Genera ``db/dump.sql`` (schema + INSERTs + índice HNSW) y un snapshot JSONL.

El ``dump.sql`` se hornea en la imagen ``db`` y siembra pgvector al arranque. El snapshot
(``snapshot.jsonl``, un post por línea con su texto) sirve para *diffing* en el refresh de corpus.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path

from ingest.chunk import Chunk
from ingest.clean import Post


def _vec_literal(vec: Iterable[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def _sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def render_dump(
    chunks: Sequence[Chunk], embeddings: Sequence[Iterable[float]], schema_sql: str
) -> str:
    lines = [schema_sql.strip(), "", "BEGIN;"]
    for ch, emb in zip(chunks, embeddings, strict=True):
        published = _sql_str(ch.published.isoformat()) if ch.published else "NULL"
        lines.append(
            "INSERT INTO chunks (url, title, lang, published, chunk_index, content, embedding) "
            "VALUES ("
            f"{_sql_str(ch.url)}, {_sql_str(ch.title)}, {_sql_str(ch.lang)}, {published}, "
            f"{ch.chunk_index}, {_sql_str(ch.content)}, {_sql_str(_vec_literal(emb))}::vector);"
        )
    lines += [
        "CREATE INDEX IF NOT EXISTS chunks_embedding_idx "
        "ON chunks USING hnsw (embedding vector_cosine_ops);",
        "COMMIT;",
        "",
    ]
    return "\n".join(lines)


def write_dump(
    path: str,
    chunks: Sequence[Chunk],
    embeddings: Sequence[Iterable[float]],
    schema_sql: str,
) -> None:
    Path(path).write_text(render_dump(chunks, embeddings, schema_sql), encoding="utf-8")


def write_snapshot(path: str, posts: Iterable[Post]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for p in posts:
            record = {
                "url": p.url,
                "title": p.title,
                "lang": p.lang,
                "published": p.published.isoformat() if p.published else None,
                "text": p.text,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
