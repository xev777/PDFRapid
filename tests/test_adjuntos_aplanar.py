# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Archivos adjuntos (añadir, guardar, bloqueo de ejecutables, eliminar, deshacer) y aplanar anotaciones."""
import pymupdf
import pytest
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from models.annotation import Ann


@pytest.fixture
def win(qapp, pdf_path):
    from ui.main_window import MainWindow
    w = MainWindow(); w.show(); w._open_path(pdf_path); qapp.processEvents()
    return w


def test_adjuntos(win, qapp, tmp_path, monkeypatch):
    att, v = win._attach, win._viewer
    f = tmp_path / "datos.csv"; f.write_text("a,b\n1,2\n", encoding="utf-8")
    att.add(str(f)); qapp.processEvents()
    assert v.doc.embfile_names() == ["datos.csv"] and att.list.topLevelItemCount() == 1 and v.dirty
    att.list.setCurrentItem(att.list.topLevelItem(0))
    out = tmp_path / "copia.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    att.save(); assert out.read_text(encoding="utf-8") == "a,b\n1,2\n"
    # un ejecutable adjunto no se abre, solo se puede guardar
    exe = tmp_path / "programa.exe"; exe.write_bytes(b"MZ")
    att.add(str(exe)); qapp.processEvents()
    avisos, abiertos = [], []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a[2]))
    monkeypatch.setattr("ui.attachments.QDesktopServices.openUrl", lambda u: abiertos.append(u))
    att.list.setCurrentItem(next(att.list.topLevelItem(i) for i in range(2) if att.list.topLevelItem(i).text(0) == "programa.exe"))
    att.open(); assert avisos and not abiertos
    att.list.setCurrentItem(att.list.topLevelItem(0)); att.delete(); qapp.processEvents()
    assert len(v.doc.embfile_names()) == 1
    v.undo(); qapp.processEvents()
    assert len(v.doc.embfile_names()) == 2 and att.list.topLevelItemCount() == 2       # el panel se actualiza


def test_aplanar(win, qapp, tmp_path):
    v = win._viewer; cv = v.canvases[0]
    cv.anns += [Ann("rect", x1=50, y1=50, x2=200, y2=150, stroke="#ff0000"),
                Ann("text", x1=60, y1=250, x2=60, y2=250, text="Texto aplanado"),
                Ann("redact", x1=300, y1=300, x2=400, y2=350)]
    n = v.flatten()
    assert n == 2 and [a.kind for a in cv.anns] == ["redact"]          # la zona de tachado se mantiene
    pg = v.doc[0]
    assert not list(pg.annots()) and "Texto aplanado" in pg.get_text() and pg.get_drawings()
    v.undo()
    assert sorted(a.kind for a in cv.anns) == ["rect", "redact", "text"] and "Texto aplanado" not in v.doc[0].get_text()
    v.redo()
    assert [a.kind for a in cv.anns] == ["redact"] and "Texto aplanado" in v.doc[0].get_text()
    assert v.flatten() == 0                                            # ya no queda nada que aplanar
