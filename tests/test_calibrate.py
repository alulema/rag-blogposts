"""Tests de la lógica de recomendación de umbral (``tools.calibrate_threshold``).

Solo prueba la función pura ``recommend_threshold`` (sin DB/torch).
"""

from __future__ import annotations

import pytest

from tools.calibrate_threshold import recommend_threshold


def test_clean_separation_midpoint():
    # in-corpus todos altos, out-corpus todos bajos → hueco limpio, umbral al medio.
    rec = recommend_threshold([0.60, 0.55, 0.70], [0.20, 0.15, 0.30], margin_frac=0.5)
    assert rec.separated is True
    assert rec.in_min == 0.55
    assert rec.out_max == 0.30
    assert rec.threshold == pytest.approx(0.425)  # 0.30 + (0.55-0.30)*0.5
    assert rec.gap == pytest.approx(0.25)


def test_margin_frac_shifts_threshold():
    # margin_frac bajo → umbral más cerca del out_max (más permisivo).
    rec = recommend_threshold([0.60], [0.30], margin_frac=0.2)
    assert rec.threshold == pytest.approx(0.36)  # 0.30 + 0.30*0.2


def test_overlap_maximizes_accuracy():
    # Un out (0.45) por encima de un in (0.40) → solapamiento.
    rec = recommend_threshold([0.40, 0.55, 0.60], [0.20, 0.45, 0.25])
    assert rec.separated is False
    # El mejor umbral clasifica bien 5/6 (sacrifica el in=0.40 o el out=0.45).
    assert 0.40 <= rec.threshold <= 0.55
    total_misclassified = len(rec.misclassified_in) + len(rec.misclassified_out)
    assert total_misclassified <= 1


def test_reports_misclassified():
    rec = recommend_threshold([0.30, 0.50], [0.40])
    # Con umbral óptimo, reporta cualquier caso mal clasificado.
    assert isinstance(rec.misclassified_in, list)
    assert isinstance(rec.misclassified_out, list)


def test_requires_both_groups():
    with pytest.raises(ValueError):
        recommend_threshold([0.5], [])
    with pytest.raises(ValueError):
        recommend_threshold([], [0.2])
