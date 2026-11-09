# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import os
import pymupdf
import pytest
from core.pdf_io import open_pdf, save_pdf


def _make_pdf(path, pages=2):
    d = pymupdf.open()
    for _ in range(pages):
        d.new_page()
    d.save(path)
    d.close()


def test_guardar_sobre_el_mismo_archivo(tmp_path):
    p = str(tmp_path / "a.pdf")
    _make_pdf(p)
    doc = open_pdf(p)
    doc.new_page()
    save_pdf(doc, p)
    assert len(pymupdf.open(p)) == 3


def test_no_bloquea_el_archivo_original(tmp_path):
    p = str(tmp_path / "a.pdf")
    _make_pdf(p)
    doc = open_pdf(p)
    os.replace(p, str(tmp_path / "b.pdf"))  # en Windows falla si queda abierto
    assert len(doc) == 2


def test_fallo_al_guardar_no_deja_temporales_ni_dana_el_original(tmp_path, monkeypatch):
    p = str(tmp_path / "a.pdf")
    _make_pdf(p)
    doc = open_pdf(p)
    doc.new_page()
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError("en uso")))
    with pytest.raises(PermissionError):
        save_pdf(doc, p)
    assert os.listdir(tmp_path) == ["a.pdf"]
    assert len(pymupdf.open(p)) == 2
