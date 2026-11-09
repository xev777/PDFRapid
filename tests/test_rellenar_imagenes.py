# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Rellenar y firmar, detección de campos de formulario e imágenes que ya trae el PDF."""
import pymupdf
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QImage
from core import form_detect, page_images, pdf_tools


def _png(tmp_path, name="a.png", color="red", w=40, h=20):
    img = QImage(w, h, QImage.Format.Format_RGB32); img.fill(QColor(color))
    p = str(tmp_path / name); img.save(p); return p


@pytest.fixture
def win(qapp, tmp_path):
    from ui.main_window import MainWindow
    p = str(tmp_path / "i.pdf"); d = pymupdf.open(); pg = d.new_page()
    pg.insert_image(pymupdf.Rect(100, 100, 300, 200), filename=_png(tmp_path))
    d.save(p)
    w = MainWindow(); w._open_path(p)
    w._viewer.canvases[0].ensure_loaded()
    yield w
    w._viewer.dirty = False; w.close()


def test_simbolos_de_rellenar(win, monkeypatch):
    cv = win._viewer.canvases[0]
    pt = QPointF(200, 300)
    (chk,) = cv._fill_anns(pt, "check")
    assert chk.kind == "ink" and len(chk.points) == 3
    a, b = cv._fill_anns(pt, "cross")
    assert a.kind == b.kind == "line" and a.group and a.group == b.group
    (dot,) = cv._fill_anns(pt, "dot")
    assert dot.kind == "circle" and dot.fill
    from ui import canvas_fill
    (date,) = cv._fill_anns(pt, "date")
    assert date.kind == "text" and date.text == canvas_fill.today()
    monkeypatch.setattr(canvas_fill, "initials", lambda parent=None: "F.E.")
    (ini,) = cv._fill_anns(pt, "initials")
    assert ini.text == "F.E."
    type(cv).fill_symbol = "cross"
    try:
        n = len(cv.anns); cv._place_fill(pt)
        assert len(cv.anns) == n + 2
        cv.undo(); assert len(cv.anns) == n
    finally:
        type(cv).fill_symbol = "check"


def _form_pdf():
    d = pymupdf.open(); p = d.new_page()
    p.insert_text((72, 100), "Nombre:"); p.draw_line((130, 102), (400, 102))
    p.insert_text((72, 140), "Fecha: ____________")
    p.draw_rect(pymupdf.Rect(72, 170, 82, 180)); p.insert_text((88, 179), "Acepto las condiciones")
    p.draw_rect(pymupdf.Rect(72, 220, 400, 300)); p.insert_text((72, 215), "Observaciones")
    p.draw_line((72, 400), (500, 400))                       # separador sin etiqueta: no es campo
    return d


def test_detectar_campos():
    d = _form_pdf()
    found = form_detect.detect(d[0])
    kinds = sorted(f["kind"] for f in found)
    assert kinds == ["check", "multiline", "text", "text"], found
    labels = {f["label"] for f in found}
    assert "Nombre" in labels and "Fecha" in labels and any(l.startswith("Acepto") for l in labels)
    n = form_detect.apply(d, {0: found}, pdf_tools.add_field, pdf_tools.unique_name, pdf_tools.clean_name)
    assert n == 4 and len(list(d[0].widgets())) == 4
    assert form_detect.detect(d[0]) == []                  # lo que ya es campo no se detecta otra vez


def test_imagenes_del_pdf(tmp_path):
    d = pymupdf.open(); d.new_page(); d.new_page()
    p, p2 = d[0], d[1]                                           # new_page invalida las referencias anteriores
    src = _png(tmp_path)
    p.insert_image(pymupdf.Rect(100, 100, 300, 200), filename=src)
    p2.insert_image(pymupdf.Rect(50, 50, 150, 100), filename=src)   # mismo archivo: misma imagen del PDF
    assert page_images.image_at(p, pymupdf.Point(10, 10)) is None
    img = page_images.image_at(p, pymupdf.Point(150, 150))
    assert img and not img["rotated"] and abs(img["bbox"].width - 200) < 0.5
    assert page_images.uses(d, img["xref"]) == 2
    assert QImage.fromData(page_images.png(d, img["xref"])).width() == 40
    out = str(tmp_path / "x.jpg"); page_images.save(d, img["xref"], out)
    assert QImage(out).width() == 40
    page_images.replace(p, img["xref"], _png(tmp_path, "b.png", "blue", 10, 10))
    new = page_images.image_at(p, pymupdf.Point(150, 150))
    assert QImage.fromData(page_images.png(d, new["xref"])).width() == 10
    page_images.delete(p, new["xref"])
    assert page_images.image_at(p, pymupdf.Point(150, 150)) is None


def test_convertir_imagen_en_objeto_y_deshacer(win):
    v = win._viewer; cv = v.canvases[0]
    fn = cv._from_page()
    sx, sy = fn(200, 150)
    img = cv._doc_image_at(QPointF(sx, sy))
    assert img
    cv._img_to_object(img)
    assert cv.anns[-1].kind == "image" and cv.anns[-1].image_data
    assert page_images.image_at(v.doc[0], pymupdf.Point(200, 150)) is None
    v.undo()                                               # un solo Ctrl+Z: vuelve la imagen y se va el objeto
    cv = v.canvases[0]
    assert not any(a.kind == "image" for a in cv.anns)
    assert page_images.image_at(v.doc[0], pymupdf.Point(200, 150))
