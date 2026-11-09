# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Crear, editar, mover, borrar y vaciar campos de formulario."""
import numpy as np
import pymupdf
import pytest
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QDialog, QMessageBox
from core import pdf_tools as pt


@pytest.fixture
def doc():
    d = pymupdf.open(); d.new_page(); d.new_page().set_rotation(90)
    yield d
    d.close()


def _valores(d):
    return [(f["name"], f["value"]) for f in pt.form_fields(d)]


def test_crear_todos_los_tipos(doc):
    a = pt.add_field(doc, 0, (50, 50, 210, 70), "text", {"name": "nombre", "tooltip": "Tu nombre", "required": True,
                                                         "value": "N/A", "fontsize": 11})
    pt.add_field(doc, 0, (50, 100, 64, 114), "check", {"name": "acepto"})
    pt.add_field(doc, 0, (50, 150, 210, 170), "combo", {"name": "país", "choices": ["Ecuador", "Perú"]})
    pt.add_field(doc, 0, (50, 200, 210, 260), "list", {"name": "lista", "choices": ["a", "b"]})
    m = pt.add_field(doc, 1, (100, 100, 300, 160), "multiline", {"name": "nota", "readonly": True})
    d = pymupdf.open("pdf", doc.tobytes())                                    # sobrevive a guardar y abrir
    assert [f["kind"] for f in pt.form_fields(d)] == ["text", "check", "combo", "combo", "text"]
    p = pt.field_props(d, 0, a)
    assert (p["name"], p["tooltip"], p["required"], p["readonly"], p["value"], p["fontsize"]) == \
           ("nombre", "Tu nombre", True, False, "N/A", 11)
    assert pt.field_props(d, 1, m)["kind"] == "multiline" and pt.field_props(d, 1, m)["readonly"]
    assert pt.field_props(d, 0, [w.xref for w in d[0].widgets()][2])["choices"] == ["Ecuador", "Perú"]
    assert pt.unique_name(d, "nombre") == "nombre1" and pt.clean_name("a.b(c)") == "abc"


def test_pagina_girada_queda_donde_se_dibujo(doc):
    """El recuadro se da en la página tal como se ve; en una página girada el campo aparece ahí."""
    x = pt.add_field(doc, 1, (100, 100, 300, 160), "text", {"name": "t"})
    pix = doc[1].get_pixmap()
    g = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[..., 0]
    ys, xs = np.where(g < 200)
    assert (xs.min(), ys.min(), xs.max(), ys.max()) == pytest.approx((100, 100, 299, 159), abs=2)
    assert pt.field_props(doc, 1, x)["rect"] == pytest.approx((100, 100, 300, 160), abs=0.5)


def test_grupo_de_botones_de_opcion(doc):
    r = [pt.add_field(doc, 0, (50, 50 + 30 * i, 64, 64 + 30 * i), "radio", {"name": "color"}) for i in range(3)]
    assert pt.radio_groups(doc) == ["color"]
    pt.set_field(doc, 0, r[1], True); pt.set_field(doc, 0, r[2], True)       # solo uno elegido
    assert [doc[0].load_widget(x).field_value == "Off" for x in r] == [True, True, False]
    pt.update_field(doc, 0, r[0], {"name": "colores", "required": True})       # el nombre es del grupo
    assert pt.radio_groups(doc) == ["colores"] and pt.field_props(doc, 0, r[2])["required"]
    pt.delete_field(doc, 0, r[0])
    d = pymupdf.open("pdf", doc.tobytes())
    assert [f["name"] for f in pt.form_fields(d)] == ["colores", "colores"]
    for x in [w.xref for w in d[0].widgets()]: pt.delete_field(d, 0, x)
    assert not pt.form_fields(d) and pt._fields_array(d)[2] == []              # sin grupo huérfano


def test_mover_y_vaciar(doc):
    a = pt.add_field(doc, 0, (50, 50, 210, 70), "text", {"name": "a", "value": "inicial"})
    b = pt.add_field(doc, 0, (50, 100, 64, 114), "check", {"name": "b"})
    r = [pt.add_field(doc, 0, (50, 150 + 30 * i, 64, 164 + 30 * i), "radio", {"name": "g"}) for i in range(2)]
    c = pt.add_field(doc, 0, (50, 250, 210, 270), "text", {"name": "c"})
    pt.update_field(doc, 0, c, {}, (300, 300, 400, 330))
    assert pt.field_props(doc, 0, c)["rect"] == pytest.approx((300, 300, 400, 330))
    for x, v in ((a, "otro"), (b, True), (r[1], True), (c, "algo")): pt.set_field(doc, 0, x, v)
    assert pt.reset_form(doc) == 4
    assert _valores(doc) == [("a", "inicial"), ("b", False), ("g", False), ("g", False), ("c", "")]
    assert pt.reset_form(doc) == 0


def test_desde_la_interfaz(qapp, tmp_path, monkeypatch):
    """Documento → Formulario → Añadir: recuadro en la página, propiedades, deshacer; vaciar y eliminar."""
    from ui.main_window import MainWindow
    from ui.canvas import PageCanvas
    from ui import doc_tools
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    p = str(tmp_path / "vacio.pdf"); d = pymupdf.open(); d.new_page(); d.save(p)
    win = MainWindow(); win._open_path(p)
    v = win._viewer
    assert win._form_panel.count == 0 and win._form_panel.bt_add.isEnabled()
    doc_tools.add_form_field(win, "text")
    assert PageCanvas.pick_label == "Texto"
    PageCanvas.pick_box[0](0, (72, 72, 232, 92)); PageCanvas.pick_box = None
    assert win._form_panel.count == 1 and v.dirty and PageCanvas.pick_label is None
    f = pt.form_fields(v.doc)[0]
    assert f["name"] == "Texto1"
    v.edit_form(0, f["xref"], "hola")
    doc_tools.reset_form_dialog(win)
    assert pt.form_fields(v.doc)[0]["value"] == ""
    win._form_panel.delete(pt.form_fields(v.doc)[0])
    assert win._form_panel.count == 0
    win._undo(); win._undo(); win._undo(); win._undo()                          # eliminar, vaciar, rellenar, crear
    assert pt.form_fields(v.doc) == [] and win._form_panel.count == 0
    win._redo()
    assert win._form_panel.count == 1
    v.dirty = False; win.close()


def test_anadir_campo_desde_el_menu(qapp, tmp_path):
    """El menú pasa «checked» (False) a su función: no debe confundirse con el tipo de campo."""
    from ui.main_window import MainWindow
    from ui.canvas import PageCanvas
    from core.i18n import T, Tf
    p = str(tmp_path / "m.pdf"); d = pymupdf.open(); d.new_page(); d.save(p)
    win = MainWindow(); win._open_path(p)
    acts = [a for a in win.findChildren(QAction) if a.text() == Tf("Añadir: {0}", T("Casilla"))]
    assert acts
    acts[0].trigger()
    assert PageCanvas.pick_box is not None
    PageCanvas.pick_box = None; PageCanvas.pick_label = None
    win._viewer.dirty = False; win.close()
