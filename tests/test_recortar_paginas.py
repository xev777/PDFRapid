# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Recortar páginas: cálculo de la caja, márgenes en blanco, objetos que siguen al contenido y deshacer."""
import pymupdf
import pytest
from core import pdf_tools
from models.annotation import Ann


def _doc(rot=0):
    d = pymupdf.open(); pg = d.new_page(width=600, height=800)
    pg.insert_text((100, 150), "Contenido", fontsize=20); pg.draw_rect(pymupdf.Rect(100, 600, 300, 700), color=(0, 0, 0))
    pg.set_rotation(rot)
    return d


def test_caja_de_recorte():
    pg = _doc()[0]
    r = pdf_tools.crop_rect(pg, 50, 20, 100, 30)
    assert r == pymupdf.Rect(50, 20, 500, 770)
    pg.set_cropbox(r)                                   # recortar otra vez: relativo al recorte actual
    assert pdf_tools.crop_rect(pg, 10, 10, 0, 0) == pymupdf.Rect(60, 30, 500, 770)
    with pytest.raises(ValueError): pdf_tools.crop_rect(pg, 300, 0, 300, 0)


def test_caja_de_recorte_pagina_girada():
    pg = _doc(90)[0]                                    # se ve apaisada: 800 × 600
    assert (pg.rect.width, pg.rect.height) == (800, 600)
    r = pdf_tools.crop_rect(pg, 0, 100, 0, 0)          # quitar 100 pt arriba de lo que se ve
    pg.set_cropbox(r)
    assert (pg.rect.width, pg.rect.height) == (800, 500)


def test_margenes_en_blanco():
    pg = _doc()[0]
    l, t, r, b = pdf_tools.content_margins(pg, pad=0)
    assert 80 < l < 105 and 120 < t < 140 and 280 < r < 310 and 90 < b < 110


def test_recortar_en_el_visor(qapp, tmp_path):
    from ui.main_window import MainWindow
    p = str(tmp_path / "c.pdf"); _doc().save(p)
    w = MainWindow(); w.show(); w._open_path(p); qapp.processEvents()
    v = w._viewer; cv = v.canvases[0]; z = cv._gk()
    cv.anns.append(Ann("rect", x1=100 * z, y1=600 * z, x2=300 * z, y2=700 * z))     # sobre el rectángulo dibujado
    v.crop_pages({0: tuple(pdf_tools.crop_rect(v.doc[0], 50, 100, 0, 0))})
    a = v.canvases[0].anns[0]; z = v.canvases[0]._gk()
    assert (a.x1 / z, a.y1 / z) == (pytest.approx(50), pytest.approx(500))           # sigue sobre el contenido
    assert v.doc[0].rect.height == 700 and v.dirty
    v.undo()
    assert v.doc[0].rect.height == 800 and a.y1 / v.canvases[0]._gk() == pytest.approx(600)
    out = str(tmp_path / "rec.pdf"); v.redo(); v.save(out)
    assert pymupdf.open(out)[0].cropbox == pymupdf.Rect(50, 100, 600, 800)


def test_dialogo(qapp, tmp_path):
    from ui.main_window import MainWindow
    from ui.doc_tools import PageCropDialog
    p = str(tmp_path / "c.pdf"); d = _doc(); d.new_page(); d.save(p)
    w = MainWindow(); w.show(); w._open_path(p); qapp.processEvents()
    dlg = PageCropDialog(w, w._viewer)
    dlg._auto(); assert all(m >= 0 for m in dlg.margins()) and dlg.margins()[0] > 50
    dlg.cb_pages.setCurrentIndex(1); assert dlg.target_pages() == [0, 1]
    dlg.cb_pages.setCurrentIndex(2); dlg.ed_range.setText("2"); assert dlg.target_pages() == [1]
