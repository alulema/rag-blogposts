"""Orquestación de la ingesta build-time.

``sitemap`` -> fetch -> clean -> chunk -> embed -> ``db/dump.sql`` + ``db/snapshot.jsonl``.

Ejemplos (desde la raíz del repo):
    python -m ingest.run --dry-run --limit 3     # sin torch: valida fetch/clean/chunk
    python -m ingest.run                          # run real (requiere torch en NUC/CI)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # permite también `python ingest/run.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from ingest import chunk, clean, dump, fetch, overview  # noqa: E402
from ingest.tokens import get_token_counter  # noqa: E402

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Ingesta RAG: posts públicos -> db/dump.sql")
    ap.add_argument("--limit", type=int, default=None, help="solo los primeros N posts (muestra)")
    ap.add_argument("--langs", default="en,es", help="idiomas a incluir (coma-separados)")
    ap.add_argument("--out", default="db/dump.sql", help="ruta del dump SQL")
    ap.add_argument("--snapshot", default="db/snapshot.jsonl", help="ruta del snapshot JSONL")
    ap.add_argument("--dry-run", action="store_true", help="fetch+clean+chunk, sin embed/escribir")
    ap.add_argument(
        "--no-model-tokenizer",
        action="store_true",
        help="usa la heurística de tokens (sin transformers)",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # títulos con acentos/em-dash en consolas no-UTF8
    settings = get_settings()
    args = _parse_args(argv)
    langs = {x.strip() for x in args.langs.split(",") if x.strip()}

    urls = [
        u for u in fetch.blog_post_urls(fetch.fetch_sitemap_urls()) if fetch.post_lang(u) in langs
    ]
    if args.limit:
        urls = urls[: args.limit]
    print(f"posts a procesar: {len(urls)}")

    count_tokens = get_token_counter(settings.embed_model, prefer_model=not args.no_model_tokenizer)
    posts: list[clean.Post] = []
    chunks: list[chunk.Chunk] = []
    for url in urls:
        post = clean.extract_post(fetch.fetch_html(url), url)
        post_chunks = chunk.chunk_post(
            post, count_tokens, settings.chunk_tokens, settings.chunk_overlap
        )
        posts.append(post)
        chunks.extend(post_chunks)
        pub = post.published.isoformat() if post.published else "----------"
        print(f"  {post.lang} {pub} {len(post_chunks):2d} chunks  {post.title[:58]}")

    # Resumen sintético del blog (uno por idioma): permite responder preguntas meta como
    # "¿de qué temas habla el blog?" que ningún chunk real cubre. Se calcula sobre los posts
    # ya recolectados y fluye por el mismo pipeline (chunk → embed → dump/snapshot).
    for op in overview.build_overview_posts(posts):
        op_chunks = chunk.chunk_post(
            op, count_tokens, settings.chunk_tokens, settings.chunk_overlap
        )
        chunks.extend(op_chunks)
        posts.append(op)
        print(f"  {op.lang} ---------- {len(op_chunks):2d} chunks  {op.title[:58]} (resumen)")
    print(f"total chunks: {len(chunks)}")

    if args.dry_run:
        print("dry-run: sin embeddings ni escritura.")
        return

    from ingest.embed import embed_texts, load_model

    model = load_model(settings.embed_model)
    embeddings = embed_texts(model, [c.content for c in chunks])
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    dump.write_dump(args.out, chunks, embeddings, schema_sql)
    dump.write_snapshot(args.snapshot, posts)
    print(f"escrito {args.out} ({len(chunks)} chunks) y {args.snapshot}")


if __name__ == "__main__":
    main()
