"""Tests de chunking (``ingest.chunk``) con un contador de tokens determinista (palabras)."""

from __future__ import annotations

from datetime import date

from ingest.chunk import Chunk, chunk_post
from ingest.clean import Post

_words = str.split


def _count(text: str) -> int:
    return len(_words(text))


def _post(text: str) -> Post:
    return Post(
        url="https://alexisalulema.com/blog/x/",
        title="X",
        lang="en",
        published=date(2020, 1, 1),
        text=text,
    )


def test_chunking_with_overlap():
    text = "One two three. Four five six. Seven eight nine. Ten eleven twelve."
    chunks = chunk_post(_post(text), _count, max_tokens=6, overlap=3)
    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert chunks[0].content == "One two three. Four five six."
    # solape: el inicio del chunk siguiente repite la última oración del anterior
    assert chunks[1].content.startswith("Four five six.")
    assert chunks[2].content.startswith("Seven eight nine.")
    assert isinstance(chunks[0], Chunk)


def test_code_block_kept_whole():
    text = "Intro sentence.\n\nimport tf\nx = 1\ny = 2\n\nAfter code."
    chunks = chunk_post(_post(text), _count, max_tokens=100, overlap=0)
    assert len(chunks) == 1
    assert "import tf\nx = 1\ny = 2" in chunks[0].content


def test_metadata_propagates():
    chunks = chunk_post(_post("Only one short sentence."), _count, max_tokens=50, overlap=10)
    assert len(chunks) == 1
    c = chunks[0]
    assert (c.url, c.title, c.lang, c.published) == (
        "https://alexisalulema.com/blog/x/",
        "X",
        "en",
        date(2020, 1, 1),
    )
