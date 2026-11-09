# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Guías desde la regla, borrado y ajuste magnético a guías y objetos."""
import pytest
from PyQt6.QtCore import Qt, QPoint, QPointF, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication
from models.annotation import Ann

L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
NOMOD, ALT = Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.AltModifier


@pytest.fixture
def win(qapp, pdf_path, monkeypatch):
    from ui.main_window import MainWindow
    from ui.canvas import PageCanvas
    for k in ("guides_visible", "snap_guides", "snap_objects"): monkeypatch.setattr(PageCanvas, k, True)
    w = MainWindow(); w.resize(1200, 900); w.show()
    monkeypatch.setattr(w._settings, "set_bool", lambda *a: None)
    w._open_path(pdf_path); qapp.processEvents()
    return w


def _ev(cv, t, x, y, btns=L, mods=NOMOD):
    p = QPointF(x, y)
    QApplication.sendEvent(cv, QMouseEvent(t, p, cv.mapToGlobal(p), L if t != QEvent.Type.MouseMove else NB, btns, mods))


def _drag(cv, a, b, mods=NOMOD):
    _ev(cv, QEvent.Type.MouseButtonPress, *a, mods=mods)
    _ev(cv, QEvent.Type.MouseMove, *b, mods=mods)
    _ev(cv, QEvent.Type.MouseButtonRelease, *b, btns=NB, mods=mods)


def test_crear_guia_desde_la_regla(win, qapp):
    v = win._viewer; cv = v.canvases[0]; k = cv._gk()
    v.ruler_drag("h", cv.mapToGlobal(QPoint(50, 120)))
    assert cv._guide_preview and cv.guides["h"] == []
    v.ruler_drag("h", cv.mapToGlobal(QPoint(50, 120)), done=True)
    assert cv.guides["h"] == [pytest.approx(120 / k)] and cv._guide_preview is None
    v.zoom_to(v.zoom * 2); qapp.processEvents()               # en puntos PDF: sigue en el mismo sitio de la página
    assert v.canvases[0].guides["h"][0] * v.canvases[0]._gk() == pytest.approx(240, abs=1)
    cv.grab()


def test_dibujar_se_ajusta_a_la_guia(win):
    v = win._viewer; cv = v.canvases[0]; k = cv._gk()
    cv.add_guide("v", 100 / k)
    v.set_tool("rect"); _drag(cv, (104, 60), (200, 150))
    a = cv.anns[-1]
    assert min(a.x1, a.x2) == pytest.approx(100)
    v.set_tool("rect"); _drag(cv, (104, 260), (200, 350), mods=ALT)   # Alt: sin ajuste
    assert min(cv.anns[-1].x1, cv.anns[-1].x2) == pytest.approx(104)


def test_mover_se_ajusta_a_otro_objeto(win):
    v = win._viewer; cv = v.canvases[0]
    cv.anns += [Ann("rect", x1=50, y1=50, x2=150, y2=100), Ann("rect", x1=300, y1=300, x2=360, y2=340)]
    v.set_tool("select")
    _drag(cv, (330, 320), (330 - 147, 320 - 77))        # borde izquierdo a 153 → se pega al derecho del otro (150)
    b = cv.anns[-1].brect()
    assert b.left() == pytest.approx(150) and cv._snap_lines == [] and cv._mv0 is None


def test_sin_ajuste_si_esta_desactivado(win):
    from ui.canvas import PageCanvas
    win.set_guide_option("snap_guides", False); win.set_guide_option("snap_objects", False)
    assert not PageCanvas.snap_guides and not win._guide_acts["snap_objects"].isChecked()
    v = win._viewer; cv = v.canvases[0]; cv.add_guide("v", 100 / cv._gk())
    v.set_tool("rect"); _drag(cv, (104, 60), (200, 150))
    assert min(cv.anns[-1].x1, cv.anns[-1].x2) == pytest.approx(104)


def test_borrar_guias(win):
    v = win._viewer; cv = v.canvases[0]; k = cv._gk()
    cv.add_guide("h", 200 / k); cv.add_guide("v", 120 / k)
    v.set_tool("select")
    _drag(cv, (300, 201), (300, -40))                    # arrastrada fuera de la página: se borra
    assert cv.guides["h"] == [] and cv.guides["v"] == [pytest.approx(120 / k)]
    _drag(cv, (121, 300), (160, 300))                    # mover una guía
    assert cv.guides["v"] == [pytest.approx(160 / k)]
    v.clear_guides()
    assert cv.guides == {"v": [], "h": []}


def test_guias_se_guardan_en_el_pdf(win, qapp, tmp_path):
    v = win._viewer; cv = v.canvases[1]; k = cv._gk()
    v.ruler_drag("v", cv.mapToGlobal(QPoint(90, 50)), done=True)
    assert v.dirty                                       # una guía nueva es un cambio sin guardar
    out = str(tmp_path / "con_guias.pdf"); v.save(out)
    import pymupdf
    d = pymupdf.open(out); assert d.xref_get_key(d[1].xref, "PdfgmGuides")[0] == "xref"; d.close()   # en su página
    win._open_path(out); qapp.processEvents()
    r = win._viewer
    assert r.canvases[1].guides["v"] == [pytest.approx(90 / k)] and r.canvases[0].guides == {"v": [], "h": []}
    assert r.doc.xref_get_key(r.doc[1].xref, "PdfgmGuides")[0] in ("null", "")   # fuera del doc en memoria
    # reordenar páginas (como en «Operaciones entre PDFs») lleva las guías con su página
    d = pymupdf.open(out); d.select([1, 0]); movido = str(tmp_path / "movido.pdf"); d.save(movido); d.close()
    from core import ann_store
    d = pymupdf.open(movido); g = ann_store.read_guides(d)
    assert list(g) == [0] and g[0]["v"] == [pytest.approx(90 / k)]


def test_guias_formato_anterior(tmp_path):
    """PDF guardado con el formato del 2026-10-26 (todas las guías en el catálogo)."""
    import json
    import pymupdf
    from core import ann_store
    d = pymupdf.open(); d.new_page(); d.new_page()
    x = d.get_new_xref(); d.update_object(x, "<<>>"); d.update_stream(x, json.dumps({"1": {"v": [50.0], "h": []}}).encode())
    d.xref_set_key(d.pdf_catalog(), "PdfgmGuides", f"{x} 0 R")
    assert ann_store.read_guides(d) == {1: {"v": [50.0], "h": []}}


@pytest.mark.parametrize("rot", [0, 90])
def test_recortar_desplaza_las_guias(win, qapp, rot):
    from core import pdf_tools
    v = win._viewer
    if rot: v.rotate_pages([0], rot); qapp.processEvents()
    cv = v.canvases[0]
    cv.add_guide("v", 200.0); cv.add_guide("h", 300.0)           # en puntos de la página visible
    v.crop_pages({0: tuple(pdf_tools.crop_rect(v.doc[0], 50, 100, 0, 0))})   # quita 50 a la izq. y 100 arriba
    assert v.guides[0]["v"] == [pytest.approx(150)] and v.guides[0]["h"] == [pytest.approx(200)]
    v.undo()
    assert v.guides[0]["v"] == [pytest.approx(200)] and v.guides[0]["h"] == [pytest.approx(300)]   # deshacer las devuelve
