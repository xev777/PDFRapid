# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Recorrido de las funciones de la app tal como las usaría una persona (ratón, menús, diálogos)."""
import pymupdf
from core.i18n import T
import pytest
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QTextEdit, QMessageBox, QFileDialog, QApplication


@pytest.fixture
def dialogos_aceptan(monkeypatch):
    """Los diálogos propios se aceptan escribiendo 'Prueba' en sus campos de texto."""
    def exec_(self):
        for te in self.findChildren(QTextEdit):
            te.setPlainText("Prueba")
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", exec_)


@pytest.fixture
def win(qapp, pdf_path, dialogos_aceptan):
    from ui.main_window import MainWindow
    w = MainWindow()
    w.resize(1200, 900)
    w.show()
    w._open_path(pdf_path)
    qapp.processEvents()
    return w


def _drag(cv, a, b):
    QTest.mousePress(cv, Qt.MouseButton.LeftButton, pos=QPoint(*a))
    QTest.mouseMove(cv, QPoint(*b))
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, pos=QPoint(*b))


def _click(cv, p, mod=Qt.KeyboardModifier.NoModifier):
    QTest.mouseClick(cv, Qt.MouseButton.LeftButton, mod, QPoint(*p))


@pytest.mark.parametrize("tool", ["line", "arrow", "darrow", "rect", "rrect", "circle",
                                  "triangle", "arrow_shape", "highlight", "textbox"])
def test_herramientas_de_dibujo(win, tool):
    cv = win._viewer.canvases[0]
    win.toolbox.activate(tool)
    _drag(cv, (100, 150), (260, 260))
    assert [a.kind for a in cv.anns] == [tool]
    win._undo()
    assert cv.anns == []


@pytest.mark.parametrize("tool", ["text", "comment"])
def test_texto_y_comentario(win, tool):
    cv = win._viewer.canvases[0]
    win.toolbox.activate(tool)
    _click(cv, (300, 500))
    assert [(a.kind, a.text) for a in cv.anns] == [(tool, "Prueba")]


def test_mover_duplicar_lazo_y_borrar(win):
    cv = win._viewer.canvases[0]
    win.toolbox.activate("rect")
    _drag(cv, (100, 150), (200, 220))
    _drag(cv, (300, 150), (400, 220))
    win.toolbox.activate("select")
    _drag(cv, (150, 185), (170, 205))                      # mover el primero
    assert cv.anns[0].x1 == pytest.approx(120, abs=1)
    win._undo()
    assert cv.anns[0].x1 == pytest.approx(100, abs=1)
    win.toolbox.activate("lasso")
    _drag(cv, (80, 130), (420, 240))
    assert len(cv._sel_multi) == 2
    QTest.keyClick(cv, Qt.Key.Key_Delete)
    assert cv.anns == []
    win._undo()
    assert len(cv.anns) == 2
    win.toolbox.activate("select")
    _click(cv, (150, 185))
    QTest.keyClick(cv, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    assert len(cv.anns) == 3


def test_formato_del_objeto(win):
    cv = win._viewer.canvases[0]
    win.toolbox.activate("rect")
    _drag(cv, (100, 150), (200, 220))
    cv._props_dlg(cv.anns[0])                               # diálogo aceptado sin cambios
    assert len(cv.anns) == 1


def test_insertar_imagen(win, tmp_path, monkeypatch):
    png = tmp_path / "img.png"
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 30), False)
    pix.clear_with(200)
    pix.save(str(png))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(png), ""))
    cv = win._viewer.canvases[0]
    win.toolbox.activate("image")
    _click(cv, (200, 200))
    assert [a.kind for a in cv.anns] == ["image"]


def test_editar_texto_original_y_deshacer(win):
    cv = win._viewer.canvases[0]
    win.toolbox.activate("text")
    sp = cv._spans[0]
    r = cv._ps(sp["vbbox"])
    _click(cv, (int(r.center().x()), int(r.center().y())))
    assert "Prueba" in win._viewer.doc[0].get_text()
    win._undo()
    assert "Prueba" not in win._viewer.doc[0].get_text()


def test_region_ocr_y_buscar(win):
    cv = win._viewer.canvases[0]
    win.toolbox.activate("ocr_region")
    _drag(cv, (50, 50), (300, 200))
    assert cv._ocr_rect is not None
    win.search_panel.search_box.setText("Pagina")
    win.search_panel._search(sync=True)
    assert len(win.search_panel._results) == 2
    win.search_panel._next()
    assert win.search_panel._idx == 1


def test_imprimir_a_pdf(win, tmp_path):
    from PyQt6.QtPrintSupport import QPrinter
    cv = win._viewer.canvases[0]
    win.toolbox.activate("rect")
    _drag(cv, (100, 150), (200, 220))
    out = str(tmp_path / "impreso.pdf")
    from ui import print_ui
    pr = QPrinter(QPrinter.PrinterMode.HighResolution)
    pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    pr.setOutputFileName(out)
    doc = print_ui.compose(win._viewer.export_copy(), {"pages": [0, 1], "annots": True, "mode": "fit"}, (595, 842))
    print_ui.paint(pr, doc, False)
    assert len(pymupdf.open(out)) == 2


def test_navegacion_zoom_y_rotar(win):
    v = win._viewer
    win._goto(1)
    assert v.current == 1 and win.pg_spin.value() == 2
    win._fit("width")
    win._fit("page")
    win.zoom_in(); win.zoom_out(); win.zoom_reset()
    assert v.zoom == 1.5
    win._rotate_pages_sig([1], 90)
    assert v.doc[1].rotation == 90


def test_operaciones_entre_pdfs(qapp, pdf_path, tmp_path, monkeypatch):
    from pdfgm_merge import PDFMergeWidget
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    m = PDFMergeWidget()
    w = m._win
    monkeypatch.setattr(w, "_ask_insert_position", lambda *a: 0)
    otro = str(tmp_path / "otro.pdf")
    d = pymupdf.open()
    for _ in range(3): d.new_page()
    d.save(otro)
    m.open_left(pdf_path)
    m.open_right(otro)
    L, R = w.panel_l, w.panel_r
    L.page_list.item(0).setSelected(True)
    w._do_op("copy_lr")
    assert len(R.doc) == 4 and len(L.doc) == 2
    w._do_op("move_lr")
    assert len(R.doc) == 5 and len(L.doc) == 1
    R.page_list.clearSelection(); R.page_list.item(0).setSelected(True)
    R.rotate_selected(90)
    assert R.doc[0].rotation == 90
    R.delete_selected()
    assert len(R.doc) == 4
    R.undo()
    assert len(R.doc) == 5
    out = str(tmp_path / "guardado.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    assert R.save_doc_as()
    assert len(pymupdf.open(out)) == 5


def test_texto_escala_con_el_zoom(win):
    from models.annotation import Ann
    cv = win._viewer.canvases[0]
    a = Ann("text", x1=100, y1=100, x2=200, y2=130, text="Hola", font_size=12)
    cv._snap(); cv.anns.append(a); cv._commit()
    h1 = a.brect().height()
    win._set_zoom(3.0)                         # 200 %
    assert a.qfont().pixelSize() == 36         # 12 pt × 3 px/pt
    assert a.brect().height() == pytest.approx(2 * h1, rel=0.25)


def test_operaciones_extra(qapp, pdf_path, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog
    from pdfgm_merge import PDFMergeWidget, MergeManyDialog, PagePreview
    m = PDFMergeWidget()
    w = m._win
    L = w.panel_l
    L.page_list.file_dropped.emit(pdf_path)                     # soltar desde el Explorador
    assert len(L.doc) == 2
    L.insert_blank()                                            # al final
    assert len(L.doc) == 3 and L.doc[2].get_text() == ""
    L.page_list.clearSelection()
    L.reverse_pages()                                           # sin selección: todo
    assert "Pagina 2" in L.doc[1].get_text() and L.doc[0].get_text() == ""
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("2-3", True))
    L.select_range()
    assert L.page_list.selected_page_nums() == [1, 2]
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    L.path = str(tmp_path / "doc.pdf")
    L.split_dialog()                                            # por defecto: cada N (=3) → 1 archivo
    assert len(pymupdf.open(str(tmp_path / "doc_parte1.pdf"))) == 3
    L.page_list.set_thumb_size(200)
    assert L.page_list.iconSize().width() == 200
    PagePreview(L, L.doc, 0)._show()
    dlg = MergeManyDialog(w)
    dlg.add_paths([pdf_path, pdf_path, str(tmp_path / "doc_parte1.pdf")])
    out = str(tmp_path / "combinado.pdf")
    dlg._combine(out)
    assert len(pymupdf.open(out)) == 7


def test_herramientas_de_documento(win, tmp_path, monkeypatch):
    from ui import doc_tools
    from core import pdf_tools
    v = win._viewer
    # proteger → al guardar queda cifrado
    def fill(self):
        self.ed_user.setText("abc"); self.ed_user2.setText("abc")
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(doc_tools.ProtectDialog, "exec", fill)
    doc_tools.protect(win)
    assert v.crypt and v.dirty and win.save_pdf()
    r = pymupdf.open(v.path)
    assert r.needs_pass and r.authenticate("abc")
    # comprimir, exportar imágenes y crear PDF desde imágenes
    out = str(tmp_path / "comp.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    doc_tools.compress(win)
    c = pymupdf.open(out)
    assert c.needs_pass and c.authenticate("abc") and len(c) == 2      # conserva la protección
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    doc_tools.export_images(win)
    png = tmp_path / "doc_p1.png"
    assert png.exists() and (tmp_path / "doc_p2.png").exists()
    out2 = str(tmp_path / "desde_imagenes.pdf")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(png)], ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out2, ""))
    doc_tools.images_to_pdf(win)
    assert win._viewer.path == out2 and len(win._viewer.doc) == 1 and win.doc_tabs.count() == 2


def test_panel_de_formulario(qapp, tmp_path, dialogos_aceptan):
    from ui.main_window import MainWindow
    p = str(tmp_path / "form.pdf")
    d = pymupdf.open(); page = d.new_page()
    w = pymupdf.Widget(); w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT; w.field_name = "nombre"
    w.rect = pymupdf.Rect(50, 50, 250, 70); page.add_widget(w); d.save(p)
    win = MainWindow(); win._open_path(p)
    assert win._form_panel.count == 1 and win._dock_form.isVisibleTo(win)
    f = __import__("core.pdf_tools", fromlist=["x"]).form_fields(win._viewer.doc)[0]
    win._viewer.edit_form(0, f["xref"], "Fernando")
    assert win._viewer.dirty and win._viewer.doc[0].first_widget.field_value == "Fernando"
    win._undo()
    assert win._viewer.doc[0].first_widget.field_value in ("", None)


def test_lectura_enlaces_indice_historial(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow
    p = str(tmp_path / "libro.pdf")
    d = pymupdf.open()
    for i in range(5):
        d.new_page().insert_text((72, 72), f"Capitulo {i + 1}")
    d[0].insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(72, 100, 200, 120), "page": 3})
    d[0].insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(72, 140, 200, 160), "uri": "https://example.com"})
    d.set_toc([[1, "Inicio", 1], [1, "Capítulo 3", 3], [2, "Sección 3.1", 3]])
    d.set_metadata({"title": "Libro", "author": "Fernando"}); d.save(p)
    w = MainWindow(); w.resize(1000, 800); w.show(); w._open_path(p); qapp.processEvents()
    v, cv = w._viewer, w._viewer.canvases[0]
    assert w._toc.tree.topLevelItemCount() == 2 and w._dock_toc.isVisibleTo(w)
    r = cv._ps(cv._links[0][0])
    QTest.mouseClick(cv, Qt.MouseButton.LeftButton, pos=r.center().toPoint())      # enlace interno
    qapp.processEvents()
    assert v.current == 3
    v.back(); qapp.processEvents()
    assert v.current == 0
    v.forward(); qapp.processEvents()
    assert v.current == 3
    abiertos = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr("ui.viewer.QDesktopServices.openUrl", lambda u: abiertos.append(u.toString()))
    v.go_to(0); qapp.processEvents()
    QTest.mouseClick(cv, Qt.MouseButton.LeftButton, pos=cv._ps(cv._links[1][0]).center().toPoint())
    assert abiertos == ["https://example.com"]
    info = []
    monkeypatch.setattr(QMessageBox, "about", lambda *a: info.append(a[2]))
    w.doc_properties()
    assert "Libro" in info[0] and "Fernando" in info[0]
    w.toggle_fullscreen(); assert not w.menuBar().isVisible()
    w.toggle_fullscreen(); assert w.menuBar().isVisible()


def test_lapiz_subrayado_firma_y_comentarios(win, tmp_path):
    from ui.canvas import PageCanvas
    from dialogs.signature import SignatureDialog
    v, cv = win._viewer, win._viewer.canvases[0]
    win.toolbox.activate("ink")                                   # lápiz
    QTest.mousePress(cv, Qt.MouseButton.LeftButton, pos=QPoint(100, 300))
    for x in range(110, 200, 10):
        QTest.mouseMove(cv, QPoint(x, 300 + (x % 30)))
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, pos=QPoint(200, 310))
    ink = cv.anns[-1]
    assert ink.kind == "ink" and len(ink.points) >= 5
    win.toolbox.activate("txtsel")                                 # subrayar y tachar texto
    w0 = cv._words[0]
    cv._update_tsel(QPointF(*cv._p2s(w0[0] + 1, w0[1] + 1)), QPointF(*cv._p2s(w0[2] - 1, w0[3] - 1)))
    cv._hl_sel(QColor("#0000ff"), "underline")
    cv._update_tsel(QPointF(*cv._p2s(w0[0] + 1, w0[1] + 1)), QPointF(*cv._p2s(w0[2] - 1, w0[3] - 1)))
    cv._hl_sel(QColor("#ff0000"), "strikeout")
    dlg = SignatureDialog(win)                                     # firma escrita
    dlg.tabs.setCurrentIndex(1); dlg.ed_name.setText("Fernando Erazo"); dlg._accept()
    assert dlg.result_b64
    PageCanvas.pending_signature = dlg.result_b64
    v.set_tool("signature")
    QTest.mouseClick(cv, Qt.MouseButton.LeftButton, pos=QPoint(300, 600))
    kinds = [a.kind for a in cv.anns]
    assert kinds == ["ink", "underline", "strikeout", "image"]
    win._comments.set_viewer(v)
    assert win._comments.lst.count() == 4
    win._comments._go(win._comments.lst.item(0))
    assert cv._sel is cv.anns[0]
    assert win.save_pdf()                                          # se guardan como anotaciones nativas
    page = pymupdf.open(v.path)[0]
    assert sorted(a.type[1] for a in page.annots()) == ["Ink", "Stamp", "StrikeOut", "Underline"]
    win._open_path(v.path)
    assert [a.kind for a in win._viewer.canvases[0].anns] == kinds   # y se recuperan editables


def test_sello_nocturno_mano_y_busqueda_con_opciones(qapp, tmp_path, dialogos_aceptan):
    from ui.main_window import MainWindow
    from ui.canvas import PageCanvas
    p = str(tmp_path / "b.pdf")
    d = pymupdf.open()
    for i in range(30):
        d.new_page().insert_text((72, 72), "Casa casa casamiento" if i in (2, 20) else "nada")
    d.save(p)
    w = MainWindow(); w.resize(1000, 700); w.show(); w._open_path(p); qapp.processEvents()
    v, cv = w._viewer, w._viewer.canvases[0]
    w._choose_stamp("APROBADO", "#1e8e3e")                      # sello
    QTest.mouseClick(cv, Qt.MouseButton.LeftButton, pos=QPoint(300, 400))
    assert cv.anns[-1].kind == "image" and cv.tool == "stamp"
    before = cv._base.toImage().pixelColor(5, 5).lightness()    # modo nocturno
    w.toggle_night()
    assert cv._base.toImage().pixelColor(5, 5).lightness() < before - 100
    w.toggle_night()
    w.toolbox.activate("hand")                                  # mano
    sb = v.scroll.verticalScrollBar(); y0 = sb.value()
    QTest.mousePress(cv, Qt.MouseButton.LeftButton, pos=QPoint(300, 500))
    QTest.mouseMove(cv, QPoint(300, 200))
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, pos=QPoint(300, 200))
    assert sb.value() > y0
    sp = w.search_panel; sp.set_doc(v.doc)                      # búsqueda con opciones
    sp.search_box.setText("casa"); sp._search(sync=True)
    assert len(sp._results) == 6
    sp.cb_word.setChecked(True); sp._search(sync=True)
    assert len(sp._results) == 4
    sp.cb_case.setChecked(True); sp._search(sync=True)
    assert len(sp._results) == 2 and sp.results.count() == 2
    sp._next(); qapp.processEvents()
    assert v.current == 20


def test_pestanas_de_documentos(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow
    from models.annotation import Ann
    paths = []
    for n in (2, 5):
        p = str(tmp_path / f"d{n}.pdf"); d = pymupdf.open()
        for _ in range(n): d.new_page()
        d.save(p); paths.append(p)
    w = MainWindow(); w.show()
    w._open_path(paths[0]); w._open_path(paths[1])
    assert w.doc_tabs.count() == 2 and len(w._viewer.doc) == 5 and w.thumbs.lst.count() == 5
    w.doc_tabs.setCurrentIndex(0)
    assert len(w._viewer.doc) == 2 and w.thumbs.lst.count() == 2 and w.pg_lbl.text().strip() == "/ 2"
    w._open_path(paths[1])                                   # ya abierto: no crea otra pestaña
    assert w.doc_tabs.count() == 2 and w.doc_tabs.currentIndex() == 1
    cv = w._viewer.canvases[0]
    cv._snap(); cv.anns.append(Ann("rect", x1=1, y1=1, x2=9, y2=9)); cv._commit()
    assert w.doc_tabs.tabText(1).startswith("•")
    preguntas = []
    monkeypatch.setattr(MainWindow, "_confirm_discard", lambda self: preguntas.append(1) or False)
    w._close_tab(1)                                          # con cambios: pregunta y no cierra
    assert preguntas and w.doc_tabs.count() == 2
    monkeypatch.setattr(MainWindow, "_confirm_discard", lambda self: True)
    w._close_tab(1); w._close_tab(0)
    assert w.doc_tabs.count() == 1 and w._viewer.doc is None   # queda una pestaña vacía


def test_exportar_a_word(win, tmp_path, monkeypatch):
    import docx
    from ui import doc_tools
    out = str(tmp_path / "doc.docx")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)   # no abrir Word
    doc_tools.export_word(win)
    texto = " ".join(p.text for p in docx.Document(out).paragraphs)
    assert "Pagina 1" in texto and "Pagina 2" in texto


def test_busqueda_por_pagina_y_en_carpeta(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow
    from ui.folder_search import FolderSearchDialog, _Worker
    from core.search import pdf_files
    sub = tmp_path / "sub"; sub.mkdir()
    for name, pages in (("a.pdf", ["contrato x", "nada", "contrato y contrato"]), ("sub/b.pdf", ["otro", "contrato"]),
                        ("c.pdf", ["sin coincidencias"])):
        d = pymupdf.open()
        for t in pages: d.new_page().insert_text((72, 72), t)
        d.save(str(tmp_path / name))
    w = MainWindow(); w.show(); w._open_path(str(tmp_path / "a.pdf"))
    sp = w.search_panel; sp.set_doc(w._viewer.doc); sp.cb_pages.setChecked(True)
    sp.search_box.setText("contrato"); sp._search(sync=True)
    assert sp.pages() == [1, 3] and sp.results.count() == 2 and "2 veces" in sp.results.item(1).text()
    sp._copy_pages()
    assert QApplication.clipboard().text() == "1, 3"
    assert len(pdf_files(str(tmp_path), True)) == 3 and len(pdf_files(str(tmp_path), False)) == 2
    dlg = FolderSearchDialog(w, str(tmp_path))
    dlg.ed.setText("contrato"); dlg._hit_files = dlg._hits = 0; dlg._missing, dlg._no_text, dlg._skipped = [], [], []
    dlg.cb_missing.setChecked(True)
    wk = _Worker(pdf_files(str(tmp_path), True), "contrato", dict(mode="phrase"))
    wk.result.connect(dlg._add); wk.done.connect(dlg._done); wk.run()       # síncrono
    assert dlg.tree.topLevelItemCount() == 3 and dlg._hits == 4 and dlg._missing[0].endswith("c.pdf")
    out = str(tmp_path / "res.csv")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    dlg._export()
    csv_txt = open(out, encoding="utf-8-sig").read()
    assert "Sin coincidencias;c.pdf" in csv_txt and csv_txt.count("Coincidencia;") == 4      # una fila por instancia
    sin = MainWindow()                                                     # sin documento: búsqueda desactivada
    assert not sin._btn_search.isEnabled() and not sin._doc_find[0].isEnabled()
    dlg.open_result.connect(w.open_search_result)
    b = next(dlg.tree.topLevelItem(i) for i in range(3) if dlg.tree.topLevelItem(i).toolTip(0).endswith("b.pdf"))
    dlg._open(b.child(0))                                                   # abre b.pdf en la página 2
    qapp.processEvents()
    assert w.doc_tabs.count() == 2 and w._viewer.path.endswith("b.pdf") and w._viewer.current == 1


def test_abrir_resultado_varias_veces_no_cierra_la_app(qapp, tmp_path):
    """Regresión: abrir el mismo resultado seguido recargaba el PDF con la búsqueda en curso → cierre nativo."""
    from ui.main_window import MainWindow
    p = str(tmp_path / "largo.pdf"); d = pymupdf.open()
    for i in range(400): d.new_page().insert_text((72, 72), "contrato" if i % 7 == 0 else "otra cosa")
    d.save(p)
    w = MainWindow(); w.show()
    for page in (14, 21, 14, 350):
        w.open_search_result(p, page, "contrato", False, False)       # sin esperar a que termine la búsqueda
    for _ in range(200): qapp.processEvents()
    assert w.doc_tabs.count() == 1 and w._viewer.doc is not None
    assert w.search_panel._results and w._viewer.current == 350


def test_texto_se_dibuja_sin_errores(win, monkeypatch):
    from models.annotation import Ann
    import ui.canvas as canvas_mod
    errores = []
    monkeypatch.setattr(canvas_mod.log, "exception", lambda *a, **k: errores.append(a))
    cv = win._viewer.canvases[0]
    cv._snap(); cv.anns.append(Ann("text", x1=50, y1=80, x2=200, y2=110, text="Hola\nmundo")); cv._commit()
    cv._redraw()
    assert errores == []


def test_cerrar_pestanas_seguidas_con_busqueda_en_curso(qapp, tmp_path, monkeypatch):
    """Regresión: al cerrar, las miniaturas usaban el documento ya cerrado → la app se caía."""
    from ui.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_confirm_discard", lambda self: True)
    paths = []
    for n in (3, 40, 80):
        p = str(tmp_path / f"d{n}.pdf"); d = pymupdf.open()
        for i in range(n): d.new_page().insert_text((72, 72), f"total {i}")
        d.save(p); paths.append(p)
    w = MainWindow(); w.resize(1200, 800); w.show()
    for p in paths: w.open_search_result(p, 1, "total", False, False)
    w._dock_comments.show(); w._dock_form.show()
    for i in (2, 1, 0):
        w.doc_tabs.tabCloseRequested.emit(min(i, w.doc_tabs.count() - 1))
        for _ in range(3): qapp.processEvents()
    for _ in range(100): qapp.processEvents()
    assert w.doc_tabs.count() == 1 and w._viewer.doc is None


def test_menu_documento_tachado_marca_numeracion_propiedades(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QLineEdit
    from ui.main_window import MainWindow
    from ui import doc_tools
    p = str(tmp_path / "datos.pdf"); d = pymupdf.open()
    for t in ("Cliente Juan Perez cedula 1712345678", "Juan Perez firma aqui"):
        d.new_page().insert_text((72, 100), t)
    d.save(p)
    w = MainWindow(); w.show(); w._open_path(p); v = w._viewer

    def exec_con(texto):
        def _exec(self):
            eds = self.findChildren(QLineEdit)
            if texto is not None and eds: eds[0].setText(texto)
            return QDialog.DialogCode.Accepted
        return _exec
    monkeypatch.setattr(QDialog, "exec", exec_con("Juan Perez"))
    doc_tools.mark_text_for_redaction(w)                       # marca en las 2 páginas
    assert sum(a.kind == "redact" for cv in v.canvases for a in cv.anns) == 2
    monkeypatch.setattr(QDialog, "exec", exec_con(None))
    doc_tools.apply_redactions(w)
    assert "Juan" not in v.doc[0].get_text() and "1712345678" in v.doc[0].get_text()
    assert not any(a.kind == "redact" for cv in v.canvases for a in cv.anns)
    w._undo()                                                  # el primer Ctrl+Z devuelve el contenido
    assert "Juan" in v.doc[0].get_text()
    w._redo()
    doc_tools.watermark_dialog(w)                              # valores por defecto: CONFIDENCIAL
    doc_tools.numbering_dialog(w)                              # «Página {n} de {total}»
    monkeypatch.setattr(QDialog, "exec", exec_con("Informe de auditoría"))
    doc_tools.edit_properties(w)                               # el primer campo es el título
    assert w.save_pdf()
    r = pymupdf.open(p)
    t0 = r[0].get_text()
    assert "Juan" not in t0 and "CONFIDENCIAL" in t0 and "Página 1 de 2" in t0
    assert r.metadata["title"] == "Informe de auditoría"


def test_busqueda_rapida_resaltado_y_rotacion_por_pasos(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow
    from ui.canvas import PageCanvas
    from models.annotation import Ann
    p = str(tmp_path / "q.pdf"); d = pymupdf.open()
    for i in range(30): d.new_page().insert_text((72, 72), "clave" if i in (3, 12, 25) else "otra")
    d.save(p)
    w = MainWindow(); w.resize(1100, 800); w.show(); w._open_path(p); qapp.processEvents()
    v = w._viewer
    v.go_to(10); qapp.processEvents()
    w._quick.setEditText("clave")                                             # escribir no busca nada todavía
    for _ in range(5): qapp.processEvents()
    assert not any(cv._search_rects for cv in v.canvases)

    def paso(d):
        w._quick_step(d)
        for _ in range(20): qapp.processEvents()
    paso(1); assert v.current == 12 and w._quick_count.text() == "p. 13 · 1/1"   # la siguiente desde la pág. 11
    paso(1); assert v.current == 25 and any(cv._search_rects for cv in v.canvases)
    paso(1); assert w._quick_count.text() == T("fin") and v.current == 25       # fin del documento: avisa
    paso(1); assert v.current == 3                                              # y la siguiente da la vuelta
    paso(-1); assert w._quick_count.text() == T("inicio")
    paso(-1); assert v.current == 25
    w._quick.lineEdit().textEdited.emit("")                                     # borrar la palabra quita el color
    assert not any(cv._search_rects for cv in v.canvases) and w._quick_count.text() == ""
    paso(1); w._quick.lineEdit().textEdited.emit("clave")                       # misma palabra: se mantiene
    assert any(cv._search_rects for cv in v.canvases)
    w._qf.clear()                                                               # Esc borra el amarillo
    assert not any(cv._search_rects for cv in v.canvases)
    # rotación: libre sin teclas, de 10 en 10 con Ctrl
    PageCanvas.rotation_step = 10
    cv = v.canvases[v.current]
    w.toolbox.activate("select")
    a = Ann("rect", x1=100, y1=100, x2=200, y2=160); cv._snap(); cv.anns.append(a); cv._commit(); cv._setsel(a); cv._redraw()
    esquina = lambda: a._rot(QPointF(a.brect().right() + 12, a.brect().top() - 12), a.rotation)   # zona de giro
    h = esquina()
    QTest.mousePress(cv, Qt.MouseButton.LeftButton, pos=h.toPoint())
    QTest.mouseMove(cv, QPoint(int(h.x()) + 37, int(h.y()) + 9))
    libre = a.rotation
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, pos=QPoint(int(h.x()) + 37, int(h.y()) + 9))
    assert libre % 10 != 0
    QTest.mousePress(cv, Qt.MouseButton.LeftButton, pos=esquina().toPoint())
    ev_pos = QPoint(int(h.x()) + 41, int(h.y()) + 13)
    QTest.mouseMove(cv, ev_pos)                                                 # QTest no lleva modificadores en move:
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent, QPointF as QPF
    me = QMouseEvent(QEvent.Type.MouseMove, QPF(ev_pos), QPF(cv.mapToGlobal(ev_pos)), Qt.MouseButton.NoButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier)
    cv.mouseMoveEvent(me)
    assert a.rotation % 10 == 0
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, pos=ev_pos)


def test_seleccion_sigue_al_objeto_girado():
    from PyQt6.QtCore import QPointF as P
    from models.annotation import Ann
    a = Ann("rect", x1=100, y1=100, x2=300, y2=140)        # horizontal 200×40, centro (200,120)
    a.rotation = 90
    hs = a.handles()
    assert abs(hs[4].x() - 200) < 1 and abs(hs[4].y() - 220) < 1      # el tirador derecho quedó abajo
    assert a.hit(P(200, 210)) and not a.hit(P(290, 120))              # se detecta en la forma girada
    anchor = hs[3]                                                     # tirador opuesto (izquierdo, ahora arriba)
    a.resize(4, 0, 30)                                                 # estirar hacia abajo = alargar en su eje
    assert abs((a.x2 - a.x1) - 230) < 0.5
    assert abs(a.handles()[3].x() - anchor.x()) < 0.5 and abs(a.handles()[3].y() - anchor.y()) < 0.5


def test_girar_con_ctrl_justo_despues_de_crear(win):
    """Recién dibujado (herramienta de dibujo activa) y con Ctrl presionado desde el clic: gira de N en N."""
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    from ui.canvas import PageCanvas
    PageCanvas.rotation_step = 15
    cv = win._viewer.canvases[0]
    win.toolbox.activate("rect")
    _drag(cv, (100, 150), (260, 230))
    a = cv.anns[-1]
    assert cv._sel is a and cv.tool == "rect"
    r = a.brect(); z = QPointF(r.right() + 12, r.top() - 12)            # fuera de la esquina superior derecha
    assert a.rot_zone(z) and a.hit_handle(z) < 0
    ctrl = Qt.KeyboardModifier.ControlModifier
    def ev(t, p, buttons):
        return QMouseEvent(t, QPointF(p), QPointF(cv.mapToGlobal(p.toPoint())), Qt.MouseButton.LeftButton, buttons, ctrl)
    cv.mousePressEvent(ev(QEvent.Type.MouseButtonPress, z, Qt.MouseButton.LeftButton))
    assert cv._rotating
    cv.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(r.right() + 40, r.center().y() + 30), Qt.MouseButton.LeftButton))
    cv.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(r.right() + 40, r.center().y() + 30), Qt.MouseButton.NoButton))
    assert a.rotation != 0 and a.rotation % 15 == 0 and len(cv.anns) == 1     # giró por pasos y no dibujó otro
    win._undo()
    assert a.rotation == 0 or cv.anns[-1].rotation == 0


def test_dibujar_flecha_con_ctrl_queda_en_angulos(win):
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    from ui.canvas import PageCanvas
    import math
    PageCanvas.rotation_step = 15
    cv = win._viewer.canvases[0]
    for tool in ("arrow", "line", "darrow"):
        win.toolbox.activate(tool)
        mods = Qt.KeyboardModifier.ControlModifier
        def ev(t, x, y, b):
            return QMouseEvent(t, QPointF(x, y), QPointF(cv.mapToGlobal(QPoint(x, y))), Qt.MouseButton.LeftButton, b, mods)
        cv.mousePressEvent(ev(QEvent.Type.MouseButtonPress, 100, 300, Qt.MouseButton.LeftButton))
        cv.mouseMoveEvent(ev(QEvent.Type.MouseMove, 260, 233, Qt.MouseButton.LeftButton))      # ~22.7°: debe ir a 15° o 30°
        cv.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, 260, 233, Qt.MouseButton.NoButton))
        a = cv.anns[-1]
        ang = math.degrees(math.atan2(-(a.y2 - a.y1), a.x2 - a.x1))
        assert a.kind == tool and abs(ang - round(ang / 15) * 15) < 0.01, (tool, ang)


def test_shift_no_ajusta_angulos(win):
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    import math
    cv = win._viewer.canvases[0]; win.toolbox.activate("arrow")
    def ev(t, x, y, b):
        return QMouseEvent(t, QPointF(x, y), QPointF(cv.mapToGlobal(QPoint(x, y))), Qt.MouseButton.LeftButton, b,
                           Qt.KeyboardModifier.ShiftModifier)
    cv.mousePressEvent(ev(QEvent.Type.MouseButtonPress, 100, 300, Qt.MouseButton.LeftButton))
    cv.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, 260, 233, Qt.MouseButton.NoButton))
    a = cv.anns[-1]
    ang = math.degrees(math.atan2(-(a.y2 - a.y1), a.x2 - a.x1))
    assert abs(ang - round(ang / 15) * 15) > 1          # Shift ya no ajusta: queda libre


def test_comparar_con_otro_pdf(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow
    from ui import compare_dialog
    pa, pb = str(tmp_path / "v1.pdf"), str(tmp_path / "v2.pdf")
    for path, txt in ((pa, "Plazo de 30 dias"), (pb, "Plazo de 45 dias")):
        d = pymupdf.open(); d.new_page().insert_text((72, 72), txt); d.new_page().insert_text((72, 72), "igual"); d.save(path)
    w = MainWindow(); w.show(); w._open_path(pa)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (pb, ""))
    vistos = []
    monkeypatch.setattr(compare_dialog.CompareDialog, "exec",
                        lambda self: vistos.append((self.lst.count(), self.changes.count(), self.view_a[2].pixmap().isNull())))
    w._compare()
    assert vistos == [(1, 1, False)]                       # 1 página con cambios, 1 cambio, imagen dibujada


def test_miniatura_muestra_los_objetos(win, qapp):
    from models.annotation import Ann
    cv = win._viewer.canvases[0]
    item = win.thumbs.lst.item(0)
    antes = item.icon().pixmap(110, 140).toImage()
    cv._snap(); cv.anns.append(Ann("rect", x1=40, y1=40, x2=600, y2=700, fill="#dc2626", stroke="#dc2626")); cv._commit()
    win.thumbs.refresh(); qapp.processEvents()
    despues = item.icon().pixmap(110, 140).toImage()
    c = despues.pixelColor(despues.width() // 2, despues.height() // 2)
    assert c.red() > 150 and c.green() < 120 and antes != despues            # el rectángulo rojo se ve en la miniatura


def test_barra_de_formato(win):
    from PyQt6.QtGui import QColor
    cv = win._viewer.canvases[0]; tb = win.toolbox
    tb.c_stroke.set(QColor("#16a34a")); tb.sp_width.setValue(4); tb.c_fill.set(QColor("#fde68a"))
    win.toolbox.activate("rect"); _drag(cv, (100, 150), (220, 230))          # lo nuevo sale con ese estilo
    a = cv.anns[-1]
    assert (a.stroke, a.fill, a.stroke_width) == ("#16a34a", "#fde68a", 4)
    tb.c_stroke.set(QColor("#dc2626"))                                       # con selección: la cambia
    assert a.stroke == "#dc2626"
    win._undo()
    assert cv.anns[-1].stroke == "#16a34a"
    cv._setsel(cv.anns[-1])                                                  # al seleccionar, la barra muestra su estilo
    assert tb.c_stroke.color.name() == "#16a34a" and tb.sp_width.value() == 4


def test_atajos_de_herramientas_sin_botones_vacios(win, qapp):
    from PyQt6.QtWidgets import QToolButton
    vacios = [w for w in win.toolbox.findChildren(QToolButton) if w.isVisible() and not w.icon().cacheKey() and not w.text()]
    assert not vacios                                            # antes: 21 botones invisibles ocupaban la barra
    win._viewer.canvases[0].setFocus()
    QTest.keyClick(win._viewer.canvases[0], Qt.Key.Key_R); qapp.processEvents()
    assert win.toolbox.current == "rect"
    QTest.keyClick(win._viewer.canvases[0], Qt.Key.Key_V); qapp.processEvents()
    assert win.toolbox.current == "select"


@pytest.mark.parametrize("rot", [0, 90, 270])
def test_busqueda_rapida_marca_la_palabra_en_pagina_girada(qapp, tmp_path, rot):
    """El resaltado debe caer sobre la palabra, también en páginas giradas."""
    from ui.main_window import MainWindow
    p = str(tmp_path / "g.pdf"); d = pymupdf.open(); pg = d.new_page()
    pg.insert_text((300, 500), "objetivo", fontsize=14); pg.set_rotation(rot); d.save(p)
    w = MainWindow(); w.show(); w._open_path(p); qapp.processEvents()
    w._quick.setEditText("objetivo"); w._quick_step(1)
    for _ in range(10): qapp.processEvents()
    cv = w._viewer.canvases[0]
    marca = cv._ps(cv._search_rects[0])
    palabra = next(cv._ps(x[:4]) for x in cv._words if x[4] == "objetivo")     # posición en pantalla de la palabra
    assert marca.intersects(palabra) and abs(marca.center().x() - palabra.center().x()) < 5
