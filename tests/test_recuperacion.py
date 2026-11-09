# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Autoguardado y recuperación tras un cierre inesperado."""
import json
import os
import pytest
from PyQt6.QtWidgets import QMessageBox
from core import recovery
from models.annotation import Ann


@pytest.fixture
def win(qapp, pdf_path):
    for r in recovery.pending(): recovery.remove(r["uid"])
    from ui.main_window import MainWindow
    w = MainWindow(); w.resize(1000, 800); w.show()
    w._open_path(pdf_path); qapp.processEvents()
    return w


def _archivos(uid):
    d = recovery._dir()
    return [os.path.exists(os.path.join(d, uid + e)) for e in (".json", ".pdf")]


def _simular_cierre(uid):
    """El proceso que autoguardó ya no existe."""
    p = os.path.join(recovery._dir(), uid + ".json")
    m = json.load(open(p, encoding="utf-8")); m["pid"] = 0x7FFFFFF0
    json.dump(m, open(p, "w", encoding="utf-8"))


def test_autoguardado_y_limpieza(win, tmp_path):
    v = win._viewer
    v.autosave(); assert _archivos(v.uid) == [False, False]          # sin cambios: nada
    v.canvases[0].anns.append(Ann("rect", x1=10, y1=10, x2=80, y2=60)); v._mark_dirty()
    v.autosave(); assert _archivos(v.uid) == [True, False]           # solo objetos
    v.apply_doc_change(lambda d: d.new_page())
    v.autosave(); assert _archivos(v.uid) == [True, True]            # el PDF cambió: copia
    assert recovery.pending() == []                                  # este proceso sigue vivo
    v.save(str(tmp_path / "g.pdf")); assert _archivos(v.uid) == [False, False]


def test_recuperar_tras_cierre(win, qapp, pdf_path, monkeypatch):
    v = win._viewer
    v.canvases[1].anns.append(Ann("rect", x1=10, y1=10, x2=80, y2=60)); v._mark_dirty()
    v.apply_doc_change(lambda d: d.new_page())                       # 3 páginas
    v.autosave(); uid = v.uid
    _simular_cierre(uid)
    v.dirty = False; v.uid = "otro"                                  # como si fuera otra sesión
    assert [r["uid"] for r in recovery.pending()] == [uid]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    win._offer_recovery(); qapp.processEvents()
    r = win._viewer
    assert r is not v and len(r.doc) == 3 and r.dirty and r.path == pdf_path
    assert len(r.canvases[1].anns) == 1 and recovery.pending() == []


def test_rechazar_borra(win, monkeypatch):
    v = win._viewer
    v.canvases[0].anns.append(Ann("rect", x1=10, y1=10, x2=80, y2=60)); v._mark_dirty(); v.autosave()
    _simular_cierre(v.uid); v.dirty = False
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    win._offer_recovery()
    assert _archivos(v.uid) == [False, False]
