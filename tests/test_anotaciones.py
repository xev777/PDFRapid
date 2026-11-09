# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import pymupdf
import pytest
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtTest import QTest
from models.annotation import Ann


@pytest.fixture
def win(qapp, pdf_path):
    from ui.main_window import MainWindow
    w = MainWindow()
    w._open_path(pdf_path)
    return w


def _add(cv, kind="rect", **kw):
    cv._snap()
    a = Ann(kind, x1=50, y1=60, x2=150, y2=120, **kw)
    cv.anns.append(a)
    cv._commit()
    return a


def _drag(cv, p1, p2):
    QTest.mousePress(cv, Qt.MouseButton.LeftButton, pos=QPoint(*p1))
    QTest.mouseMove(cv, QPoint(*p2))
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, pos=QPoint(*p2))


def test_deshacer_tras_dibujar_y_seleccionar_con_el_raton(win):
    cv = win._viewer.canvases[0]
    win._tool_changed("rect")
    _drag(cv, (40, 40), (140, 120))
    assert len(cv.anns) == 1
    win._tool_changed("select")
    QTest.mouseClick(cv, Qt.MouseButton.LeftButton, pos=QPoint(90, 80))   # solo selecciona
    QTest.mouseClick(cv, Qt.MouseButton.LeftButton, pos=QPoint(300, 300))  # deselecciona
    win._undo()
    assert cv.anns == []
    win._redo()
    assert len(cv.anns) == 1


def test_deshace_en_orden_entre_paginas(win):
    c0, c1 = win._viewer.canvases[:2]
    _add(c1)
    _add(c0)
    win._undo()
    assert c0.anns == [] and len(c1.anns) == 1
    win._undo()
    assert c1.anns == []


def test_deshacer_rotacion(win):
    win._rotate_pages_sig([0], 90)
    assert win._viewer.doc[0].rotation == 90
    win._undo()
    assert win._viewer.doc[0].rotation == 0


def test_deshacer_edicion_de_texto_del_pdf(win):
    v = win._viewer
    cv = v.canvases[0]
    cv.sig_before_doc_edit.emit(0)
    v.doc[0].insert_text((72, 200), "NUEVO")
    assert "NUEVO" in v.doc[0].get_text()
    win._undo()
    assert "NUEVO" not in v.doc[0].get_text()
    assert cv.doc is v.doc


def test_guardar_y_reabrir_sin_duplicar(win, pdf_path):
    cv = win._viewer.canvases[0]
    a = _add(cv, "rect", stroke="#ff0000")
    _add(cv, "text", text="Hola")
    assert win.save_pdf() and win.save_pdf()                 # dos veces
    assert len(list(pymupdf.open(pdf_path)[0].annots())) == 2   # nativas, sin duplicar
    win._viewer.zoom_to(2.0)
    win._open_path(pdf_path)
    cv = win._viewer.canvases[0]
    assert sorted(x.kind for x in cv.anns) == ["rect", "text"]
    r = next(x for x in cv.anns if x.kind == "rect")
    assert r.stroke == "#ff0000"
    assert abs(r.x1 - a.x1) < 0.01 and abs(r.y2 - a.y2) < 0.01
    assert list(win._viewer.doc[0].annots()) == []           # no se dibujan dos veces


def test_rotar_conserva_posicion_de_objetos(win, pdf_path):
    cv = win._viewer.canvases[0]
    _add(cv)
    before = cv.anns_to_page()[0]
    win._rotate_pages_sig([0], 90)
    after = cv.anns_to_page()[0]
    assert abs(before["x1"] - after["x1"]) < 0.01 and abs(before["y1"] - after["y1"]) < 0.01
    assert win.save_pdf()
    saved = pymupdf.open(pdf_path)
    page = saved[0]
    annot = next(page.annots())
    assert annot.rect.x0 == pytest.approx(min(before["x1"], before["x2"]), abs=2)


def test_anotaciones_ajenas_se_conservan(qapp, tmp_path):
    from ui.main_window import MainWindow
    p = str(tmp_path / "ajeno.pdf")
    d = pymupdf.open()
    d.new_page().add_text_annot((50, 50), "de otra persona")
    d.save(p)
    w = MainWindow()
    w._open_path(p)
    _add(w._viewer.canvases[0])
    assert w.save_pdf()
    assert len(list(pymupdf.open(p)[0].annots())) == 2
