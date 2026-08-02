"""Chunking sentence-aware (~``chunk_tokens``, solape ~``chunk_overlap``) con metadata.

Empaqueta oraciones/párrafos hasta ``max_tokens`` y arrastra un solape del final del chunk
anterior. Los bloques de código (``<pre>``, detectados por saltos de línea internos) se mantienen
enteros como un solo segmento para no partirlos.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from ingest.clean import Post

# Fin de oración seguido de mayúscula/dígito o apertura ES (¿¡).
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡0-9])")


@dataclass(frozen=True)
class Chunk:
    url: str
    title: str
    lang: str
    published: date | None
    chunk_index: int
    content: str


def split_sentences(paragraph: str) -> list[str]:
    return [p.strip() for p in _SENT_SPLIT.split(paragraph.strip()) if p.strip()]


def _segments(text: str) -> list[str]:
    segs: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if "\n" in para:  # bloque preformateado/código: mantener entero
            segs.append(para)
        else:
            segs.extend(split_sentences(para))
    return segs


def chunk_post(
    post: Post,
    count_tokens: Callable[[str], int],
    max_tokens: int,
    overlap: int,
) -> list[Chunk]:
    segments = _segments(post.text)
    grouped: list[list[str]] = []
    cur: list[str] = []
    cur_tokens = 0

    for seg in segments:
        seg_tokens = count_tokens(seg)
        if cur and cur_tokens + seg_tokens > max_tokens:
            grouped.append(cur)
            carry: list[str] = []
            carry_tokens = 0
            for prev in reversed(cur):
                t = count_tokens(prev)
                if carry_tokens + t > overlap:
                    break
                carry.insert(0, prev)
                carry_tokens += t
            cur = carry
            cur_tokens = carry_tokens
        cur.append(seg)
        cur_tokens += seg_tokens

    if cur:
        grouped.append(cur)

    return [
        Chunk(
            url=post.url,
            title=post.title,
            lang=post.lang,
            published=post.published,
            chunk_index=i,
            content=" ".join(segs).strip(),
        )
        for i, segs in enumerate(grouped)
    ]
