# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Diseño de página: continua, dos páginas y dos páginas con portada."""
import pymupdf
import pytest


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow
    from ui.viewer import _PagesArea
    monkeypatch.setattr(_PagesArea, "mode", "continuous")          # se restaura al terminar
    p = str(tmp_path / "libro.pdf"); d = pymupdf.open()
    for i in range(5): d.new_page(width=400, height=560)
    d.save(p); d.close()
    w = MainWindow(); w.resize(1200, 800); w.show()
    monkeypatch.setattr(w._settings, "set_str", lambda *a: None)
    w._open_path(p); qapp.processEvents()
    return w


def test_dos_paginas(win, qapp):
    v = win._viewer; c = v.canvases
    win.set_page_layout("two"); qapp.processEvents()
    assert c[0].y() == c[1].y() and c[1].x() > c[0].x() + c[0].width() and c[2].y() > c[0].y()
    assert win._layout_acts["two"].isChecked()
    v.fit("width"); qapp.processEvents()                            # dos páginas caben a lo ancho
    assert c[0].width() * 2 <= v.scroll.viewport().width()
    v.go_to(3); v._update_visible(); assert v.current in (2, 3)


def test_portada_y_vuelta_a_continua(win, qapp):
    v = win._viewer; c = v.canvases
    win.set_page_layout("cover"); qapp.processEvents()
    assert c[0].y() < c[1].y() == c[2].y() and c[3].y() == c[4].y()
    c[1].grab()                                                     # se dibuja sin errores
    win.set_page_layout("continuous"); qapp.processEvents()
    assert c[0].y() < c[1].y() < c[2].y() and c[0].x() == c[1].x()
