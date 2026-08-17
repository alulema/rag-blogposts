"""Extracción/limpieza del contenido principal de un post (tema Astro de alexisalulema.com).

El contenido vive en ``<div class="post-content prose">``; ``<header class="post-header">`` y
``<footer class="post-footer">`` son metadatos/navegación. Dentro del contenido se limpian:
un **Table of Contents** (heading + lista de anclas ``#``) y **ligaduras de iconos** de Material
Symbols (p.ej. el texto suelto ``beenhere``), además de glifos del área de uso privado (PUA).

El header también trae ``<div class="post-tags"><span class="badge">…</span></div>``: los tags
que el autor curó a mano al publicar (p.ej. ``python``, ``transformers``). Se extraen a
``Post.tags`` — no van al cuerpo del chunk, pero alimentan el resumen sintético del blog (ver
``ingest/overview.py``): la fuente de verdad de "de qué trata" cada post, más confiable que
adivinarlo por keywords del texto.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

CONTENT_SELECTORS = (".post-content", ".prose", "article", "main")
DROP_TAGS = [
    "script",
    "style",
    "svg",
    "noscript",
    "form",
    "button",
    "iframe",
    "header",
    "footer",
    "nav",
    "aside",
]
BLOCK_TAGS = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "pre",
    "blockquote",
    "figcaption",
    "td",
    "th",
}
TOC_HEADINGS = {
    "table of contents",
    "contents",
    "tabla de contenidos",
    "tabla de contenido",
    "contenido",
    "contenidos",
    "índice",
    "indice",
}
# Ligaduras de Material Symbols que aparecen como iconos sueltos en el contenido.
ICON_LIGATURES = {"beenhere"}
TITLE_SUFFIX = " — Alexis Alulema"


@dataclass(frozen=True)
class Post:
    url: str
    title: str
    lang: str
    published: date | None
    text: str
    tags: tuple[str, ...] = ()


def _strip_pua(s: str) -> str:
    """Normaliza a NFC, mapea nbsp->espacio, quita zero-width/BOM y glifos PUA (iconos)."""
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\u00a0", " ").replace("\u200b", "").replace("\u200c", "").replace("\ufeff", "")
    return "".join(c for c in s if not (0xE000 <= ord(c) <= 0xF8FF))


def _title(soup: BeautifulSoup, article: Tag | None) -> str:
    h1 = article.find("h1") if article else None
    if h1 and h1.get_text(strip=True):
        return re.sub(r"\s+", " ", _strip_pua(h1.get_text(" ", strip=True))).strip()
    og = soup.find("meta", attrs={"property": "og:title"})
    raw = (og.get("content") if og else None) or (soup.title.get_text() if soup.title else "")
    raw = raw.replace(TITLE_SUFFIX, "").strip()
    return re.sub(r"\s+", " ", _strip_pua(raw)).strip()


def _published(article: Tag | None) -> date | None:
    t = article.find("time") if article else None
    iso = t.get("datetime") if t else None
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _tags(article: Tag | None) -> tuple[str, ...]:
    """Tags del post (``<div class="post-tags"><span class="badge">…</span></div>``), en el
    header — curados a mano por el autor al publicar. No confundir con keywords extraídas: son
    la fuente de verdad de "de qué trata" cada post (ver ``ingest/overview.py``)."""
    box = article.select_one(".post-tags") if article else None
    if not box:
        return ()
    out: list[str] = []
    for badge in box.select(".badge"):
        t = _strip_pua(badge.get_text(strip=True)).strip().lower()
        if t:
            out.append(t)
    return tuple(out)


def _lang(url: str, soup: BeautifulSoup) -> str:
    if "/es/blog/" in url:
        return "es"
    if "/blog/" in url:
        return "en"
    html = soup.find("html")
    code = (html.get("lang") if html else None) or "en"
    return "es" if code.lower().startswith("es") else "en"


def _remove_icons(content: Tag) -> None:
    for el in content.find_all(["em", "span", "i", "b", "strong", "p", "li"]):
        if el.find():  # solo elementos hoja (sin hijos-tag)
            continue
        if el.get_text(strip=True).lower() in ICON_LIGATURES:
            parent = el.parent
            el.decompose()
            if isinstance(parent, Tag) and not parent.get_text(strip=True):
                parent.decompose()


def _remove_toc(content: Tag) -> None:
    for h in content.find_all(re.compile(r"^h[1-6]$")):
        if h.get_text(strip=True).lower() in TOC_HEADINGS:
            sib = h.find_next_sibling()
            h.decompose()
            if sib and sib.name in ("ul", "ol"):
                sib.decompose()


def _iter_blocks(content: Tag) -> list[str]:
    """Texto de cada bloque hoja; ``<pre>`` conserva saltos de línea (código)."""
    blocks: list[str] = []
    for el in content.find_all(BLOCK_TAGS):
        if el.find(lambda c: isinstance(c, Tag) and c.name in BLOCK_TAGS):
            continue  # evita duplicar bloques anidados (p.ej. <p> dentro de <li>)
        sep = "\n" if el.name == "pre" else " "
        txt = el.get_text(sep, strip=True)
        if txt:
            blocks.append(txt)
    return blocks


def _body_text(content: Tag) -> str:
    text = "\n\n".join(_iter_blocks(content))
    text = _strip_pua(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_post(html: str, url: str) -> Post:
    """Parsea el HTML de un post y devuelve título, idioma, fecha y cuerpo limpio."""
    soup = BeautifulSoup(html, "lxml")
    article = soup.find("article")

    title = _title(soup, article)
    published = _published(article)
    lang = _lang(url, soup)
    tags = _tags(article)

    content: Tag | None = None
    for sel in CONTENT_SELECTORS:
        content = soup.select_one(sel)
        if content:
            break
    if content is None:
        content = soup.body or soup

    for tag in content.find_all(DROP_TAGS):
        tag.decompose()
    # KaTeX: quita la copia MathML/anotación LaTeX (lector de pantalla) y conserva la visual
    # (.katex-html); evita duplicar el texto de las fórmulas (p.ej. "x x" -> "x").
    for el in content.select(".katex-mathml"):
        el.decompose()
    _remove_icons(content)
    _remove_toc(content)

    return Post(
        url=url, title=title, lang=lang, published=published, text=_body_text(content), tags=tags
    )
