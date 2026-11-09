# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Ayuda: fichas completas en los dos idiomas, cada ventana/panel/herramienta con su ficha, botón ? y F1, guía en PDF."""
import ast
import glob
import pymupdf
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout
from core import help as helpdoc
from ui import help_ui

FIELDS = ("title", "what", "why", "how", "example", "expert")


def test_fichas_completas():
    ids = [t["id"] for t in helpdoc.topics()]
    assert len(ids) == len(set(ids)) >= 40
    groups = {g for g, _ in helpdoc.groups("es")}
    for t in helpdoc.topics():
        assert t["group"] in groups, t["id"]
        for lg in ("es", "en"):
            c = t[lg]
            assert all(c.get(f) for f in FIELDS), (t["id"], lg)
            assert isinstance(c["how"], list) and len(c["how"]) >= 2
    for m in (help_ui.CLASS_TOPICS, help_ui.TITLE_TOPICS, help_ui.TOOL_TOPICS):
        assert all(helpdoc.topic(v) for v in m.values()), [v for v in m.values() if not helpdoc.topic(v)]


def _classes_and_titles():
    classes, titles = set(), set()
    for f in glob.glob("ui/*.py") + glob.glob("dialogs/*.py") + ["pdfgm_merge.py"]:
        tree = ast.parse(open(f, encoding="utf-8").read())
        for n in ast.walk(tree):
            if isinstance(n, ast.ClassDef) and any(getattr(b, "id", "") in ("QDialog", "QWidget", "QFrame") for b in n.bases):
                classes.add(n.name)
            if (isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "setWindowTitle" and n.args
                    and isinstance(n.args[0], ast.Call) and getattr(n.args[0].func, "id", "") == "T"
                    and isinstance(n.args[0].args[0], ast.Constant)):
                titles.add(n.args[0].args[0].value)
    return classes, titles


def test_cada_ventana_tiene_su_ayuda():
    classes, titles = _classes_and_titles()
    assert set(help_ui.CLASS_TOPICS) <= classes                       # no quedan nombres viejos
    # ventanas que no son de una función (avisos, piezas internas) no necesitan ficha
    internal = {"_PagesArea", "Viewer", "_CropArea", "SignaturePad", "PageItem", "PageList", "ElidedLabel",
                "HelpCenter", "PDFMergeWindow"}
    missing = classes - set(help_ui.CLASS_TOPICS) - internal
    assert not missing, f"Ventanas o paneles sin ficha de ayuda: {missing}"
    skip = {"Cambios sin guardar", "Buscar", "OCR", "Comparar documentos", "Centro de ayuda"}
    assert not (titles - set(help_ui.TITLE_TOPICS) - skip), titles - set(help_ui.TITLE_TOPICS) - skip


def test_buscar():
    assert helpdoc.search("contraseña", "es")[0] == "proteger"
    assert helpdoc.search("CONTRASENA", "es")[0] == "proteger"          # sin tildes ni mayúsculas
    assert "exportar" in helpdoc.search("markdown", "en")
    assert helpdoc.search("zzzz", "es") == []


def test_guia_incluye_la_referencia(tmp_path):
    from core import guide
    out = guide.build("es", str(tmp_path / "g.pdf"))
    text = "".join(p.get_text() for p in pymupdf.open(out))
    assert "Referencia de funciones" in text and "Procesar por lotes" in text and "Para usuarios avanzados" in text


def test_boton_y_f1_en_ventanas(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    dlg = QDialog(win); dlg.setWindowTitle(help_ui.T("Marca de agua"))
    QVBoxLayout(dlg).addWidget(QDialogButtonBox(QDialogButtonBox.StandardButton.Ok))
    dlg.show(); qapp.processEvents()
    box = dlg.findChild(QDialogButtonBox)
    assert box.button(QDialogButtonBox.StandardButton.Help) is not None
    QTest.keyClick(dlg, Qt.Key.Key_F1); qapp.processEvents()
    hc = win._help_center
    assert hc.isVisible() and "Marca de agua" in hc.view.toPlainText()
    hc.close(); dlg.close()
    assert help_ui.topic_for(win._dock_form) == "formularios"
    cv_tool = win._viewer.tool
    assert help_ui.TOOL_TOPICS[cv_tool]
    win.close()
