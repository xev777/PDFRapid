# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Guardar como PDF/A-2b. Si veraPDF está instalado (D:\\Claude\\tools\\verapdf o $VERAPDF), valida el resultado."""
import json
import os
import subprocess
import pymupdf
import pytest
from core import pdfa

VERAPDF = os.environ.get("VERAPDF", r"D:\Claude\tools\verapdf\app\verapdf.bat")


def _annots(doc):
    pg = doc.new_page(); pg.insert_text((72, 72), "Hola áéíóú ñ", fontname="tiro")
    pg.add_highlight_annot(pymupdf.Rect(72, 58, 200, 76)); pg.add_freetext_annot(pymupdf.Rect(72, 100, 300, 140), "Nota")
    pg.add_text_annot((300, 300), "comentario")


def _form(doc):
    pg = doc.new_page()
    for t, name, r, val in ((pymupdf.PDF_WIDGET_TYPE_TEXT, "nombre", (72, 72, 300, 96), "Juan"),
                            (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, "ok", (72, 120, 90, 138), True)):
        w = pymupdf.Widget(); w.field_type = t; w.field_name = name; w.rect = pymupdf.Rect(r); w.field_value = val
        pg.add_widget(w)


def _truetype(doc):                                         # Arial sin incrustar, como dejan algunos programas
    pg = doc.new_page(); pg.insert_text((1, 1), " ")
    x = doc.get_new_xref()
    doc.update_object(x, "<</Type/Font/Subtype/TrueType/BaseFont/Arial/Encoding/WinAnsiEncoding>>")
    doc.xref_set_key(pg.xref, "Resources", f"<</Font<</F1 {x} 0 R>>>>")
    doc.update_stream(pg.get_contents()[0], b"BT /F1 24 Tf 72 700 Td (Arial \xe1\xe9) Tj ET")


def _cmyk(doc):
    pg = doc.new_page(); pg.draw_rect(pymupdf.Rect(72, 72, 200, 200), color=(0, 1, 1, 0), fill=(1, 0, 0, 0))
    pg.insert_text((72, 300), "texto cmyk")


def _dangerous(doc):
    pg = doc.new_page(); pg.insert_text((72, 72), "js", fontname="symb"); pg.insert_text((72, 100), "normal")
    doc.xref_set_key(doc.pdf_catalog(), "OpenAction", "<</S/JavaScript/JS(app.alert(1))>>")
    doc.embfile_add("x.txt", b"hola"); doc.set_metadata({"title": "Título <raro> & co", "author": "Ana"})


def _cmyk_girada(doc):
    pg = doc.new_page(width=842, height=595); pg.draw_rect(pymupdf.Rect(72, 72, 200, 200), fill=(1, 0, 0, 0))
    pg.insert_text((300, 100), "girada", fontsize=20); pg.set_rotation(90)


CASES = {"anotaciones": _annots, "formulario": _form, "truetype": _truetype, "cmyk": _cmyk, "peligroso": _dangerous,
         "cmyk_girada": _cmyk_girada}


@pytest.fixture(scope="module")
def converted(tmp_path_factory):
    d = tmp_path_factory.mktemp("pdfa"); out = {}
    for name, fn in CASES.items():
        doc = pymupdf.open(); fn(doc)
        p = str(d / f"{name}_a.pdf")
        out[name] = (p, pdfa.convert(doc, p)); doc.close()
    return out


def test_informe(converted):
    assert "Arial" in converted["truetype"][1]["fuentes"]
    assert converted["cmyk"][1]["rasterizadas"] == [1]
    assert {"acción al abrir", "adjuntos"} <= set(converted["peligroso"][1]["quitado"])
    assert "ZapfDingbats" in converted["formulario"][1]["fuentes"]          # la casilla marcada


def test_resultado(converted):
    for name, (p, _) in converted.items():
        doc = pymupdf.open(p)
        assert pdfa.is_pdfa(doc) == "PDF/A-2b", name
        assert doc.embfile_count() == 0 and "/OutputIntents" in doc.xref_object(doc.pdf_catalog())
        assert not [f for pg in doc for f in pg.get_fonts() if f[1] == "n/a"], name   # todas incrustadas
        doc.close()
    t = pymupdf.open(converted["cmyk"][0])
    assert "texto cmyk" in t[0].get_text()                                    # sigue siendo buscable
    g = pymupdf.open(converted["cmyk_girada"][0])[0]                          # el texto invisible, en su sitio
    assert g.rotation == 90 and [w[4] for w in g.get_text("words")] == ["girada"]
    assert abs(g.get_text("words")[0][0] - 300) < 2
    assert pymupdf.open(converted["peligroso"][0]).metadata["title"] == "Título <raro> & co"


def test_no_toca_el_original(pdf_path, tmp_path):
    doc = pymupdf.open(pdf_path)
    objs = lambda: [doc.xref_object(x) for x in range(1, doc.xref_length())]  # tobytes() cambia el /ID cada vez
    antes = objs()
    pdfa.convert(doc, str(tmp_path / "a.pdf"))
    assert objs() == antes and not pdfa.is_pdfa(doc)


@pytest.mark.skipif(not os.path.isfile(VERAPDF), reason="veraPDF no instalado")
def test_verapdf(converted):
    r = subprocess.run([VERAPDF, "--flavour", "2b", "--format", "json", *[p for p, _ in converted.values()]],
                       capture_output=True, text=True, encoding="utf-8", timeout=600)
    fallos = {}
    for job in json.loads(r.stdout)["report"]["jobs"]:
        vr = job["validationResult"]; vr = vr[0] if isinstance(vr, list) else vr
        if not vr["compliant"]:
            fallos[os.path.basename(job["itemDetails"]["name"])] = [
                (s["clause"], s["description"][:80]) for s in vr["details"]["ruleSummaries"]]
    assert not fallos


def test_menu_guardar_pdfa(qapp, monkeypatch, pdf_path, tmp_path):
    from PyQt6.QtWidgets import QMessageBox, QFileDialog
    from ui.main_window import MainWindow
    out = str(tmp_path / "copia_PDFA.pdf")
    preguntas = []

    def question(*a, **k):                                    # «¿Continuar?» sí; «¿Abrir la copia?» no
        preguntas.append(a[2])
        return QMessageBox.StandardButton.Yes if len(preguntas) == 1 else QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "question", question)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    from models.annotation import Ann
    w = MainWindow(); w._open_path(pdf_path); qapp.processEvents()
    cv = w._viewer.canvases[0]                                # marcas de PDFRapid: deben llegar a la copia
    cv._snap(); cv.anns += [Ann("rect", x1=50, y1=50, x2=200, y2=150, stroke="#ff0000"),
                            Ann("text", x1=60, y1=250, x2=260, y2=280, text="Texto añadido", font_size=12),
                            Ann("highlight", x1=60, y1=300, x2=260, y2=320)]
    cv._commit()
    act =[a for m in w.menuBar().findChildren(type(w.menuBar().actions()[0].menu())) for a in m.actions()
           if a.text().startswith("Como PDF/A")]
    assert act
    act[0].trigger(); qapp.processEvents()
    assert os.path.isfile(out) and pdfa.is_pdfa(pymupdf.open(out)) == "PDF/A-2b"
    assert "PDF/A-2b" in preguntas[-1]
    copia = pymupdf.open(out)
    assert len(list(copia[0].annots())) >= 3
    assert any("Texto añadido" in a.info["content"] for a in copia[0].annots())
    if os.path.isfile(VERAPDF):
        r = subprocess.run([VERAPDF, "--flavour", "2b", "--format", "json", out], capture_output=True, text=True,
                           encoding="utf-8", timeout=300)
        vr = json.loads(r.stdout)["report"]["jobs"][0]["validationResult"]; vr = vr[0] if isinstance(vr, list) else vr
        assert vr["compliant"], [(s["clause"], s["description"][:80]) for s in vr["details"]["ruleSummaries"]]


@pytest.mark.parametrize("estilo", ["qr", "text"])
def test_firmar_un_pdfa_lo_mantiene(tmp_path, estilo):
    """El sello de la firma lleva su tipografía incrustada, así la copia firmada sigue siendo PDF/A."""
    pytest.importorskip("pyhanko")
    from core import signing
    from tests.test_firma import _cert, _pdf
    src = str(tmp_path / "a.pdf"); pdfa.convert(_pdf(tmp_path), src)
    out = str(tmp_path / "firmado.pdf")
    signing.sign_pdf(src, out, _cert(tmp_path), "clave123", page_no=0, pos="br", style=estilo)
    assert signing.list_signatures(out)[0]["integra"]
    d = pymupdf.open(out)
    assert pdfa.is_pdfa(d) == "PDF/A-2b"
    w = next(d[0].widgets()); ap = d.xref_get_key(w.xref, "AP/N")[1]
    assert not [f for pg in d for f in pg.get_fonts() if f[1] == "n/a"]      # todas incrustadas
    if os.path.isfile(VERAPDF):
        r = subprocess.run([VERAPDF, "--flavour", "2b", "--format", "json", out], capture_output=True, text=True,
                           encoding="utf-8", timeout=300)
        vr = json.loads(r.stdout)["report"]["jobs"][0]["validationResult"]; vr = vr[0] if isinstance(vr, list) else vr
        assert vr["compliant"], [(s["clause"], s["description"][:80]) for s in vr["details"]["ruleSummaries"]]
    assert ap
