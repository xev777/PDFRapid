# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import pymupdf
from PyQt6.QtWidgets import QMessageBox


def test_visor_guarda_sobre_el_mismo_archivo(qapp, pdf_path):
    from ui.main_window import MainWindow
    w = MainWindow()
    w._open_path(pdf_path)
    assert w._viewer.dirty is False
    w._rotate_pages_sig([0], 90)
    assert w._viewer.dirty is True
    assert w.save_pdf() is True
    assert w._viewer.dirty is False
    assert pymupdf.open(pdf_path)[0].rotation == 90


def test_sin_cambios_no_pregunta_al_cerrar(qapp, pdf_path, monkeypatch):
    from ui.main_window import MainWindow
    monkeypatch.setattr(QMessageBox, "exec", lambda self: (_ for _ in ()).throw(AssertionError("no debía preguntar")))
    w = MainWindow()
    w._open_path(pdf_path)
    assert w._confirm_discard() is True


def test_merge_guarda_sobre_el_mismo_archivo(qapp, pdf_path, monkeypatch):
    from pdfgm_merge import PDFMergeWidget
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    m = PDFMergeWidget()
    panel = m._win.panel_l
    panel.open_doc(pdf_path)
    panel.doc.delete_page(1)
    panel._mark_dirty()
    assert panel.save_doc() is True
    assert len(pymupdf.open(pdf_path)) == 1
