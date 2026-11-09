# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Medir perímetro y área a escala, dividir por marcadores, leer en voz alta y ortografía."""
import pymupdf
import pytest
from PyQt6.QtCore import QPointF, Qt
from core.pages import groups_bookmarks, safe_filename
from ui.canvas_measure import PT, Scale, length, shoelace


def test_formulas():
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert shoelace(sq) == 100
    assert length(sq) == 30 and length(sq, closed=True) == 40


@pytest.fixture
def cv(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow
    p = str(tmp_path / "m.pdf"); d = pymupdf.open(); d.new_page(); d.save(p)
    monkeypatch.setattr(Scale, "paper", 0.0); monkeypatch.setattr(Scale, "_loaded", True)
    win = MainWindow(); win._open_path(p)
    c = win._viewer.canvases[0]; c.ensure_loaded()
    yield c
    from ui.canvas import PageCanvas
    PageCanvas.measure_mode = "dist"
    win._viewer.dirty = False; win.close()


def test_area_y_perimetro_a_escala(cv, monkeypatch):
    from ui.canvas import PageCanvas
    PageCanvas.measure_mode = "area"
    k = cv._mk()                                       # pt por píxel
    side = PT["cm"] / k                                # 1 cm del papel, en píxeles
    for x, y in ((10, 10), (10 + side, 10), (10 + side, 10 + side), (10, 10 + side)):
        cv._mpoly_click(QPointF(x, y), Qt.KeyboardModifier.NoModifier)
    assert cv._mpoly_finish()
    monkeypatch.setattr(Scale, "paper", PT["cm"]); monkeypatch.setattr(Scale, "real", 1.0)
    monkeypatch.setattr(Scale, "unit", "m")             # 1 cm = 1 m
    txt = cv.mpoly_text()
    assert "1.00 m²" in txt and "4.00 m" in txt
    PageCanvas.measure_mode = "perim"
    assert "3.00 m" in cv.mpoly_text()                 # abierto: tres tramos
    cv._mpoly_reset(); assert cv.mpoly_text() == ""


def test_dividir_por_marcadores():
    toc = [[1, "Intro", 2], [2, "Sub", 3], [1, "Capítulo: 2/B", 5], [1, "Fuera", 99]]
    g = groups_bookmarks(toc, 8, 1)
    assert [t for t, _ in g] == ["Inicio", "Intro", "Capítulo: 2/B"]
    assert g[1][1] == [1, 2, 3] and g[2][1] == [4, 5, 6, 7]
    assert len(groups_bookmarks(toc, 8, 2)) == 4
    assert safe_filename("Capítulo: 2/B") == "Capítulo_ 2_B"


def test_texto_para_leer():
    from ui.read_aloud import page_text
    d = pymupdf.open(); p = d.new_page()
    p.insert_text((72, 72), "Primera línea\nsigue el párrafo")
    assert page_text(p) == "Primera línea sigue el párrafo"


def test_ortografia():
    from core import spell
    chk = spell.checker("es")
    if chk is None: pytest.skip("Windows no tiene el diccionario de español")
    errs = chk.errors("Esto es una prueva")
    assert errs == [(12, 6)]
    assert "prueba" in chk.suggest("prueva")
