# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Guía de usuario (docs/guia → PDF) y su entrada en el menú Ayuda."""
import pymupdf
import pytest
from core import guide


@pytest.mark.parametrize("lang, titulo", [("es", "Guía de usuario"), ("en", "User guide")])
def test_guia_pdf(tmp_path, lang, titulo):
    p = guide.build(lang, str(tmp_path / f"g_{lang}.pdf"))
    d = pymupdf.open(p)
    texto = "".join(pg.get_text() for pg in d)
    assert len(d) >= 2 and titulo in texto and "PDF/A" in texto and "{version}" not in texto
    assert d.metadata["title"].endswith(titulo)


def test_misma_estructura_en_ambos_idiomas():
    import re
    secciones = [len(re.findall(r"<h2>", open(guide.source(l), encoding="utf-8").read())) for l in ("es", "en")]
    filas = [len(re.findall(r"<tr>", open(guide.source(l), encoding="utf-8").read())) for l in ("es", "en")]
    assert secciones[0] == secciones[1] >= 8 and filas[0] == filas[1]


def test_menu_ayuda_abre_la_guia(qapp, monkeypatch, tmp_path):
    from ui.main_window import MainWindow
    monkeypatch.setattr(guide.tempfile, "gettempdir", lambda: str(tmp_path))
    w = MainWindow(); qapp.processEvents()
    act = [a for m in w.menuBar().actions() if m.menu() for a in m.menu().actions() if a.text() == "Guía de usuario"]
    assert act
    act[0].trigger(); qapp.processEvents()
    assert w._viewer and w._viewer.path.endswith("PDFRapid-guia-es.pdf")
