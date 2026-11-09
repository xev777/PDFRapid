# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Fondo de página y encabezado/pie con texto libre."""
import pymupdf
from core import pdf_tools


def test_fondo_color_detras_del_contenido():
    d = pymupdf.open(); p = d.new_page(); p.insert_text((72, 72), "Hola")
    pdf_tools.background(d, [0], color="#ff0000")
    pix = d[0].get_pixmap(dpi=20)
    assert pix.pixel(2, 2)[:3] == (255, 0, 0)
    assert "Hola" in d[0].get_text()


def test_encabezado_con_fecha_y_nombre():
    d = pymupdf.open(); d.new_page(); d.new_page()
    pdf_tools.number_pages(d, [0, 1], "{name} {date} {n}/{total}", "tc", date="08/11/2026", name="informe")
    assert "informe 08/11/2026 2/2" in d[1].get_text()
