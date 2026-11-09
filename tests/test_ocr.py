# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import pymupdf
import pytest

pytest.importorskip("rapidocr")
from core import ocr  # noqa: E402


def _escaneado(rot=0):
    """PDF de una página que solo contiene una imagen con texto (como un escaneo)."""
    src = pymupdf.open()
    src.new_page().insert_text((72, 100), "Información del año", fontsize=16)
    png = src[0].get_pixmap(dpi=150).tobytes("png")
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_image(pg.rect, stream=png)
    pg.set_rotation(rot)
    return doc


@pytest.mark.parametrize("rot", [0, 90])
def test_pdf_buscable_con_capa_de_texto(rot):
    doc = _escaneado(rot)
    assert doc[0].get_text().strip() == ""
    lines = ocr.ocr_page(doc[0])
    assert any("Información" in t for _, t in lines)
    out = pymupdf.open(stream=ocr.searchable_pdf(doc, {0: lines}), filetype="pdf")
    page = out[0]
    hits = page.search_for("Información")
    assert hits
    esperado = next(r for r, t in lines if "Información" in t)   # posición visible
    assert (hits[0] * page.rotation_matrix).intersects(esperado)   # search_for usa coords sin rotar


def test_worker_devuelve_texto_y_pdf(qapp):
    from ui.ocr_panel import OcrWorker
    w = OcrWorker(_escaneado().tobytes(), [0])
    got = []
    w.finished.connect(lambda t, pdf: got.append((t, pdf)))
    w.run()                                   # síncrono, sin hilo
    txt, pdf = got[0]
    assert "Información" in txt and pdf.startswith(b"%PDF")
