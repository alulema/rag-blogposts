"""Tests de extracción/limpieza de contenido (``ingest.clean``).

Usa un fixture HTML sintético que reproduce la estructura real del tema Astro:
``post-header`` (meta) + ``post-content`` con una ligadura de icono suelta (``beenhere``),
un Table of Contents (heading + lista de anclas ``#``) y un bloque de código ``<pre>``.
"""

from __future__ import annotations

from datetime import date

from ingest.clean import extract_post

_HTML = """
<html lang="en"><head>
  <title>Sample Post — Alexis Alulema</title>
  <meta property="og:title" content="Sample Post — Alexis Alulema">
</head><body><main>
  <article class="post-article section"><div class="container container--narrow">
    <header class="post-header">
      <div class="post-meta">
        <time datetime="2022-09-23T00:00:00.000Z">September 23, 2022</time> 5 min read
      </div>
      <h1 class="post-title">Sample Post</h1>
      <p class="post-description"><em>beenhere</em>Update summary</p>
      <div class="post-tags">
        <span class="badge">Python</span><span class="badge">machine-learning</span>
      </div>
    </header>
    <div class="post-content prose">
      <p><em>beenhere</em></p>
      <h3>Table of Contents</h3>
      <ul><li><a href="#intro">Intro</a></li><li><a href="#more">More</a></li></ul>
      <h3>Intro</h3>
      <p>First paragraph about activation functions. It has two sentences here.</p>
      <p>The variable
        <span class="katex">
          <span class="katex-mathml">x x</span>
          <span class="katex-html" aria-hidden="true">x</span>
        </span>
        matters.</p>
      <p>Softplus&#160;is&#160;smooth.</p>
      <pre class="astro-code"><code>import tensorflow as tf
x = tf.constant(1)</code></pre>
      <p>Closing paragraph with a citation-worthy fact.</p>
    </div>
    <footer class="post-footer"><a href="/blog/">← Back to blog</a></footer>
  </div></article>
</main></body></html>
"""


def _post(url="https://alexisalulema.com/blog/sample/"):
    return extract_post(_HTML, url)


def test_metadata():
    p = _post()
    assert p.title == "Sample Post"
    assert p.lang == "en"
    assert p.published == date(2022, 9, 23)


def test_lang_from_es_url():
    p = extract_post(_HTML, "https://alexisalulema.com/es/blog/sample/")
    assert p.lang == "es"


def test_icon_ligature_removed():
    assert "beenhere" not in _post().text


def test_toc_removed():
    text = _post().text
    assert "Table of Contents" not in text
    # los items del ToC (anclas #) no deben quedar como contenido
    assert "\nIntro\nMore\n" not in text


def test_body_kept_including_code():
    text = _post().text
    assert "First paragraph about activation functions." in text
    assert "import tensorflow as tf" in text  # bloque de código preservado
    assert "Closing paragraph" in text
    # metadatos (tags, fecha suelta, back-link) fuera del cuerpo
    assert "min read" not in text
    assert "Back to blog" not in text


def test_katex_mathml_deduplicated():
    text = _post().text
    assert "The variable x matters." in text  # visual .katex-html ("x"), no la copia MathML
    assert "x x" not in text


def test_nbsp_normalized():
    assert "Softplus is smooth." in _post().text  # &nbsp; -> espacio normal


def test_tags_extracted_lowercased_in_order():
    assert _post().tags == ("python", "machine-learning")  # "Python" -> "python"


def test_tags_not_in_body():
    text = _post().text
    assert "python" not in text.lower()
    assert "machine-learning" not in text.lower()


def test_no_tags_div_yields_empty_tuple():
    html_no_tags = _HTML.replace(
        '<div class="post-tags">\n        <span class="badge">Python</span>'
        '<span class="badge">machine-learning</span>\n      </div>',
        "",
    )
    assert extract_post(html_no_tags, "https://alexisalulema.com/blog/sample/").tags == ()
