# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Reglas alineadas al borde de la página y herramienta Medir."""
import pytest
from PyQt6.QtCore import Qt, QPoint, QPointF, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication


@pytest.fixture
def win(qapp, pdf_path):
    from ui.main_window import MainWindow
    w = MainWindow(); w.resize(1200, 900); w.show()
    w._open_path(pdf_path); qapp.processEvents()
    return w


def _origen(v):
    cv = v.ruler_page()
    return (v.hruler.mapFromGlobal(cv.mapToGlobal(QPoint(0, 0))).x(),
            v.vruler.mapFromGlobal(cv.mapToGlobal(QPoint(0, 0))).y(), cv)


@pytest.mark.parametrize("zoom", [0.5, 1.5, 3.0])
def test_regla_alineada_al_borde(win, qapp, zoom):
    v = win._viewer
    v.zoom_to(zoom); qapp.processEvents()
    v.scroll.verticalScrollBar().setValue(37); v.scroll.horizontalScrollBar().setValue(11); qapp.processEvents()
    x, y, cv = _origen(v)
    # el borde izquierdo/superior de la página, visto desde la regla, coincide con su posición en pantalla
    assert x == v.hruler.mapFromGlobal(v.scroll.viewport().mapToGlobal(cv.mapTo(v.scroll.viewport(), QPoint(0, 0)))).x()
    assert y == v.vruler.mapFromGlobal(v.scroll.viewport().mapToGlobal(cv.mapTo(v.scroll.viewport(), QPoint(0, 0)))).y()


def test_medir_media_pagina(win, qapp):
    from ui.ruler import fmt
    v = win._viewer; win._tool_changed("measure"); qapp.processEvents()
    cv = v.canvases[0]
    a, b = QPointF(10, 40), QPointF(10 + cv.width() / 2, 40)
    for t, p, btn in ((QEvent.Type.MouseButtonPress, a, Qt.MouseButton.LeftButton),
                      (QEvent.Type.MouseMove, b, Qt.MouseButton.LeftButton),
                      (QEvent.Type.MouseButtonRelease, b, Qt.MouseButton.NoButton)):
        QApplication.sendEvent(cv, QMouseEvent(t, p, cv.mapToGlobal(p), Qt.MouseButton.LeftButton, btn, Qt.KeyboardModifier.NoModifier))
    d, dx, dy, ang = cv.measure_info()
    assert abs(d - cv._prect.width / 2) < 1.5 and abs(dy) < 0.01 and abs(ang) < 0.01
    assert fmt(72, "in") == "1.00 in" and fmt(72, "mm") == "25.4 mm"
    cv.grab()                                            # pinta la etiqueta sin errores
    win._tool_changed("select"); assert cv.measure_info() is None


def test_mostrar_ocultar_reglas(win, qapp, monkeypatch):
    from ui.ruler import Ruler
    monkeypatch.setattr(win._settings, "set_rulers_shown", lambda on: None)
    antes = Ruler.shown
    win.toggle_rulers(); qapp.processEvents()
    assert win._viewer.hruler.isVisible() == (not antes)
    win.toggle_rulers(); assert Ruler.shown == antes
