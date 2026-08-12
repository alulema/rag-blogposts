"""Calibración de ``SIMILARITY_THRESHOLD`` (umbral de rehúso grounded).

El umbral decide el rehúso: la app responde solo si el **top-1** de similitud coseno del retrieval
supera el umbral; si no, rehúsa ("solo puedo responder sobre los posts de Alexis").

Este harness corre contra el **pgvector sembrado** (NUC/CI, requiere torch para embeber la query):
lanza una batería de preguntas etiquetadas —dentro del corpus (EN/ES), cross-lingual y fuera del
corpus— imprime la distribución de scores y **recomienda un umbral** que separe ambos grupos.

Uso (en la NUC, con Postgres sembrado + venv):
    python -m tools.calibrate_threshold
    python -m tools.calibrate_threshold --top-k 5 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

from app.config import get_settings
from app.retrieval import vector_literal

# ── Baterías de preguntas etiquetadas (basadas en el corpus real del blog) ──────────────
# in_corpus: deberían recuperar contenido relevante (score alto → responder).
# out_corpus: no tienen respuesta en el blog (score bajo → rehusar).
IN_CORPUS: dict[str, list[str]] = {
    "en": [
        "What are activation functions in neural networks?",
        "How does asyncio work in Python?",
        "Explain Support Vector Machines for classification",
        "How do transformers work internally?",
        "What is Cholesky decomposition for linear regression?",
        "How do I profile memory usage in Python?",
        "How to implement the Levenshtein algorithm in JavaScript?",
        "How do I declare tensors in TensorFlow?",
    ],
    "es": [
        "¿Qué son las funciones de activación?",
        "¿Cómo funcionan los transformers internamente?",
        "¿Cómo funciona asyncio en Python?",
        "¿Qué es la descomposición de Cholesky?",
    ],
    # Cross-lingual: pregunta en un idioma, contenido predominante en el otro.
    "cross": [
        "What is StableDiffusion image generation about?",  # post ES
        "¿Cómo declarar variables y placeholders en TensorFlow?",  # post EN
    ],
}
OUT_CORPUS: list[str] = [
    "Who won the 2022 FIFA World Cup?",
    "What's the best recipe for pizza dough?",
    "What is the capital of France?",
    "How tall is Mount Everest?",
    "¿Cuál es la mejor receta de ceviche?",
    "Who is Taylor Swift?",
    "What will the weather be tomorrow in Quito?",
]

_SCORE_SQL = """
SELECT title, lang, 1 - (embedding <=> %(vec)s::vector) AS score
FROM chunks
ORDER BY embedding <=> %(vec)s::vector
LIMIT %(k)s
"""


@dataclass
class Probe:
    query: str
    label: str  # "in" | "out"
    group: str  # "en" | "es" | "cross" | "out"
    top1: float = 0.0
    top_title: str = ""


@dataclass
class Recommendation:
    threshold: float
    separated: bool
    in_min: float
    out_max: float
    gap: float
    misclassified_in: list[str] = field(default_factory=list)
    misclassified_out: list[str] = field(default_factory=list)


def recommend_threshold(
    in_top1: list[float],
    out_top1: list[float],
    margin_frac: float = 0.5,
) -> Recommendation:
    """Recomienda un umbral a partir de los top-1 scores etiquetados.

    Si hay separación limpia (min in-corpus > max out-corpus), pone el umbral en un punto
    intermedio (``margin_frac`` del hueco). Si hay solapamiento, elige el umbral observado que
    maximiza la precisión de clasificación (responder in-corpus / rehusar out-corpus) y reporta
    los casos mal clasificados.
    """
    if not in_top1 or not out_top1:
        raise ValueError("se requieren scores in-corpus y out-corpus")

    in_min, out_max = min(in_top1), max(out_top1)

    if in_min > out_max:
        threshold = round(out_max + (in_min - out_max) * margin_frac, 3)
        return Recommendation(
            threshold=threshold,
            separated=True,
            in_min=in_min,
            out_max=out_max,
            gap=round(in_min - out_max, 4),
        )

    # Solapamiento: barre umbrales candidatos y maximiza aciertos (desempata por mayor umbral).
    candidates = sorted({round(s, 4) for s in in_top1 + out_top1})
    best_threshold, best_correct = candidates[0], -1
    for cand in candidates:
        correct = sum(s >= cand for s in in_top1) + sum(s < cand for s in out_top1)
        if correct >= best_correct:
            best_correct, best_threshold = correct, cand
    return Recommendation(
        threshold=round(best_threshold, 3),
        separated=False,
        in_min=in_min,
        out_max=out_max,
        gap=round(in_min - out_max, 4),
        misclassified_in=[f"{s:.3f}" for s in in_top1 if s < best_threshold],
        misclassified_out=[f"{s:.3f}" for s in out_top1 if s >= best_threshold],
    )


def _build_probes() -> list[Probe]:
    probes = [Probe(q, "in", g) for g, qs in IN_CORPUS.items() for q in qs]
    probes += [Probe(q, "out", "out") for q in OUT_CORPUS]
    return probes


def _score_probes(probes: list[Probe], top_k: int) -> None:
    """Rellena ``top1``/``top_title`` de cada probe consultando el pgvector sembrado."""
    import psycopg

    from app.embeddings import Embedder

    settings = get_settings()
    embedder = Embedder(settings.embed_model)
    with psycopg.connect(settings.db_dsn) as conn:
        for p in probes:
            vec = vector_literal(embedder.embed_query(p.query))
            rows = conn.execute(_SCORE_SQL, {"vec": vec, "k": top_k}).fetchall()
            if rows:
                p.top_title, p.top1 = rows[0][0], float(rows[0][2])


def _print_report(probes: list[Probe], rec: Recommendation) -> None:
    groups = {
        "en": "IN-CORPUS (EN)",
        "es": "IN-CORPUS (ES)",
        "cross": "CROSS-LINGUAL",
        "out": "OUT-OF-CORPUS",
    }
    for g, label in groups.items():
        rows = [p for p in probes if p.group == g]
        if not rows:
            continue
        print(f"\n{label}")
        for p in sorted(rows, key=lambda x: x.top1, reverse=True):
            print(f"  top1={p.top1:.3f}  {p.query[:56]:56}  → {p.top_title[:34]}")

    print("\n" + "=" * 72)
    print(f"in-corpus  top1 min = {rec.in_min:.3f}")
    print(f"out-corpus top1 max = {rec.out_max:.3f}")
    verdict = "SEPARADO" if rec.separated else "SOLAPADO"
    print(f"gap (min_in - max_out) = {rec.gap:+.4f}  →  {verdict}")
    if not rec.separated:
        if rec.misclassified_in:
            print(f"  ⚠ in-corpus que se rehusarían: {rec.misclassified_in}")
        if rec.misclassified_out:
            print(f"  ⚠ out-corpus que se responderían: {rec.misclassified_out}")
    print(f"\n>>> SIMILARITY_THRESHOLD recomendado: {rec.threshold}")
    print("=" * 72)


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Calibra SIMILARITY_THRESHOLD vs pgvector sembrado.")
    ap.add_argument("--top-k", type=int, default=None, help="LIMIT del retrieval (default: TOP_K)")
    ap.add_argument("--margin-frac", type=float, default=0.5, help="posición en el hueco [0..1]")
    ap.add_argument("--json", action="store_true", help="imprime la recomendación como JSON")
    args = ap.parse_args(argv)

    top_k = args.top_k or get_settings().top_k
    probes = _build_probes()
    _score_probes(probes, top_k)

    rec = recommend_threshold(
        [p.top1 for p in probes if p.label == "in"],
        [p.top1 for p in probes if p.label == "out"],
        margin_frac=args.margin_frac,
    )

    if args.json:
        print(json.dumps(rec.__dict__, ensure_ascii=False, indent=2))
    else:
        _print_report(probes, rec)


if __name__ == "__main__":
    main()
