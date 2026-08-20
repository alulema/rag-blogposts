"""Tests del resumen sintético del blog (``ingest.overview``) — funciones puras, sin torch."""

from __future__ import annotations

from datetime import date

from ingest.clean import Post
from ingest.overview import (
    OVERVIEW_TITLES,
    OVERVIEW_URLS,
    build_overview_posts,
)


def _post(title: str, lang: str, published: date | None, tags: tuple[str, ...] = ()) -> Post:
    base = (
        "https://alexisalulema.com/es/blog/" if lang == "es" else "https://alexisalulema.com/blog/"
    )
    return Post(
        url=f"{base}{title.lower()}/",
        title=title,
        lang=lang,
        published=published,
        text="body",
        tags=tags,
    )


def test_one_overview_per_language():
    posts = [
        _post("Activation Functions", "en", date(2017, 10, 15), tags=("tensorflow",)),
        _post("Funciones de Activación", "es", date(2022, 9, 23), tags=("tensorflow",)),
    ]
    overviews = build_overview_posts(posts)
    langs = {o.lang for o in overviews}
    assert langs == {"en", "es"}
    for o in overviews:
        assert o.url == OVERVIEW_URLS[o.lang]
        assert o.title == OVERVIEW_TITLES[o.lang]
        assert o.published is None


def test_overview_text_lists_tags_with_framing():
    posts = [
        _post("Gradient Descent", "en", date(2019, 1, 1), tags=("machine-learning", "python")),
        _post("Neural Networks", "en", date(2020, 1, 1), tags=("deep-learning",)),
    ]
    (overview,) = build_overview_posts(posts)
    # encuadre temático + cada tag enumerado. Los títulos NO son la fuente: un título como
    # "Gradient Descent" puede no aparecer, lo que importa son los tags reales del post.
    assert "topics" in overview.text.lower()
    assert "machine-learning" in overview.text
    assert "python" in overview.text
    assert "deep-learning" in overview.text
    assert overview.text.endswith("covered by the blog.")


def test_tags_alphabetical_and_deduped_case_insensitive():
    posts = [
        _post("Old Post", "en", date(2018, 1, 1), tags=("python", "Machine-Learning")),
        _post("New Post", "en", date(2021, 1, 1), tags=("asyncio",)),
        _post("Dup Post", "en", date(2020, 1, 1), tags=("machine-learning",)),  # dup de arriba
    ]
    (overview,) = build_overview_posts(posts)
    assert overview.text.count("machine-learning") == 1  # deduped sin importar mayúsculas
    idx = overview.text.index
    assert idx("asyncio") < idx("machine-learning") < idx("python")  # alfabético


def test_posts_without_tags_dont_contribute():
    posts = [
        _post("Tagged", "en", date(2021, 1, 1), tags=("python",)),
        _post("Untagged", "en", date(2022, 1, 1)),  # sin tags: no aporta, no rompe
    ]
    (overview,) = build_overview_posts(posts)
    assert overview.text.count("«") == 1  # un solo tag enumerado (el del post con tags)
    assert "python" in overview.text


def test_spanish_overview_is_in_spanish():
    posts = [_post("Funciones de Activación", "es", date(2022, 9, 23), tags=("tensorflow", "ia"))]
    (overview,) = build_overview_posts(posts)
    assert overview.lang == "es"
    assert "temas" in overview.text.lower()
    assert "Alexis Alulema escribe sobre" in overview.text
    assert "tensorflow" in overview.text


def test_empty_posts_yield_no_overview():
    assert build_overview_posts([]) == []


def test_unknown_language_ignored():
    posts = [_post("Something", "fr", None, tags=("python",))]
    assert build_overview_posts(posts) == []


def test_no_tags_at_all_yields_no_overview_for_that_lang():
    posts = [_post("Untagged Only", "en", date(2021, 1, 1))]
    assert build_overview_posts(posts) == []
