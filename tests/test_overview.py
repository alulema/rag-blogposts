"""Tests del resumen sintético del blog (``ingest.overview``) — funciones puras, sin torch."""

from __future__ import annotations

from datetime import date

from ingest.clean import Post
from ingest.overview import (
    OVERVIEW_TITLES,
    OVERVIEW_URLS,
    build_overview_posts,
)


def _post(title: str, lang: str, published: date | None) -> Post:
    base = (
        "https://alexisalulema.com/es/blog/" if lang == "es" else "https://alexisalulema.com/blog/"
    )
    return Post(
        url=f"{base}{title.lower()}/", title=title, lang=lang, published=published, text="body"
    )


def test_one_overview_per_language():
    posts = [
        _post("Activation Functions", "en", date(2017, 10, 15)),
        _post("Funciones de Activación", "es", date(2022, 9, 23)),
    ]
    overviews = build_overview_posts(posts)
    langs = {o.lang for o in overviews}
    assert langs == {"en", "es"}
    for o in overviews:
        assert o.url == OVERVIEW_URLS[o.lang]
        assert o.title == OVERVIEW_TITLES[o.lang]
        assert o.published is None


def test_overview_text_lists_titles_with_framing():
    posts = [
        _post("Gradient Descent", "en", date(2019, 1, 1)),
        _post("Neural Networks", "en", date(2020, 1, 1)),
    ]
    (overview,) = build_overview_posts(posts)
    # encuadre temático + cada título enumerado
    assert "topics" in overview.text.lower()
    assert "Gradient Descent" in overview.text
    assert "Neural Networks" in overview.text
    assert overview.text.endswith("covered by the blog.")


def test_titles_ordered_newest_first_and_deduped():
    posts = [
        _post("Old Post", "en", date(2018, 1, 1)),
        _post("New Post", "en", date(2021, 1, 1)),
        _post("Mid Post", "en", date(2020, 1, 1)),
        _post("New Post", "en", date(2021, 1, 1)),  # duplicado exacto → una sola vez
    ]
    (overview,) = build_overview_posts(posts)
    assert overview.text.count("New Post") == 1
    idx = overview.text.index
    assert idx("New Post") < idx("Mid Post") < idx("Old Post")


def test_spanish_overview_is_in_spanish():
    posts = [_post("Funciones de Activación", "es", date(2022, 9, 23))]
    (overview,) = build_overview_posts(posts)
    assert overview.lang == "es"
    assert "temas" in overview.text.lower()
    assert "Alexis Alulema escribe sobre" in overview.text


def test_empty_posts_yield_no_overview():
    assert build_overview_posts([]) == []


def test_unknown_language_ignored():
    posts = [_post("Something", "fr", None)]
    assert build_overview_posts(posts) == []
