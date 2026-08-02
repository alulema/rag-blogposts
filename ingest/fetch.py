"""Fetch de la fuente pública: ``sitemap-index.xml`` -> URLs de posts -> HTML.

Solo datos públicos (los posts ya son públicos). No depende del repo privado del sitio.
"""

from __future__ import annotations

import re

import requests

SITEMAP_INDEX = "https://alexisalulema.com/sitemap-index.xml"

# Post de blog: /blog/<slug>/ o /es/blog/<slug>/ (excluye los índices /blog/ y /es/blog/).
_BLOG_POST_RE = re.compile(r"/(?:es/)?blog/[^/]+/?$")
_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.DOTALL)

DEFAULT_TIMEOUT = 30
_HEADERS = {"User-Agent": "rag-blogposts-ingest/0.1 (+https://alexisalulema.com)"}


def _get(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    resp = requests.get(url, timeout=timeout, headers=_HEADERS)
    resp.raise_for_status()
    resp.encoding = "utf-8"  # el sitio es UTF-8; evita que requests adivine Latin-1 (mojibake)
    return resp.text


def fetch_sitemap_urls(index_url: str = SITEMAP_INDEX, timeout: int = DEFAULT_TIMEOUT) -> list[str]:
    """Devuelve todas las ``<loc>`` del sitemap, siguiendo sub-sitemaps ``.xml``."""
    locs = _LOC_RE.findall(_get(index_url, timeout))
    urls: list[str] = []
    for loc in locs:
        if loc.endswith(".xml"):
            urls.extend(_LOC_RE.findall(_get(loc, timeout)))
        else:
            urls.append(loc)
    return urls


def blog_post_urls(urls: list[str]) -> list[str]:
    """Filtra a URLs de posts de blog (excluye índices y páginas estáticas)."""
    return [u for u in urls if _BLOG_POST_RE.search(u)]


def post_lang(url: str) -> str:
    """Idioma derivado del prefijo de URL: ``/es/blog/`` -> ``es``, si no ``en``."""
    return "es" if "/es/blog/" in url else "en"


def fetch_html(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    return _get(url, timeout)
