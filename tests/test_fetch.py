"""Tests del filtro de URLs de sitemap (``ingest.fetch``)."""

from __future__ import annotations

from ingest.fetch import blog_post_urls, post_lang

_URLS = [
    "https://alexisalulema.com/",
    "https://alexisalulema.com/about/",
    "https://alexisalulema.com/blog/",
    "https://alexisalulema.com/blog/activation-functions-in-tensorflow/",
    "https://alexisalulema.com/es/blog/",
    "https://alexisalulema.com/es/blog/funciones-de-activacion-en-tensorflow/",
    "https://alexisalulema.com/es/about/",
]


def test_blog_post_urls_excludes_indexes_and_static():
    posts = blog_post_urls(_URLS)
    assert posts == [
        "https://alexisalulema.com/blog/activation-functions-in-tensorflow/",
        "https://alexisalulema.com/es/blog/funciones-de-activacion-en-tensorflow/",
    ]


def test_post_lang():
    assert post_lang("https://alexisalulema.com/blog/x/") == "en"
    assert post_lang("https://alexisalulema.com/es/blog/x/") == "es"
