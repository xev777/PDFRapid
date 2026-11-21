# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Ventana de impresión con vista previa: colocación, opciones y salida."""
import pymupdf
import pytest
from ui import print_ui


def _doc():
    d = pymupdf.open()
    for i in range(5):
        horiz = i == 2
        p = d.new_page(width=842 if horiz else 595, height=595 if horiz else 842)
        p.insert_text((72, 100), f"Pagina {i + 1}", fontsize=30)
    return d


def test_colocacion():
    r, rot, s = print_ui.place(500, 800, 595, 842, "fit")
    assert not rot and s == pytest.approx(500 / 595) and r.x() == pytest.approx(0)
    _, _, s = print_ui.place(500, 800, 595, 842, "shrink")
    assert s < 1
    _, _, s = print_ui.place(800, 1200, 595, 842, "shrink")
    assert s == 1                                                   # cabe: no se amplía
    _, _, s = print_ui.place(500, 800, 595, 842, "custom", 0.5)
    assert s == 0.5
    r, rot, _ = print_ui.place(595, 842, 842, 595, "fit", auto_rotate=True)
    assert rot and r.width() < r.height()                         # apaisada girada en papel vertical


def test_opciones_y_vista_previa(qapp):
    dlg = print_ui.PrintDialog(None, 5, 1, _doc())
    try:
        assert len(dlg._doc) == 5 and dlg.preview.pixmap() is not None and not dlg.preview.pixmap().isNull()
        assert "%" in dlg.lb_scale.text() and "mm" in dlg.lb_size.text()
        dlg.b_more.setChecked(True); dlg.cb_subset.setCurrentIndex(1); dlg.cb_reverse.setChecked(True)
        assert dlg.pages() == [4, 2, 0]                               # impares (1, 3, 5) en orden inverso
        dlg.cb_subset.setCurrentIndex(0); dlg.rb_cur.setChecked(True); assert dlg.pages() == [1]
        dlg.grp_kind.button(3).click()                                # folleto → doble cara por el borde corto
        assert dlg.options()["mode"] == "booklet" and dlg.options()["duplex"] == "short"
        dlg.grp_kind.button(2).click(); dlg.rb_all.setChecked(True); dlg.cb_subset.setCurrentIndex(0)
        dlg.cb_reverse.setChecked(False); dlg.refresh()
        assert len(dlg._doc) == 2                                     # 5 páginas, 4 por hoja
        dlg.slider.setValue(2); assert "2" in dlg.lb_sheet.text()
    finally:
        dlg.done(0)


def test_imprime_a_pdf_con_giro_automatico(qapp, tmp_path):
    from PyQt6.QtPrintSupport import QPrinter
    out = str(tmp_path / "salida.pdf")
    pr = QPrinter(QPrinter.PrinterMode.HighResolution)
    pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat); pr.setOutputFileName(out)
    opts = {"pages": [0, 1, 2], "annots": True, "mode": "fit", "orient": "auto", "gray": True, "copies": 1}
    doc = print_ui.compose(_doc(), opts, (595, 842))
    print_ui.configure(pr, opts, doc)
    print_ui.paint(pr, doc, opts)
    res = pymupdf.open(out)
    assert len(res) == 3 and all(p.rect.height > p.rect.width for p in res)   # papel vertical en todas
