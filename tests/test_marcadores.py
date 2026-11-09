# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Panel de marcadores editable: añadir, renombrar, niveles, eliminar, deshacer y guardar."""
import pymupdf
import pytest


@pytest.fixture
def win(qapp, tmp_path):
    from ui.main_window import MainWindow
    p = str(tmp_path / "libro.pdf"); d = pymupdf.open()
    for i in range(5): d.new_page().insert_text((72, 72), f"Capitulo {i + 1}")
    d.set_toc([[1, "Uno", 1], [2, "Uno.a", 2], [1, "Dos", 3]]); d.save(p); d.close()
    w = MainWindow(); w.show(); w._open_path(p); qapp.processEvents()
    return w


def _simple(w): return [r[:3] for r in w._viewer.doc.get_toc(simple=False)]


def test_carga_y_edicion(win, qapp, tmp_path):
    bm, v = win._toc, win._viewer
    assert win._dock_toc.isVisible() and bm.tree.topLevelItemCount() == 2 and bm.editable()
    # añadir después de «Dos», en la página actual (4), con el texto seleccionado como título
    v.go_to(3); v.current = 3
    v.canvases[3]._tsel_text = "  Capitulo   4 "
    bm.tree.setCurrentItem(bm.tree.topLevelItem(1)); bm.add()
    assert _simple(win) == [[1, "Uno", 1], [2, "Uno.a", 2], [1, "Dos", 3], [1, "Capitulo 4", 4]]
    # renombrar
    it = bm.tree.topLevelItem(2); it.setText(0, "Cuatro")
    assert _simple(win)[3] == [1, "Cuatro", 4]
    # bajar de nivel (hijo de «Dos») y volver a subir
    bm.tree.setCurrentItem(it); bm.indent()
    assert _simple(win)[3] == [2, "Cuatro", 4]
    bm.outdent(); assert _simple(win)[3] == [1, "Cuatro", 4]
    # eliminar «Uno» (con su hijo)
    bm.tree.setCurrentItem(bm.tree.topLevelItem(0)); bm.delete()
    assert _simple(win) == [[1, "Dos", 3], [1, "Cuatro", 4]] and v.dirty
    # deshacer recupera «Uno» y el panel se actualiza
    v.undo(); qapp.processEvents()
    assert [r[1] for r in _simple(win)][:2] == ["Uno", "Uno.a"] and bm.tree.topLevelItem(0).text(0) == "Uno"
    # guardar y reabrir conserva los marcadores
    out = str(tmp_path / "editado.pdf"); v.save(out)
    d = pymupdf.open(out); assert [r[1] for r in d.get_toc()] == ["Uno", "Uno.a", "Dos", "Cuatro"]; d.close()


def test_documento_sin_marcadores(qapp, pdf_path):
    from ui.main_window import MainWindow
    w = MainWindow(); w.show(); w._open_path(pdf_path); qapp.processEvents()
    bm = w._toc
    assert bm.tree.topLevelItemCount() == 0 and not bm.empty.isHidden()
    bm.add()
    assert w._viewer.doc.get_toc() == [[1, "Página 1", 1]] and bm.empty.isHidden()
