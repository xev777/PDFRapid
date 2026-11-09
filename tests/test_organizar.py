# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Organizar objetos: alinear, distribuir, voltear, agrupar, bloquear, ocultar, formato y posición exacta."""
import pymupdf
import pytest
from PyQt6.QtCore import QPointF, QRectF
from models.annotation import Ann
from ui.canvas_arrange import gbox, mirror, set_box, vbox


@pytest.fixture
def cv(qapp, tmp_path):
    from ui.main_window import MainWindow
    p = str(tmp_path / "o.pdf"); d = pymupdf.open(); d.new_page(); d.save(p)
    win = MainWindow(); win._open_path(p)
    c = win._viewer.canvases[0]; c.ensure_loaded()
    yield c
    win._viewer.dirty = False; win.close()


def _sel(cv, *anns):
    cv._sel_multi = list(anns); cv._sel = anns[-1]


def test_alinear_y_distribuir(cv):
    a = Ann("rect", x1=10, y1=10, x2=50, y2=30); b = Ann("rect", x1=80, y1=60, x2=100, y2=90)
    c = Ann("rect", x1=300, y1=20, x2=340, y2=40)
    cv.anns += [a, b, c]
    _sel(cv, a, b, c)
    cv._align("left")
    assert a.x1 == b.x1 == c.x1 == 10
    cv._align("bottom")
    assert a.y2 == b.y2 == c.y2 == 90
    b.move(30, 0); c.move(200, 0)             # a: 10-50, b: 40-60 (desplazada), c: 210-250
    cv._distribute(True)
    ra, rb, rc = vbox(a), vbox(b), vbox(c)
    assert abs((rb.left() - ra.right()) - (rc.left() - rb.right())) < 0.01
    cv.undo()
    a, b, c = cv.anns[-3:]
    assert vbox(b).left() == 40               # deshacer devuelve el paso completo
    _sel(cv, a)
    cv._align("hcenter")                      # un solo objeto: se centra en la página
    assert abs(vbox(a).center().x() - cv._bw / 2) < 0.01


def test_voltear():
    ln = Ann("arrow", x1=0, y1=0, x2=100, y2=40, rotation=30)
    mirror(ln, True)
    assert (ln.x1, ln.x2, ln.rotation) == (100, 0, 330)
    tri = Ann("triangle", x1=0, y1=0, x2=60, y2=60)
    mirror(tri, False)
    assert tri.y1 == 60 and tri.y2 == 0
    tri.resize(7, 10, 10)                     # sigue volteado al cambiar el tamaño
    assert tri.y1 == 70 and tri.y2 == 0 and tri.x2 == 70
    ink = Ann("ink", points=[[0, 0], [10, 20]]); ink.fit_bbox()
    mirror(ink, True)
    assert ink.points == [[10, 0], [0, 20]]
    txt = Ann("textbox", x1=0, y1=0, x2=50, y2=20, rotation=10, text="hola")
    mirror(txt, True)
    assert txt.rotation == 10                 # el texto no se voltea


def test_voltear_grupo_refleja_posiciones(cv):
    a = Ann("rect", x1=0, y1=0, x2=20, y2=20); b = Ann("rect", x1=80, y1=0, x2=100, y2=20)
    cv.anns += [a, b]; _sel(cv, a, b)
    cv._flip(True)
    assert cv.anns[0].x1 == 80 and cv.anns[1].x1 == 0


def test_agrupar_bloquear_ocultar(cv):
    a = Ann("rect", x1=10, y1=10, x2=50, y2=30); b = Ann("circle", x1=100, y1=10, x2=140, y2=50)
    cv.anns += [a, b]; _sel(cv, a, b)
    cv._group()
    assert a.group and a.group == b.group
    cv._desel(); cv._pick(a)
    assert set(map(id, cv._sel_multi)) == {id(a), id(b)}      # un clic selecciona todo el grupo
    cv._ungroup()
    assert not a.group and not b.group
    _sel(cv, a); cv._set_flag("locked")
    assert a.locked and not a.hit(QPointF(20, 20))
    cv._clear_flag("locked"); assert not a.locked and a.hit(QPointF(20, 20))
    _sel(cv, b); cv._set_flag("hidden")
    assert b.hidden and not b.hit(QPointF(120, 30))


def test_formato_y_posicion(cv):
    a = Ann("rect", x1=0, y1=0, x2=10, y2=10, stroke="#ff0000", stroke_width=4, fill="#00ff00")
    b = Ann("circle", x1=50, y1=50, x2=60, y2=60)
    cv.anns += [a, b]
    cv._copy_fmt(a); _sel(cv, b); cv._paste_fmt()
    assert (b.stroke, b.stroke_width, b.fill) == ("#ff0000", 4, "#00ff00")
    ink = Ann("ink", points=[[0, 0], [10, 10]]); ink.fit_bbox()
    set_box(ink, QRectF(100, 100, 40, 20))
    assert ink.points == [[100, 100], [140, 120]] and gbox(ink) == QRectF(100, 100, 40, 20)
    ln = Ann("line", x1=50, y1=0, x2=50, y2=30)            # línea vertical (ancho 0): solo se mueve en X
    set_box(ln, QRectF(70, 0, 5, 60))
    assert (ln.x1, ln.x2, ln.y2) == (70, 70, 60)


def test_se_guardan_y_ocultos_no_se_imprimen(qapp, tmp_path):
    from ui.main_window import MainWindow
    from core import imposition
    p = str(tmp_path / "g.pdf"); d = pymupdf.open(); d.new_page(); d.save(p)
    win = MainWindow(); win._open_path(p); v = win._viewer; c = v.canvases[0]; c.ensure_loaded()
    c._snap()
    c.anns += [Ann("rect", x1=10, y1=10, x2=50, y2=50, group="g1", locked=True, fill="#000000"),
               Ann("rect", x1=200, y1=200, x2=260, y2=260, group="g1", hidden=True, fill="#000000"),
               Ann("triangle", x1=300, y1=100, x2=360, y2=40)]               # volteado: punta abajo
    c._commit()
    out = str(tmp_path / "g2.pdf"); v.save(out); v.dirty = False; win.close()
    w2 = MainWindow(); w2._open_path(out); c2 = w2._viewer.canvases[0]; c2.ensure_loaded()
    a, b, t = c2.anns
    assert a.locked and b.hidden and a.group == b.group == "g1" and t.y1 > t.y2
    w2._viewer.dirty = False; w2.close()
    doc = pymupdf.open(out)
    info = [(x.rect, bool(x.flags & pymupdf.PDF_ANNOT_IS_HIDDEN)) for x in doc[0].annots()]
    assert [h for _, h in info] == [False, True, False]
    vc, hc = ((r.tl + r.br) / 2 for r, _ in info[:2])
    imposition.prepare(doc, True)
    pix = doc[0].get_pixmap()                 # al imprimir: el oculto queda en blanco, el visible se ve
    assert pix.pixel(int(hc.x), int(hc.y)) == (255, 255, 255)
    assert pix.pixel(int(vc.x), int(vc.y)) != (255, 255, 255)
