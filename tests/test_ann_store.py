# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import base64
import json
import pymupdf
import pytest
from core.ann_store import export, extract
from core.pdf_io import open_pdf, save_pdf

KINDS = ["highlight", "line", "arrow", "darrow", "rect", "rrect", "circle",
         "triangle", "arrow_shape", "text", "textbox", "comment"]


def _ann(kind, **kw):
    d = {"kind": kind, "x1": 100, "y1": 100, "x2": 200, "y2": 160, "stroke": "#0078d4",
         "stroke_width": 1.5, "opacity": 1.0, "text": "Hola", "font_size": 12,
         "text_color": "#000000", "rotation": 0}
    d.update(kw)
    return d


def _png():
    pm = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 20, 10), False)
    pm.clear_with(120)
    return base64.b64encode(pm.tobytes("png")).decode()


def _roundtrip(tmp_path, pages, base=None):
    p = str(tmp_path / "out.pdf")
    src = base or pymupdf.open()
    if not len(src):
        src.new_page()
    out = export(src, pages)
    save_pdf(out, p)
    out.close()
    doc = open_pdf(p)
    return p, doc, extract(doc)


@pytest.mark.parametrize("kind", KINDS + ["image"])
def test_cada_tipo_se_guarda_y_se_recupera(tmp_path, kind):
    a = _ann(kind, image_data=_png()) if kind == "image" else _ann(kind)
    p, doc, pages = _roundtrip(tmp_path, {0: [a]})
    assert pages[0][0]["kind"] == kind
    assert pages[0][0]["x1"] == 100
    assert len(list(pymupdf.open(p)[0].annots())) == 1          # nativa, visible en otros lectores
    assert len(list(doc[0].annots())) == 0                   # quitada del doc en memoria


def test_no_duplica_al_guardar_dos_veces(tmp_path):
    p, doc, pages = _roundtrip(tmp_path, {0: [_ann("rect")]})
    out = export(doc, pages)
    save_pdf(out, p)
    out.close()
    assert len(list(pymupdf.open(p)[0].annots())) == 1
    assert b" re" not in pymupdf.open(p)[0].read_contents()     # nada grabado en el contenido


def test_respeta_anotaciones_ajenas(tmp_path):
    base = pymupdf.open()
    base.new_page().add_text_annot((50, 50), "de otra persona")
    p, doc, pages = _roundtrip(tmp_path, {0: [_ann("circle")]}, base)
    assert len(list(doc[0].annots())) == 1                   # la ajena sigue
    assert len(list(pymupdf.open(p)[0].annots())) == 2


def test_imagen_grande_no_se_pierde(tmp_path):
    pm = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 400, 400), False)
    big = base64.b64encode(pm.tobytes("ppm")).decode()      # ~640 KB
    assert len(big) > 65535
    _, _, pages = _roundtrip(tmp_path, {0: [_ann("image", image_data=big)]})
    assert pages[0][0]["image_data"] == big


def test_limpia_formato_antiguo_en_keywords():
    doc = pymupdf.open()
    doc.new_page()
    doc.set_metadata({"keywords": json.dumps({"0": "[]"})})
    extract(doc)
    assert doc.metadata["keywords"] == ""


def test_imagen_y_texto_girados_se_exportan_girados(qapp):
    import base64
    from PyQt6.QtGui import QImage, QColor
    from PyQt6.QtCore import QBuffer, QIODevice
    from core import ann_store
    img = QImage(100, 50, QImage.Format.Format_ARGB32); img.fill(QColor("#2563eb"))
    buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly); img.save(buf, "PNG")
    d = pymupdf.open(); d.new_page()
    anns = [dict(kind="image", x1=100, y1=100, x2=300, y2=200, rotation=30, image_data=base64.b64encode(bytes(buf.data())).decode()),
            dict(kind="text", x1=100, y1=400, x2=300, y2=430, rotation=45, text="Hola", font_size=14, text_color="#000000")]
    out = ann_store.export(d, {0: anns})
    page = out[0]                                                       # la página debe seguir viva
    a = list(page.annots())
    assert [x.type[1] for x in a] == ["Stamp", "Stamp"]                  # el texto girado va como imagen
    assert a[0].rect.width > 200 and a[0].rect.height > 100              # caja de la imagen girada (más grande)
    back = ann_store.extract(out)[0]
    assert [x["rotation"] for x in back] == [30, 45] and back[1]["text"] == "Hola"   # en PDFRapid sigue editable


def test_borde_de_caja_de_texto_con_su_color():
    from core import ann_store
    d = pymupdf.open(); d.new_page()
    box = dict(kind="textbox", x1=72, y1=72, x2=300, y2=130, text="Caja", font_size=12, text_color="#0000ff",
               box_bg="#ffff99", box_bw=3, box_border="#ff0000")
    out = ann_store.export(d, {0: [box]})
    page = out[0]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(4, 4), clip=pymupdf.Rect(72, 72, 300, 130))
    assert pix.pixel(2, 120)[0] > 200 and pix.pixel(2, 120)[2] < 80          # borde rojo (no el azul del texto)
    back = ann_store.extract(out)                                             # al reabrir: un solo objeto, sin duplicar
    assert len(back[0]) == 1 and back[0][0]["box_border"] == "#ff0000" and not list(page.annots())
