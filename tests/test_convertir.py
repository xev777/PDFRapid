# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Crear PDF desde Office y escanear (con conversor y escáner simulados; Word real si está instalado)."""
import os
import pymupdf
import pytest
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from core import convert
from ui import doc_tools


@pytest.fixture
def win(qapp, monkeypatch):
    from ui.main_window import MainWindow
    w = MainWindow(); w.show()
    monkeypatch.setattr(doc_tools, "run_with_progress", lambda win, t, x, fn: _run(fn))
    return w


def _run(fn):
    try: return fn(), None
    except Exception as e: return None, e


def _pdf(path, n=1):
    d = pymupdf.open()
    for _ in range(n): d.new_page()
    d.save(path); d.close()


def test_tipos():
    assert convert.kind_of("a.DOCX") == "Word" and convert.kind_of("b.csv") == "Excel"
    assert convert.kind_of("c.pptx") == "PowerPoint" and convert.kind_of("d.pdf") is None


def test_desde_office(win, tmp_path, monkeypatch):
    src, out = str(tmp_path / "informe.docx"), str(tmp_path / "informe.pdf")
    open(src, "w").close()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (src, ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    monkeypatch.setattr(convert, "available", lambda: {"Word": "LibreOffice", "Excel": None, "PowerPoint": None})
    monkeypatch.setattr(convert, "office_to_pdf", lambda s, d: (_pdf(d, 3), "LibreOffice")[1])
    doc_tools.from_office(win)
    assert win._viewer.path == out and len(win._viewer.doc) == 3


def test_desde_office_sin_conversor(win, tmp_path, monkeypatch):
    avisos = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(tmp_path / "x.xlsx"), ""))
    monkeypatch.setattr(convert, "available", lambda: {"Word": None, "Excel": None, "PowerPoint": None})
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a[2]))
    doc_tools.from_office(win)
    assert avisos and "LibreOffice" in avisos[0] and win._viewer.doc is None


def test_escanear_dos_paginas(win, tmp_path, monkeypatch):
    respuestas = iter([QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No])

    def escanear(dst):
        img = QImage(400, 560, QImage.Format.Format_RGB32); img.fill(QColor("white")); img.save(dst); return True
    monkeypatch.setattr(convert, "scan_page", escanear)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: next(respuestas))
    out = str(tmp_path / "escaneo.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    doc_tools.scan(win)
    assert win._viewer.path == out and len(win._viewer.doc) == 2 and win._dock_ocr.isVisible()


def test_escanear_sin_escaner(win, monkeypatch):
    avisos = []

    def sin(dst): raise convert.ScanError(convert.NO_SCANNER)
    monkeypatch.setattr(convert, "scan_page", sin)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a[2]))
    doc_tools.scan(win)
    assert avisos and "escáner" in avisos[0] and win._viewer.doc is None


@pytest.mark.skipif(not convert.office_installed("Word"), reason="Microsoft Word no instalado")
def test_word_real(tmp_path, monkeypatch):
    docx = pytest.importorskip("docx")
    monkeypatch.undo()                                   # la conversión real lanza Word (proceso local)
    src, out = str(tmp_path / "carta.docx"), str(tmp_path / "carta.pdf")
    d = docx.Document(); d.add_paragraph("Carta de prueba PDFRapid"); d.save(src)
    assert convert.office_to_pdf(src, out) == "Microsoft Office"
    assert "Carta de prueba" in pymupdf.open(out)[0].get_text()


def test_conversion_basica_docx(tmp_path, monkeypatch):
    """Sin Office ni LibreOffice (o si no pueden abrirlo), un .docx se convierte igual: texto y tablas."""
    docx = pytest.importorskip("docx")
    src, out = str(tmp_path / "guia.docx"), str(tmp_path / "guia.pdf")
    d = docx.Document(); d.add_heading("Guía de prueba", 1); d.add_paragraph("Párrafo con acentos: ñandú")
    t = d.add_table(rows=2, cols=2); t.cell(0, 0).text = "Celda A"; t.cell(1, 1).text = "Celda D"; d.save(src)
    monkeypatch.setattr(convert, "office_installed", lambda app: False)
    monkeypatch.setattr(convert, "find_libreoffice", lambda: None)
    assert convert.office_to_pdf(src, out) == convert.BASIC
    txt = pymupdf.open(out)[0].get_text()
    assert "Guía de prueba" in txt and "ñandú" in txt and "Celda D" in txt
    with pytest.raises(convert.ConverterMissing):           # Excel/PowerPoint sí necesitan un programa
        convert.office_to_pdf(str(tmp_path / "x.xlsx"), str(tmp_path / "x.pdf"))
