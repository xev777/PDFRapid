# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Exportar a Excel/texto/HTML, procesar por lotes, impresión avanzada, enlaces y respuestas a comentarios."""
import os
import re
import zipfile
import numpy as np
import pymupdf
import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox
from core import batch, export, imposition, pdf_tools as pt


def _tabla(path=None):
    d = pymupdf.open(); pg = d.new_page()
    heads = ["Nombre", "Código", "Total"]
    for r in range(4):
        for c in range(3):
            rect = pymupdf.Rect(72 + c * 110, 100 + r * 22, 182 + c * 110, 122 + r * 22); pg.draw_rect(rect)
            txt = heads[c] if r == 0 else ["Ana", "0123", "12,5"][c] if r == 1 else f"x{r}{c}"
            pg.insert_text((rect.x0 + 3, rect.y1 - 6), txt, fontsize=9)
    d.new_page().insert_text((72, 100), "Segunda página con ñandú", fontsize=12)
    if path: d.save(path)
    return d


def _paginas(n, rot=None):
    d = pymupdf.open()
    for i in range(n):
        p = d.new_page(); p.insert_text((72, 120), f"Pagina {i + 1}", fontsize=36)
        p.draw_rect((300, 500, 500, 700), fill=(0, 0, 0))
    if rot is not None: d[rot].set_rotation(90)
    return d


# ── exportar ───────────────────────────────────────────────────────────────
def test_excel_con_tablas(tmp_path):
    out = str(tmp_path / "t.xlsx")
    assert export.to_xlsx(_tabla(), out) == (1, "tablas")
    z = zipfile.ZipFile(out)
    assert z.testzip() is None and "xl/workbook.xml" in z.namelist()
    hoja = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "Código" in hoja and "<v>12.5</v>" in hoja                 # 12,5 → número
    assert ">0123<" in hoja                                           # código con cero inicial: texto


def test_excel_sin_tablas_usa_el_texto(tmp_path):
    d = pymupdf.open(); d.new_page().insert_text((72, 72), "Hola mundo", fontsize=12)
    out = str(tmp_path / "t.xlsx")
    assert export.to_xlsx(d, out) == (1, "texto")
    assert "Hola mundo" in zipfile.ZipFile(out).read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert export.to_xlsx(pymupdf.open(), str(tmp_path / "v.xlsx"), []) == (0, None)


def test_texto_y_html(tmp_path):
    d = _tabla()
    assert export.to_text(d, str(tmp_path / "t.txt")) > 20
    t = open(tmp_path / "t.txt", encoding="utf-8-sig").read()
    assert "ñandú" in t and "\f" in t                                  # salto de página entre páginas
    assert export.to_html(d, str(tmp_path / "t.html"), title="<x>") == 2
    import html
    h = html.unescape(open(tmp_path / "t.html", encoding="utf-8").read())
    assert "<title><x></title>" in h and 'id="p2"' in h and "ñandú" in h


# ── por lotes ──────────────────────────────────────────────────────────────
def test_lotes(tmp_path):
    src = tmp_path / "entrada"; (src / "sub").mkdir(parents=True)
    _tabla(str(src / "a.pdf")); _tabla(str(src / "sub" / "b.pdf"))
    open(src / "roto.pdf", "wb").write(b"no es un pdf")
    cifrado = _tabla(); cifrado.save(str(src / "clave.pdf"), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    antes = open(src / "a.pdf", "rb").read()
    assert len(batch.find_pdfs(str(src), False)) == 3 and len(batch.find_pdfs(str(src), True)) == 4
    out = str(tmp_path / "salida")
    files = batch.find_pdfs(str(src), True)
    res = batch.run(files, str(src), out, "watermark", {"text": "BORRADOR"})
    errores = {os.path.basename(s): e for s, _, e, _ in res if e}
    assert set(errores) == {"roto.pdf", "clave.pdf"} and errores["clave.pdf"] == "protegido con contraseña"
    assert "BORRADOR" in pymupdf.open(os.path.join(out, "sub", "b.pdf"))[0].get_text()
    assert open(src / "a.pdf", "rb").read() == antes                   # el original no cambia
    res = batch.run([str(src / "a.pdf")], str(src), out, "protect", {"password": "1234"})
    d = pymupdf.open(res[0][1]); assert d.needs_pass and d.authenticate("1234"); d.close()
    res = batch.run([str(src / "a.pdf")], str(src), out, "xlsx", {})
    assert res[0][1].endswith("a.xlsx") and res[0][3] == "1 tablas"
    for action in ("compress", "number", "flatten", "scrub", "txt"):
        assert batch.run([str(src / "a.pdf")], str(src), out, action, {})[0][2] is None
    assert batch.out_path(str(src / "a.pdf"), str(src), str(src), "compress").endswith("a_procesado.pdf")
    cancel = batch.run(files, str(src), out, "compress", {}, cancelled=lambda: True)
    assert cancel == []


# ── impresión avanzada ─────────────────────────────────────────────────────
def test_varias_por_hoja_folleto_y_poster():
    src = _paginas(6)
    d = imposition.n_up(src, list(range(6)), 4, (595, 842))
    assert len(d) == 2 and d[0].rect.width < d[0].rect.height
    assert re.findall(r"Pagina \d", d[0].get_text()) == [f"Pagina {i}" for i in range(1, 5)]
    assert imposition.n_up(src, list(range(6)), 2, (595, 842))[0].rect.width > 800    # 2 por hoja: apaisada
    assert imposition.booklet_order(6) == [(None, 0), (1, None), (5, 2), (3, 4)]
    b = imposition.booklet(src, list(range(6)), (595, 842))
    assert len(b) == 4 and b[0].rect.width > b[0].rect.height
    p, tiles = imposition.poster(src, [0], (595, 842), 2.0)
    assert tiles == len(p) and tiles >= 4


def test_pagina_girada_se_imprime_como_se_ve():
    src = _paginas(1, rot=0)
    vis = src[0].get_pixmap(dpi=36)
    a = np.frombuffer(vis.samples, np.uint8).reshape(vis.h, vis.w, 3)[..., 0] < 128
    imposition.prepare(src)
    d = imposition.n_up(src, [0], 4, (595, 842))
    one = pymupdf.open(); s = one.new_page(width=src[0].rect.width, height=src[0].rect.height)
    s.show_pdf_page(s.rect, src, 0)
    px = s.get_pixmap(dpi=36); b = np.frombuffer(px.samples, np.uint8).reshape(px.h, px.w, 3)[..., 0] < 128
    assert (a & b).sum() / (a | b).sum() > 0.95 and len(d) == 1


def test_imprimir_sin_comentarios(tmp_path):
    from ui import print_ui
    d = _paginas(2); d[0].add_text_annot((50, 50), "nota")
    sin = print_ui.compose(pymupdf.open("pdf", d.tobytes()), {"pages": [0], "annots": False, "mode": "fit"}, (595, 842))
    con = print_ui.compose(pymupdf.open("pdf", d.tobytes()), {"pages": [0], "annots": True, "mode": "fit"}, (595, 842))
    assert len(sin) == 1 and not list(sin[0].annots()) and not list(con[0].annots())   # aplanadas o quitadas
    assert len(con[0].get_drawings()) > len(sin[0].get_drawings())


# ── enlaces ────────────────────────────────────────────────────────────────
def test_enlaces_tambien_en_pagina_girada():
    d = _paginas(3, rot=1)
    pt.add_link(d, 1, (50, 50, 150, 80), "uri", "https://example.com")
    pt.add_link(d, 0, (60, 60, 160, 90), "page", 2)
    links = pt.list_links(d)
    assert [(l["page"], l["kind"], l["target"]) for l in links] == [(0, "page", 2), (1, "uri", "https://example.com")]
    assert links[1]["rect"] == pytest.approx((50, 50, 150, 80))           # donde se dibujó, aunque esté girada
    pt.update_link(d, 1, 0, "page", 0)
    assert pt.list_links(d)[1]["kind"] == "page" and pt.list_links(d)[1]["rect"] == pytest.approx((50, 50, 150, 80))
    pt.delete_link(d, 0, 0)
    assert len(pt.list_links(pymupdf.open("pdf", d.tobytes()))) == 1


def test_enlace_desde_la_interfaz(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow
    from ui.canvas import PageCanvas
    from ui import doc_tools
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    p = str(tmp_path / "e.pdf"); _paginas(3).save(p)
    win = MainWindow(); win._open_path(p); v = win._viewer
    doc_tools.add_link(win)
    PageCanvas.pick_box[0](0, (72, 72, 200, 92)); PageCanvas.pick_box = None
    assert pt.list_links(v.doc) == [{"page": 0, "index": 0, "rect": pytest.approx((72, 72, 200, 92)), "kind": "page", "target": 1}]
    assert v.canvases[0]._links                                         # el lienzo lo ve y se puede pulsar
    win._undo()
    assert pt.list_links(v.doc) == []
    v.dirty = False; win.close()


# ── respuestas y estado de comentarios ─────────────────────────────────────
def test_respuestas_se_guardan_y_acrobat_las_ve(qapp, tmp_path):
    from ui.main_window import MainWindow
    from models.annotation import Ann
    p = str(tmp_path / "c.pdf"); _paginas(1).save(p)
    win = MainWindow(); win._open_path(p); v = win._viewer; cv = v.canvases[0]
    a = Ann("comment", x1=50, y1=50, x2=78, y2=78, text="¿Cambiamos esto?", author="Ana", date="01/11/2026 10:00",
            replies=[{"author": "Luis", "date": "01/11/2026 11:00", "text": "Sí, de acuerdo"}], status="accepted")
    cv.anns.append(a); cv._commit()
    assert "↳ Luis: Sí, de acuerdo" in a.thread_text()
    out = str(tmp_path / "c2.pdf"); v.save(out); v.dirty = False; win.close()
    d = pymupdf.open(out)
    irt = [x for x in d[0].annots() if d.xref_get_key(x.xref, "IRT")[0] == "xref"]
    assert sorted(x.info["content"] for x in irt) == ["Accepted", "Sí, de acuerdo"]
    assert any(d.xref_get_key(x.xref, "State")[1] == "Accepted" for x in irt)
    w2 = MainWindow(); w2._open_path(out)
    b = w2._viewer.canvases[0].anns
    assert len(b) == 1 and b[0].replies[0]["text"] == "Sí, de acuerdo" and b[0].status == "accepted"
    w2._viewer.dirty = False; w2.close()


def test_markdown(tmp_path):
    d = _tabla()
    p = d[0]
    p.insert_text((72, 60), "Informe de ventas", fontsize=22, fontname="hebo")
    p.insert_text((72, 230), "• uno con *asterisco*", fontsize=9)
    p.insert_text((72, 245), "• dos", fontsize=9)
    p.insert_text((72, 270), "Ver la web", fontsize=9)
    p.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(70, 260, 130, 274), "uri": "https://example.com"})
    d.reload_page(p)                                     # la página en caché no ve el enlace nuevo
    out = tmp_path / "v.md"
    assert export.to_markdown(d, str(out)) > 0
    md = out.read_text(encoding="utf-8")
    assert md.startswith("# Informe de ventas")
    assert "| Nombre | Código | Total |\n|---|---|---|\n| Ana | 0123 | 12,5 |" in md
    assert "- uno con \\*asterisco\\*\n- dos" in md
    assert "[Ver la web](https://example.com)" in md
    assert "\n---\n\n## Segunda página con ñandú" in md     # letra más grande que la del resto: título
    assert md.count("Nombre") == 1                       # el texto de la tabla no se repite como párrafo


def test_filtrar_y_resumir_comentarios(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow
    from models.annotation import Ann
    from core import comment_summary
    p = str(tmp_path / "r.pdf"); _paginas(2).save(p)
    win = MainWindow(); win._open_path(p); v = win._viewer
    c0, c1 = v.canvases
    c0.anns += [Ann("comment", x1=10, y1=10, x2=30, y2=30, text="Revisar la cifra", author="Ana", date="1/11", status="accepted",
                    replies=[{"author": "Luis", "date": "2/11", "text": "Hecho"}]),
                Ann("rect", x1=50, y1=50, x2=90, y2=90, author="Ana")]
    c1.anns += [Ann("comment", x1=10, y1=10, x2=30, y2=30, text="Falta firma", author="Luis", date="3/11")]
    panel = win._comments; panel.set_viewer(v)
    assert panel.lst.count() == 3 and panel.f_author.count() == 3          # «cualquier autor» + Ana + Luis
    panel.f_kind.setCurrentIndex(panel.f_kind.findData("comment"))
    assert panel.lst.count() == 2
    panel.f_author.setCurrentIndex(panel.f_author.findData("Luis"))
    assert [a.text for _, a in panel.visible()] == ["Falta firma"]
    panel.f_author.setCurrentIndex(0); panel.f_status.setCurrentIndex(panel.f_status.findData("accepted"))
    assert len(panel.visible()) == 1
    panel.f_status.setCurrentIndex(0); panel.f_text.setText("hecho")                 # busca también en las respuestas
    assert [a.text for _, a in panel.visible()] == ["Revisar la cifra"]
    panel.f_text.clear(); panel.f_kind.setCurrentIndex(0)
    out = str(tmp_path / "resumen.pdf")
    items = [dict(panel._describe(a), page=pno) for pno, a in panel.visible()]
    thumbs = v.export_copy()
    assert comment_summary.build(items, out, "r.pdf", "08/11/2026", "es", thumbs) == 3
    thumbs.close()
    d = pymupdf.open(out); text = "".join(pg.get_text() for pg in d).replace("ﬁ", "fi")   # ligadura «ﬁ»
    assert "Resumen de comentarios" in text and "Página 2" in text and "Falta firma" in text and "Hecho" in text
    assert "Aceptado" in text and d[0].get_images()                                 # estado y miniatura de la página
    d.close()
    v.dirty = False; win.close()


def test_recuerda_pagina_y_zoom(qapp, tmp_path):
    from ui.main_window import MainWindow
    p = str(tmp_path / "largo.pdf"); _paginas(6).save(p)
    win = MainWindow(); win._open_path(p); v = win._viewer
    v.zoom_to(2.25); v.go_to(4); v._update_visible(); v.current = 4
    win.close()
    w2 = MainWindow(); w2._open_path(p); qapp.processEvents()
    assert abs(w2._viewer.zoom - 2.25) < 1e-6
    assert w2._settings.get_position(p)[0] == 4
    w2.close()
