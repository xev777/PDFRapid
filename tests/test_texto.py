# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import pymupdf
import pytest
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication


def _win(qapp, tmp_path, rot=0, permisos=None):
    from ui.main_window import MainWindow
    p = str(tmp_path / "texto.pdf")
    d = pymupdf.open()
    pg = d.new_page()
    pg.insert_text((72, 100), "Hola mundo azul", fontsize=14)
    pg.insert_text((72, 130), "segunda linea verde", fontsize=14)
    pg.set_rotation(rot)
    if permisos is None:
        d.save(p)
    else:
        d.save(p, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="dueno", permissions=permisos)
    w = MainWindow()
    w.show()
    w._open_path(p)
    w._tool_changed("txtsel")
    qapp.processEvents()
    return w, w._viewer.canvases[0]


def _centro(cv, palabra):
    w = next(x for x in cv._words if x[4] == palabra)
    return QPoint(*map(int, cv._p2s((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)))


def _arrastrar(cv, a, b):
    QTest.mousePress(cv, Qt.MouseButton.LeftButton, pos=a)
    QTest.mouseMove(cv, b)
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, pos=b)


@pytest.mark.parametrize("rot", [0, 90])
def test_seleccion_de_texto_corrido(qapp, tmp_path, rot):
    w, cv = _win(qapp, tmp_path, rot)
    _arrastrar(cv, _centro(cv, "mundo"), _centro(cv, "linea"))
    assert cv._tsel_text == "mundo azul\nsegunda linea"
    QTest.mouseMove(cv, _centro(cv, "verde"))               # ya soltado: no debe cambiar
    assert cv._tsel_text == "mundo azul\nsegunda linea"


def test_ctrl_c_copia_texto(qapp, tmp_path):
    w, cv = _win(qapp, tmp_path)
    _arrastrar(cv, _centro(cv, "Hola"), _centro(cv, "azul"))
    QTest.keyClick(cv, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "Hola mundo azul"


def test_documento_protegido_no_permite_copiar(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a))
    QApplication.clipboard().setText("antes")
    w, cv = _win(qapp, tmp_path, permisos=pymupdf.PDF_PERM_PRINT)
    _arrastrar(cv, _centro(cv, "Hola"), _centro(cv, "azul"))
    QTest.keyClick(cv, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "antes" and avisos


def test_copiar_y_pegar_objeto_y_texto(qapp, tmp_path):
    from models.annotation import Ann
    w, cv = _win(qapp, tmp_path)
    w._tool_changed("select")
    cv._snap(); a = Ann("rect", x1=10, y1=10, x2=60, y2=40); cv.anns.append(a); cv._commit()
    cv._setsel(a)
    QTest.keyClick(cv, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    cv._paste(QPointF(200, 300))
    assert len(cv.anns) == 2 and cv.anns[1].kind == "rect" and cv.anns[1].x1 == 200
    QApplication.clipboard().setText("texto externo")
    cv._paste()
    assert cv.anns[-1].kind == "text" and cv.anns[-1].text == "texto externo"
    w._undo()
    assert len(cv.anns) == 2


def test_busqueda_en_pagina_rotada(qapp, tmp_path):
    w, cv = _win(qapp, tmp_path, rot=90)
    w.search_panel.search_box.setText("verde")
    w.search_panel._search(sync=True)
    r = cv._ps(cv._search_rects[0])
    assert r.contains(QPointF(_centro(cv, "verde")))


def test_pide_contrasena_y_guarda_cifrado(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog
    from ui.main_window import MainWindow
    from models.annotation import Ann
    p = str(tmp_path / "secreto.pdf")
    d = pymupdf.open(); d.new_page().insert_text((72, 72), "secreto")
    d.save(p, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="abc", owner_pw="dueno")
    respuestas = iter([("mal", True), ("abc", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(respuestas))
    w = MainWindow(); w._open_path(p)
    cv = w._viewer.canvases[0]
    assert "secreto" in w._viewer.doc[0].get_text()
    cv._snap(); cv.anns.append(Ann("rect", x1=10, y1=10, x2=60, y2=40)); cv._commit()
    assert w.save_pdf()
    r = pymupdf.open(p)
    assert r.needs_pass and r.authenticate("abc") and len(list(r[0].annots())) == 1


def test_solo_lectura_bloquea_herramientas_e_impresion(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a))
    w, cv = _win(qapp, tmp_path, permisos=pymupdf.PDF_PERM_COPY)
    w._tool_changed("rect")
    assert cv.tool == "select" and avisos
    w._viewer.print_doc()
    assert len(avisos) == 2


def test_guardar_conserva_permisos(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from models.annotation import Ann
    preguntas = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: preguntas.append(a) or QMessageBox.StandardButton.Yes)
    w, cv = _win(qapp, tmp_path, permisos=pymupdf.PDF_PERM_ANNOTATE | pymupdf.PDF_PERM_PRINT)
    cv._snap(); cv.anns.append(Ann("rect", x1=10, y1=10, x2=60, y2=40)); cv._commit()
    assert w.save_pdf() and preguntas                       # avisa de la clave de propietario
    r = pymupdf.open(w._path)
    assert not r.needs_pass and not r.permissions & pymupdf.PDF_PERM_COPY
    assert len(list(r[0].annots())) == 1


def test_quitar_resaltado(qapp, tmp_path):
    from PyQt6.QtGui import QColor
    w, cv = _win(qapp, tmp_path)
    _arrastrar(cv, _centro(cv, "Hola"), _centro(cv, "azul"))
    cv._hl_sel(QColor(255, 235, 0, 160))
    antes = len(cv.anns); assert antes >= 1
    _arrastrar(cv, _centro(cv, "mundo"), _centro(cv, "azul"))     # seleccionar parte del texto resaltado
    marcas = cv._marks_in_sel()
    assert marcas and all(a.kind == "highlight" for a in marcas)
    cv._remove_marks(marcas)
    assert len(cv.anns) == antes - len(marcas) and not cv._tsel_rects
    w._viewer.undo(); assert len(cv.anns) == antes              # se puede deshacer
