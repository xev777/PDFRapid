# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Ventana Principal de la aplicación"""
from core.portable import qsettings
from core.i18n import T, Tf
import os
import sys
from PyQt6.QtWidgets import (QMainWindow, QWidget, QSizePolicy, QVBoxLayout, QHBoxLayout,
                             QTabWidget, QDockWidget, QStatusBar, QToolBar,
                             QToolButton, QLabel, QSpinBox, QFileDialog,
                             QMessageBox, QInputDialog, QLineEdit, QTreeWidget, QTreeWidgetItem, QDialog, QComboBox,
                             QApplication)
from PyQt6.QtGui import QAction, QShortcut, QKeySequence
from PyQt6.QtCore import Qt, QSize, QTimer
from ui.viewer import Viewer
from ui.sidebar import ToolsBar
from ui.draw_defaults import DrawDefaults
from ui.thumbs import Thumbs
from ui.search_panel import SearchPanel
from ui.ocr_panel import OcrPanel
from ui.styles import C, MENU_SS
from ui.icons import get_icon, get_toggle_icon
from core.settings import AppSettings
from core.pdf_io import PasswordRequired, crypt_warning
from ui import doc_tools, help_ui
from models.annotation import Ann
from core.constants import SOURCE_URL, DONATE_URL, APP_NAME, APP_VERSION, APP_TITLE, APP_TAGLINE, AUTOSAVE_MS, T_QRLENS, T_SELECT
from core.logger import log


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(T(APP_TITLE))
        self.setMinimumSize(1300, 840)
        self.resize(1680, 980)
        self._settings = AppSettings()
        try:
            self._build_ui()
            self._build_menu()
            self._build_toolbar()
            self._refresh_doc_ui()          # estado inicial: sin documento
            self._status(T("Listo · Clic derecho sobre objetos para opciones · F1 para ayuda"))
            log.info(f"{APP_NAME} {APP_VERSION} iniciado")
        except Exception as e:
            log.critical(f"__init__: {e}")

    def _build_ui(self):
        cw = QWidget()
        self.setCentralWidget(cw)
        mh = QHBoxLayout(cw)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.setSpacing(0)
        self.thumbs = Thumbs()
        self.thumbs.clicked.connect(lambda i: self._viewer.jump(i))
        self.thumbs.overlay = self._thumb_overlay
        self._thumb_timer = QTimer(self); self._thumb_timer.setSingleShot(True); self._thumb_timer.setInterval(600)
        self._thumb_timer.timeout.connect(self.thumbs.refresh)
        self._autosave_timer = QTimer(self); self._autosave_timer.setInterval(AUTOSAVE_MS)   # recuperación tras un cierre inesperado
        self._autosave_timer.timeout.connect(self.autosave_all); self._autosave_timer.start()
        QTimer.singleShot(700, self._offer_recovery)
        self.thumbs.rotate_pages.connect(self._rotate_pages_sig)
        mh.addWidget(self.thumbs)
        col = QWidget()
        col_lay = QVBoxLayout(col)
        col_lay.setContentsMargins(0, 0, 0, 0)
        col_lay.setSpacing(0)
        self.search_panel = SearchPanel()
        self.search_panel.go_to_result.connect(self._on_search_result)
        self.search_panel.closed.connect(lambda: self._viewer and self._viewer.highlight_search(-1, []))
        col_lay.addWidget(self.search_panel)
        mid = QWidget()
        midh = QHBoxLayout(mid)
        midh.setContentsMargins(0, 0, 0, 0)
        midh.setSpacing(0)
        self.toolbox = ToolsBar()
        self.toolbox.tool_changed.connect(self._tool_changed)
        self.toolbox.stamp_chosen.connect(self._choose_stamp)
        self.toolbox.fill_chosen.connect(self._choose_fill)
        self.toolbox.measure_chosen.connect(self._choose_measure)
        self.toolbox.format_changed.connect(self._apply_format)
        self.tabs = QTabWidget()
        midh.addWidget(self.tabs, 1)
        col_lay.addWidget(mid, 1)
        mh.addWidget(col, 1)
        # una pestaña por documento; self._viewer es siempre el de la pestaña activa
        self.doc_tabs = QTabWidget()
        self.doc_tabs.setTabsClosable(True); self.doc_tabs.setMovable(True); self.doc_tabs.setDocumentMode(True)
        self.doc_tabs.tabCloseRequested.connect(self._close_tab)
        self.doc_tabs.currentChanged.connect(self._on_doc_tab)
        self._props = DrawDefaults()
        self._props.on_select = lambda a: hasattr(self, "toolbox") and self.toolbox.show_format(a)
        self._new_viewer()
        self.tabs.addTab(self.doc_tabs, get_icon("pdf_doc"), T("Visor / Editor PDF"))
        self.setAcceptDrops(True)
        try:
            from pdfgm_merge import PDFMergeWidget
            self._merge_tab = PDFMergeWidget()
            self._merge_tab.status.connect(self._status)
            self.tabs.addTab(self._merge_tab, get_icon("merge"), T("Operaciones entre PDFs"))
        except ImportError:
            log.warning("pdfgm_merge.py no encontrado")
            self._merge_tab = None
        self._ocr_panel = OcrPanel()
        dock_ocr = QDockWidget(T("OCR"), self)
        dock_ocr.setWidget(self._ocr_panel)
        dock_ocr.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock_ocr)
        dock_ocr.hide()
        self._dock_ocr = dock_ocr
        from ui.bookmarks import BookmarksPanel
        self._toc = BookmarksPanel()
        dock_toc = QDockWidget(T("Marcadores"), self); dock_toc.setWidget(self._toc)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_toc)
        dock_toc.hide(); self._dock_toc = dock_toc
        from ui.attachments import AttachmentsPanel
        self._attach = AttachmentsPanel(self)
        dock_att = QDockWidget(T("Adjuntos"), self); dock_att.setWidget(self._attach)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_att); self.tabifyDockWidget(dock_toc, dock_att)
        dock_att.hide(); self._dock_att = dock_att
        self._form_panel = doc_tools.FormPanel()
        dock_form = QDockWidget(T("Formulario"), self)
        dock_form.setWidget(self._form_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock_form)
        dock_form.hide()
        self._dock_form = dock_form
        from ui.signature_ui import SignaturesPanel
        self._sigs = SignaturesPanel()
        dock_sig = QDockWidget(T("Firmas"), self); dock_sig.setWidget(self._sigs)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock_sig); dock_sig.hide(); self._dock_sigs = dock_sig
        self._comments = doc_tools.CommentsPanel()
        dock_com = QDockWidget(T("Comentarios"), self); dock_com.setWidget(self._comments)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock_com)
        self.tabifyDockWidget(dock_form, dock_com); dock_com.hide(); self._dock_comments = dock_com
        dock_com.visibilityChanged.connect(lambda vis: vis and self._comments.refresh())
        for d in (dock_ocr, dock_toc, dock_att, dock_form, dock_sig, dock_com):     # «?» y «×» en el título de cada panel
            help_ui.dock_title(d, help_ui.CLASS_TOPICS[type(d.widget()).__name__])
        if not hasattr(QApplication.instance(), "_help_filter"): help_ui.install(QApplication.instance())
        self.setStatusBar(QStatusBar())
        self._esc_fs = QShortcut(QKeySequence("Esc"), self)      # salir de pantalla completa
        self._esc_fs.setEnabled(False); self._esc_fs.activated.connect(self.toggle_fullscreen)
        self._sb_info = QLabel()
        self._sb_info.setStyleSheet(f"color:{C['muted']};padding:0 8px;")
        self.statusBar().addPermanentWidget(self._sb_info)
        self.tabs.currentChanged.connect(self._on_tab)

    def _build_menu(self):
        """Menús agrupados por tarea, como Acrobat/Foxit (cada submenú agrupa acciones afines)."""
        mb = self.menuBar()

        def sub(menu, title, icon=None):
            m = menu.addMenu(get_icon(icon), title) if icon else menu.addMenu(title)
            m.setStyleSheet(MENU_SS)
            return m

        # ── Archivo: abrir, guardar, crear, exportar, imprimir ──
        fm = mb.addMenu(T("Archivo")); fm.setStyleSheet(MENU_SS)
        self._act(fm, T("Abrir PDF…"), self.open_pdf, T("Ctrl+O"), "open")
        self._recent_menu = sub(fm, T("Abrir reciente"), "open")
        self._recent_menu.aboutToShow.connect(self._fill_recent)
        fm.addSeparator()
        self._act(fm, T("Guardar"), self.save_pdf, T("Ctrl+S"), "save")
        self._act(fm, T("Guardar como…"), self.save_pdf_as, T("Ctrl+Shift+S"), "save")
        fm.addSeparator()
        cm = sub(fm, T("Crear PDF"), "pdf_doc")
        self._act(cm, T("Desde imágenes…"), lambda: doc_tools.images_to_pdf(self), icon="image")
        self._act(cm, T("Desde Word, Excel o PowerPoint…"), lambda: doc_tools.from_office(self), icon="pdf_doc")
        self._act(cm, T("Desde el escáner…"), lambda: doc_tools.scan(self), icon="ocr_panel")
        xm = sub(fm, T("Exportar"), "save")
        self._act(xm, T("A Word (.docx)…"), lambda: doc_tools.export_word(self), icon="textbox")
        self._act(xm, T("A Excel (.xlsx, tablas)…"), lambda: doc_tools.export_other(self, "xlsx"), icon="table")
        self._act(xm, T("A texto (.txt)…"), lambda: doc_tools.export_other(self, "txt"), icon="text")
        self._act(xm, T("A HTML (página web)…"), lambda: doc_tools.export_other(self, "html"), icon="text")
        self._act(xm, T("A Markdown (.md)…"), lambda: doc_tools.export_other(self, "md"), icon="text")
        self._act(xm, T("Páginas como imágenes…"), lambda: doc_tools.export_images(self), icon="image")
        self._act(xm, T("Como PDF/A (archivo a largo plazo)…"), lambda: doc_tools.export_pdfa(self), icon="save")
        fm.addSeparator()
        self._act(fm, T("Imprimir…"), self.print_pdf, T("Ctrl+P"), "print")
        self._act(fm, T("Propiedades del documento…"), self.doc_properties, T("Ctrl+I"), "help")
        fm.addSeparator()
        self._act(fm, T("Cerrar PDF"), self.close_pdf, T("Ctrl+W"), "close")
        self._act(fm, T("Siguiente documento"), lambda: self.doc_tabs.setCurrentIndex((self.doc_tabs.currentIndex() + 1) % self.doc_tabs.count()), T("Ctrl+Tab"), "swap")
        fm.addSeparator()
        self._act(fm, T("Salir"), self.close, T("Ctrl+Q"), "exit")

        # ── Editar: deshacer, objetos, buscar, preferencias ──
        em = mb.addMenu(T("Editar")); em.setStyleSheet(MENU_SS)
        self._act(em, T("Deshacer"), self._undo, T("Ctrl+Z"), "undo")
        self._act(em, T("Rehacer"), self._redo, T("Ctrl+Shift+Z"), "redo")
        em.addSeparator()
        self._act(em, T("Duplicar"), self._duplicate, T("Ctrl+D"), "duplicate")
        self._act(em, T("Eliminar"), self._delete_sel, icon="delete")
        em.addSeparator()
        self._doc_find = [self._act(em, T("Buscar en el documento"), self._toggle_search, T("Ctrl+F"), "search")]
        self._doc_find += [self._act(em, T("Buscar siguiente"), self.search_panel._next, "F3", "next"),
                           self._act(em, T("Buscar anterior"), self.search_panel._prev, T("Shift+F3"), "prev")]
        self._act(em, T("Buscar en carpeta…"), self.folder_search, T("Ctrl+Shift+F"), "search")
        em.addSeparator()
        self._act(em, T("Preferencias…"), self.preferences, T("Ctrl+,"), "format")

        # ── Vista: zoom, diseño, navegación, paneles, reglas, apariencia ──
        vm = mb.addMenu(T("Vista")); vm.setStyleSheet(MENU_SS)
        zm = sub(vm, T("Zoom"), "zoom_in")
        self._act(zm, T("Acercar"), self.zoom_in, T("Ctrl++"), "zoom_in")
        self._act(zm, T("Alejar"), self.zoom_out, T("Ctrl+-"), "zoom_out")
        self._act(zm, "100%", self.zoom_reset, T("Ctrl+0"))
        self._act(zm, T("Ajustar al ancho"), lambda: self._fit("width"), icon="fit_width")
        self._act(zm, T("Página completa"), lambda: self._fit("page"), icon="fit_page")
        lm = sub(vm, T("Diseño de página"), "pdf_doc")
        from PyQt6.QtGui import QActionGroup
        from ui.viewer import _PagesArea
        mode = self._settings.get_str("page_layout", "continuous")
        _PagesArea.mode = mode if mode in ("continuous", "two", "cover") else "continuous"
        grp = QActionGroup(self); self._layout_acts = {}
        for key, label in (("continuous", T("Una página (continua)")), ("two", T("Dos páginas")),
                           ("cover", T("Dos páginas con portada"))):
            a = self._act(lm, label, lambda _=False, k=key: self.set_page_layout(k),
                          icon={"continuous": "page1", "two": "page2", "cover": "cover"}[key])
            a.setCheckable(True); a.setChecked(key == _PagesArea.mode); grp.addAction(a); self._layout_acts[key] = a
        nm = sub(vm, T("Navegación"), "goto")
        self._act(nm, T("Ir a página…"), self._go_to_page, T("Ctrl+G"), "goto")
        self._act(nm, T("Atrás"), lambda: self._viewer.back(), T("Alt+Left"), "prev")
        self._act(nm, T("Adelante"), lambda: self._viewer.forward(), T("Alt+Right"), "next")
        vm.addSeparator()
        pm = sub(vm, T("Paneles"), "select_group")
        self._act(pm, T("Marcadores"), lambda: self._dock_toc.setVisible(not self._dock_toc.isVisible()), T("Ctrl+B"), "range_select")
        self._act(pm, T("Adjuntos"), lambda: self._dock_att.setVisible(not self._dock_att.isVisible()), icon="duplicate")
        self._act(pm, T("Comentarios"), lambda: self._dock_comments.setVisible(not self._dock_comments.isVisible()), T("Ctrl+Shift+C"), "comment")
        self._act(pm, T("Formulario"), lambda: self._dock_form.setVisible(not self._dock_form.isVisible()), icon="textbox")
        self._act(pm, T("Firmas digitales"), lambda: self._dock_sigs.setVisible(not self._dock_sigs.isVisible()), icon="signature")
        self._act(pm, T("OCR"), lambda: self._dock_ocr.setVisible(not self._dock_ocr.isVisible()), icon="ocr_panel")
        self._act(vm, T("Reglas"), self.toggle_rulers, T("Ctrl+R"), "ruler")
        from ui.canvas import PageCanvas
        PageCanvas.load_guide_options()
        gm = sub(vm, T("Guías y ajuste"), "ruler")
        self._guide_acts = {}
        for key, label, sc in (("guides_visible", T("Mostrar guías"), "Ctrl+;"), ("snap_guides", T("Ajustar a guías"), None),
                               ("snap_objects", T("Ajustar a objetos"), None)):
            a = self._act(gm, label, lambda on, k=key: self.set_guide_option(k, on), sc)
            a.setCheckable(True); a.setChecked(getattr(PageCanvas, key)); self._guide_acts[key] = a
        gm.addSeparator()
        self._act(gm, T("Borrar todas las guías"), lambda: self._viewer.clear_guides(), icon="delete")
        vm.addSeparator()
        self._act(vm, T("Pantalla completa"), self.toggle_fullscreen, T("F11"), "fit_page")
        self._act(vm, T("Modo nocturno (lectura)"), self.toggle_night, T("Ctrl+Shift+N"), "moon")
        from ui.read_aloud import ReadAloud
        self._reader = ReadAloud(self)
        ra = sub(vm, T("Leer en voz alta"), "speaker")
        self._act(ra, T("Leer esta página"), lambda: self._reader.read("page"), "Ctrl+Shift+V", "speaker")
        self._act(ra, T("Leer hasta el final del documento"), lambda: self._reader.read("to_end"), "Ctrl+Shift+B", "next")
        self._act(ra, T("Leer el texto seleccionado"), lambda: self._reader.read("selection"), icon="txtsel")
        ra.addSeparator()
        self._act(ra, T("Pausar / continuar"), lambda: self._reader.pause_resume(), "Ctrl+Shift+P", "pause")
        self._act(ra, T("Detener"), lambda: self._reader.stop(), "Ctrl+Shift+E", "stop")
        ra.addSeparator()
        self._act(ra, T("Voz y velocidad…"), lambda: self._reader.settings_dialog(), icon="voice")
        from ui.styles import THEMES, current_theme
        tm = sub(vm, T("Tema"), "moon")
        for key, (name, _) in THEMES.items():
            a = tm.addAction(T(name)); a.setCheckable(True); a.setChecked(key == current_theme())
            a.triggered.connect(lambda _, k=key: self._set_theme(k))

        # ── Documento: páginas, protección, firmas, herramientas ──
        dm = mb.addMenu(T("Documento")); dm.setStyleSheet(MENU_SS)
        pgm = sub(dm, T("Páginas"), "pdf_doc")
        self._act(pgm, T("Recortar páginas…"), lambda: doc_tools.crop_pages_dialog(self), icon="crop")
        self._act(pgm, T("Marca de agua…"), lambda: doc_tools.watermark_dialog(self), icon="stamp")
        self._act(pgm, T("Encabezado, pie y numeración…"), lambda: doc_tools.numbering_dialog(self), icon="text")
        self._act(pgm, T("Fondo de página…"), lambda: doc_tools.background_dialog(self), icon="fill")
        sm = sub(dm, T("Proteger"), "lock")
        self._act(sm, T("Proteger con contraseña…"), lambda: doc_tools.protect(self), icon="lock")
        self._act(sm, T("Marcar texto para tachado…"), lambda: doc_tools.mark_text_for_redaction(self), icon="search")
        self._act(sm, T("Aplicar tachado definitivo…"), lambda: doc_tools.apply_redactions(self), icon="redact")
        self._act(sm, T("Eliminar información oculta…"), lambda: doc_tools.scrub_dialog(self), icon="lock")
        fsm = sub(dm, T("Firmas"), "signature")
        self._act(fsm, T("Firmar con certificado digital…"), lambda: __import__("ui.signature_ui", fromlist=["x"]).sign_document(self), icon="signature")
        self._act(fsm, T("Ver firmas digitales"), lambda: self._dock_sigs.setVisible(True), icon="lock")
        dm.addSeparator()
        self._act(dm, T("Comparar con otro PDF…"), self._compare, icon="swap")
        self._act(dm, T("Procesar por lotes…"), lambda: __import__("ui.batch_ui", fromlist=["x"]).batch_dialog(self), icon="duplicate")
        self._act(dm, T("Comprimir PDF…"), lambda: doc_tools.compress(self), icon="save")
        lk = sub(dm, T("Enlaces"), "link")
        self._act(lk, T("Añadir enlace…"), lambda: doc_tools.add_link(self), icon="link")
        self._act(lk, T("Gestionar enlaces…"), lambda: doc_tools.manage_links(self), icon="link")
        frm = sub(dm, T("Formulario"), "textbox")
        for k, name in doc_tools.FIELD_KIND_NAMES.items():
            self._act(frm, Tf("Añadir: {0}", T(name)), lambda _=False, k=k: doc_tools.add_form_field(self, k), icon="textbox")
        frm.addSeparator()
        self._act(frm, T("Detectar campos automáticamente…"), lambda: doc_tools.detect_fields_dialog(self), icon="search")
        self._act(frm, T("Vaciar formulario…"), lambda: doc_tools.reset_form_dialog(self), icon="textbox")
        self._act(frm, T("Ver panel Formulario"), lambda: self._dock_form.setVisible(True), icon="textbox")
        self._act(dm, T("Aplanar anotaciones y formularios…"), lambda: doc_tools.flatten_dialog(self), icon="select_group")
        self._act(dm, T("Adjuntar archivo…"), lambda: (self._dock_att.setVisible(True), self._attach.add()), icon="duplicate")
        dm.addSeparator()
        self._act(dm, T("Editar propiedades (título, autor…)…"), lambda: doc_tools.edit_properties(self), icon="format")

        hm = mb.addMenu(T("Ayuda")); hm.setStyleSheet(MENU_SS)
        self._act(hm, T("Ayuda de lo que estoy usando"), lambda: help_ui.context_help(), "F1", "help")
        self._act(hm, T("Centro de ayuda…"), lambda: help_ui.show_help(None, self), "Shift+F1", "search")
        self._act(hm, T("Guía de usuario"), self.user_guide, icon="pdf_doc")
        self._act(hm, T("Atajos de teclado"), self.shortcuts_help, "Ctrl+F1", "help")
        self._act(hm, T("Privacidad y licencias"), self.open_legal, icon="pdf_doc")
        hm.addSeparator()
        self._act(hm, T("Apoyar el proyecto (donar)…"), lambda: __import__("ui.donate", fromlist=["x"]).show(self), icon="heart")
        hm.addAction(self._act(None, T("Acerca de…"), self.about, icon="help"))

    def _build_toolbar(self):
        tb = self._main_tb = QToolBar("Principal")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        self.addToolBar(tb)
        # Estilo aplicado por widget para el estado "checked": bajo esta combinación
        # de PyQt6/Fusion/Windows, QToolButton:checked en QSS a veces no pinta el
        # relleno (queda "hueco"), así que se fuerza el estilo desde el código.
        toolbtn_off = (
            f"QToolButton{{background-color:transparent;border:1px solid transparent;border-radius:4px;padding:4px 8px;}}"
            f"QToolButton:hover{{background-color:{C['hover']};border-color:{C['border']};}}"
        )
        toolbtn_on = f"QToolButton{{background-color:{C['accent']};border:1px solid {C['accent']};border-radius:4px;padding:4px 8px;}}"

        def tbtn(icon, tip, slot, checkable=False):
            b = QToolButton()
            b.setIcon(get_toggle_icon(icon) if checkable else get_icon(icon))
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.setStyleSheet(toolbtn_off)
            if checkable:
                b.toggled.connect(lambda on, btn=b: btn.setStyleSheet(toolbtn_on if on else toolbtn_off))
            b.clicked.connect(slot)
            tb.addWidget(b)
            return b
        # Archivo
        tbtn("open", T("Abrir PDF  Ctrl+O"), self.open_pdf)
        tbtn("save", T("Guardar  Ctrl+S"), self.save_pdf)
        tbtn("print", T("Imprimir  Ctrl+P"), self.print_pdf)
        tb.addSeparator()
        # Edición
        tbtn("undo", T("Deshacer  Ctrl+Z"), self._undo)
        tbtn("redo", T("Rehacer  Ctrl+Shift+Z"), self._redo)
        tb.addSeparator()
        # Navegación
        tbtn("prev", T("Página anterior"), lambda: self._goto(self._viewer.current - 1))
        self.pg_spin = QSpinBox()
        self.pg_spin.setRange(1, 1)
        self.pg_spin.setFixedWidth(64)
        self.pg_spin.setFixedHeight(28)
        self.pg_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.pg_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pg_spin.editingFinished.connect(lambda: self._goto(self.pg_spin.value() - 1))
        tb.addWidget(self.pg_spin)
        self.pg_lbl = QLabel(" / 0 ")
        self.pg_lbl.setStyleSheet(f"color:{C['muted']};")
        tb.addWidget(self.pg_lbl)
        tbtn("next", T("Página siguiente"), lambda: self._goto(self._viewer.current + 1))
        tb.addSeparator()
        # Vista
        tbtn("zoom_out", T("Zoom -  Ctrl+-"), self.zoom_out)
        self.zoom_lbl = QLabel("100%")
        self.zoom_lbl.setStyleSheet(f"color:{C['muted']};min-width:38px;")
        self.zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tb.addWidget(self.zoom_lbl)
        tbtn("zoom_in", T("Zoom +  Ctrl++"), self.zoom_in)
        tbtn("fit_width", T("Ajustar al ancho"), lambda: self._fit("width"))
        tbtn("fit_page", T("Página completa"), lambda: self._fit("page"))
        tb.addSeparator()
        tbtn("rotate_cw", T("Rotar página 90°"), lambda: self._viewer.doc and self._rotate_pages_sig([self._viewer.current], 90))
        tb.addSeparator()
        tbtn("digisign", T("Firmar con certificado digital…"), lambda: __import__("ui.signature_ui", fromlist=["x"]).sign_document(self))
        self._btn_qrlens = tbtn("qrlens", T("Lupa QR: leer el código QR de una firma") + "  (W)", self._toggle_qrlens, checkable=True)
        self.toolbox.tool_changed.connect(lambda t: self._btn_qrlens.setChecked(t == T_QRLENS))
        tbtn("speaker", T("Leer en voz alta esta página; otro clic detiene  (Ctrl+Shift+V)"),
             lambda: self._reader.stop() if self._reader.speaking() else self._reader.read("page"))
        tb.addSeparator()
        self._btn_search = tbtn("search", T("Buscar en el documento  Ctrl+F"), self._toggle_search)
        tbtn("ops", T("Buscar en carpeta (varios PDF)  Ctrl+Shift+F"), self.folder_search)
        # búsqueda rápida: escribir salta a la coincidencia más cercana desde la página actual
        self._quick = QComboBox(); self._quick.setEditable(True); self._quick.setFixedWidth(210)
        self._quick.setInsertPolicy(QComboBox.InsertPolicy.NoInsert); self._quick.setMaxCount(12)
        self._quick.lineEdit().setPlaceholderText(T("Búsqueda rápida…"))
        self._quick.setToolTip(T("Escribe una palabra y pulsa Enter o ▶ para ir a la siguiente coincidencia, ◀ para la anterior · Esc borra"))
        self._quick.lineEdit().returnPressed.connect(lambda: self._quick_step(1))
        self._quick.activated.connect(lambda _: self._quick_step(1))
        self._quick.lineEdit().installEventFilter(self)
        self._quick.lineEdit().textEdited.connect(lambda t: self._qf.term not in (None, t.strip()) and self._qf.clear())
        tb.addWidget(self._quick)
        self._quick_prev = tbtn("prev", T("Coincidencia anterior  (Shift+F3)"), lambda: self._quick_step(-1))
        self._quick_next = tbtn("next", T("Coincidencia siguiente  (F3)"), lambda: self._quick_step(1))
        self._quick_count = QLabel(""); self._quick_count.setStyleSheet(f"color:{C['muted']};min-width:46px;")
        tb.addWidget(self._quick_count)
        from ui.quick_find import QuickFind
        self._qf = QuickFind(self, self._quick_count)
        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred); tb.addWidget(spacer)
        tbtn("heart", T("Apoyar el proyecto (donar)"), lambda: __import__("ui.donate", fromlist=["x"]).show(self))
        self.addToolBarBreak()
        self.addToolBar(self.toolbox)

    def _act(self, menu, text, slot, sc=None, icon=None):
        a = QAction(text, self)
        if icon: a.setIcon(get_icon(icon))
        if sc: a.setShortcut(sc)
        a.triggered.connect(slot)
        if menu: menu.addAction(a)
        return a

    READONLY_TOOLS = ("select", "lasso", "txtsel", "ocr_region", "hand", "measure")

    def _toggle_qrlens(self):
        self.toolbox.activate(T_SELECT if self.toolbox.current == T_QRLENS else T_QRLENS)

    def _tool_changed(self, t):
        if self._viewer and self._viewer.readonly and t not in self.READONLY_TOOLS:
            QMessageBox.information(self, T("Documento protegido"),
                                    T("El autor de este documento no permite añadirle anotaciones.\n"
                                    "Puedes leerlo, buscar y seleccionar texto."))
            t = "select"
            self.toolbox.activate(t)
        if t == "signature":
            from dialogs.signature import SignatureDialog
            from ui.canvas import PageCanvas
            dlg = SignatureDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_b64:
                PageCanvas.pending_signature = dlg.result_b64
                self._status(T("Haz clic donde quieras colocar la firma (puedes firmar varias páginas). V para terminar."))
            else:
                t = "select"
                self.toolbox.activate(t)
                return
        if self._viewer: self._viewer.set_tool(t)
        if t == "ocr_region" and self._viewer:
            self._dock_ocr.setVisible(True)
            self._ocr_panel.set_doc(self._viewer.doc, self._viewer.canvases)

    def _delete_sel(self):
        if self._viewer:
            self._viewer.delete_selected()
            self._status(T("Objeto eliminado."))

    def _duplicate(self):
        if not self._viewer: return
        for cv in self._viewer.canvases:
            if cv._sel or cv._sel_multi:
                cv._duplicate()
                break

    def _undo(self):
        if self._viewer:
            self._viewer.undo()
            self._status(T("Deshacer."))

    def _redo(self):
        if self._viewer:
            self._viewer.redo()
            self._status(T("Rehacer."))

    def _go_to_page(self):
        if not self._viewer or not self._viewer.doc: return
        total = len(self._viewer.doc)
        n, ok = QInputDialog.getInt(self, T("Ir a página"), Tf("Página (1-{0}):", total), 1, 1, total, 1)
        if ok:
            self._viewer.jump(n - 1)

    def _quick_step(self, d):
        """Búsqueda rápida: una coincidencia por pulsación (ver ui/quick_find.py)."""
        term = self._quick.currentText().strip()
        if not term: return
        self._qf.step(d, term)
        if self._quick.findText(term) < 0:            # recordar la palabra en la lista
            self._quick.insertItem(0, term); self._quick.setCurrentIndex(0)

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if hasattr(self, "_quick") and obj is self._quick.lineEdit() and ev.type() == QEvent.Type.KeyPress \
                and ev.key() == Qt.Key.Key_Escape:
            self._quick.setEditText(""); self._qf.clear()
            return True
        return super().eventFilter(obj, ev)

    def _compare(self):
        from ui.compare_dialog import compare_with_file
        compare_with_file(self)

    def preferences(self):
        """Preferencias de la aplicación: nombre del autor, paso de rotación y tema."""
        from PyQt6.QtWidgets import QFormLayout, QDialogButtonBox, QSpinBox
        from ui.styles import THEMES, current_theme
        from ui.canvas import PageCanvas
        dlg = QDialog(self); dlg.setWindowTitle(T("Preferencias")); dlg.setMinimumWidth(420); form = QFormLayout(dlg)
        ed = QLineEdit(self._settings.get_author())
        sp = QSpinBox(); sp.setRange(1, 90); sp.setSuffix(" °"); sp.setValue(self._settings.get_rotation_step())
        sp.setToolTip(T("Con Ctrl presionado, al girar un objeto o dibujar una línea/flecha se avanza de este número de grados en grados"))
        cb = QComboBox()
        for key, (name, _) in THEMES.items(): cb.addItem(T(name), key)
        cb.setCurrentIndex(max(cb.findData(current_theme()), 0))
        form.addRow(T("Mi nombre (comentarios y sellos):"), ed)
        form.addRow(T("Ángulos con Ctrl, cada:"), sp)
        form.addRow(T("Tema:"), cb)
        from ui.ruler import Ruler, set_unit
        cb_unit = QComboBox()
        for key, label in (("mm", T("Milímetros (mm)")), ("cm", T("Centímetros (cm)")), ("in", T("Pulgadas (in)"))): cb_unit.addItem(label, key)
        cb_unit.setCurrentIndex(max(cb_unit.findData(Ruler.unit), 0))
        form.addRow(T("Unidades de la regla:"), cb_unit)
        from PyQt6.QtWidgets import QCheckBox
        ck_sg = QCheckBox(T("Ajustar a guías")); ck_sg.setChecked(PageCanvas.snap_guides)
        ck_so = QCheckBox(T("Ajustar a objetos")); ck_so.setChecked(PageCanvas.snap_objects)
        ck_so.setToolTip(T("Bordes y centros de otros objetos y de la página. Mantén Alt para no ajustar."))
        snap_row = QWidget(); hl = QHBoxLayout(snap_row); hl.setContentsMargins(0, 0, 0, 0); hl.addWidget(ck_sg); hl.addWidget(ck_so); hl.addStretch()
        form.addRow(T("Ajuste magnético:"), snap_row)
        from ui import spell_ui
        ck_sp = QCheckBox(T("Revisar la ortografía al escribir (corrector de Windows)")); ck_sp.setChecked(spell_ui.enabled())
        form.addRow(T("Ortografía:"), ck_sp)
        from core.translator import translator
        cb_lang = QComboBox(); cb_lang.addItem("Español", "es"); cb_lang.addItem("English", "eng")
        cb_lang.setCurrentIndex(max(cb_lang.findData(translator.current_lang), 0))
        form.addRow(T("Idioma / Language:"), cb_lang)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Guardar")); bb.button(QDialogButtonBox.StandardButton.Cancel).setText(T("Cancelar"))
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        if ed.text().strip(): self._settings.set_author(ed.text())
        self._settings.set_rotation_step(sp.value()); PageCanvas.rotation_step = sp.value()
        set_unit(cb_unit.currentData())
        spell_ui.set_enabled(ck_sp.isChecked())
        self.set_guide_option("snap_guides", ck_sg.isChecked()); self.set_guide_option("snap_objects", ck_so.isChecked())
        self._status(T("Preferencias guardadas."))
        if cb_lang.currentData() != translator.current_lang:
            translator._s.setValue("language", cb_lang.currentData())
            self._restart_prompt(T("El idioma se aplica al reiniciar. ¿Reiniciar ahora?"))
        elif cb.currentData() != current_theme(): self._set_theme(cb.currentData())

    def _toggle_search(self):
        if not (self._viewer and self._viewer.doc): return
        vis = not self.search_panel.isVisible() or not self.search_panel.search_box.hasFocus()
        self.search_panel.setVisible(vis)
        if vis and self._viewer and self._viewer.doc:
            self.search_panel.set_doc(self._viewer.doc, self._viewer.zoom)
            self.search_panel.search_box.setFocus(); self.search_panel.search_box.selectAll()

    def _on_search_result(self, page_num, rects):
        if self._viewer: self._viewer.highlight_search(page_num, rects)

    def _apply_format(self, f):
        """Barra de formato: estilo para lo próximo que se dibuje y, si hay selección, cambiarla (con deshacer)."""
        from PyQt6.QtGui import QColor
        pr = self._props
        pr.stroke_color, pr.fill_color, pr.line_width, pr.opacity = QColor(f["stroke"]), f["fill"], f["width"], f["opacity"]
        v = self._viewer
        if not v: return
        for cv in v.canvases:
            v._sync(cv)
            targets = cv._sel_multi or ([cv._sel] if cv._sel else [])
            if not targets: continue
            cv._snap()
            for a in targets:
                a.stroke = f["stroke"].name(); a.fill = f["fill"].name() if f["fill"] else None
                a.stroke_width = f["width"]; a.opacity = f["opacity"]
            cv._redraw(); cv._commit()

    def _thumb_overlay(self, i, p, scale):
        """Dibuja en la miniatura los objetos de la página (están en píxeles del zoom del visor)."""
        v = self._viewer
        if not (v and i < len(v.canvases) and v.canvases[i].anns): return
        cv = v.canvases[i]
        p.scale(scale / v.zoom, scale / v.zoom)
        for a in cv.anns:
            sel, a.selected = a.selected, False            # sin marco de selección en la miniatura
            try: cv._draw(p, a)
            finally: a.selected = sel

    def _load_toc(self):
        """Marcadores y adjuntos del PDF en el panel izquierdo; se muestran si existen."""
        if self._attach.load():
            self._dock_att.setVisible(True)
        has = self._toc.load(self._viewer)
        if has: self._dock_toc.setVisible(True)

    def _fill_recent(self):
        m = self._recent_menu; m.clear()
        rec = [p for p in self._settings.get_recent() if os.path.exists(p)]
        for p in rec:
            m.addAction(os.path.basename(p)).triggered.connect(lambda _, p=p: self._open_path(p))
            m.actions()[-1].setToolTip(p)
        if rec:
            m.addSeparator(); m.addAction(T("Borrar lista")).triggered.connect(self._settings.clear_recent)
        else:
            m.addAction(T("(sin archivos recientes)")).setEnabled(False)

    def _set_author(self):
        name, ok = QInputDialog.getText(self, T("Mi nombre"), T("Nombre que aparecerá en comentarios y sellos:"),
                                        text=self._settings.get_author())
        if ok and name.strip(): self._settings.set_author(name)

    def folder_search(self):
        from ui.folder_search import FolderSearchDialog
        if getattr(self, "_fsearch", None) is None:
            self._fsearch = FolderSearchDialog(self, os.path.dirname(self._path) if self._path else self._settings.get_last_dir())
            self._fsearch.open_result.connect(self.open_search_result)
            self._fsearch.find_in_current.connect(lambda: self._viewer.doc and (self.raise_(), self.activateWindow(), self._toggle_search()))
        self._fsearch.show(); self._fsearch.raise_(); self._fsearch.activateWindow()

    def open_search_result(self, path, page, term, case, whole):
        """Abre el PDF (o va a su pestaña), busca el texto y salta a la primera coincidencia de la página."""
        same = lambda a: a and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(path))
        tab = next((i for i in range(self.doc_tabs.count()) if same(self.doc_tabs.widget(i).path)), None)
        if tab is not None: self.doc_tabs.setCurrentIndex(tab)     # ya abierto: no recargar
        else: self._open_path(path)
        if not (self._viewer.doc and self._viewer.path and os.path.samefile(self._viewer.path, path)): return
        sp = self.search_panel
        sp.set_doc(self._viewer.doc); sp.search_box.setText(term)
        sp.cb_case.setChecked(case); sp.cb_word.setChecked(whole); sp.cb_pages.setChecked(True)
        sp.setVisible(True)

        def ir():                                   # cuando termine: saltar a la coincidencia de esa página
            k = next((k for k, (p, _) in enumerate(sp._results) if p == page), None)
            if k is not None: sp._goto(k)
        sp._search(on_done=ir)
        self._viewer.jump(page)
        self.raise_(); self.activateWindow()

    def _choose_stamp(self, text, color):
        from ui.stamps import stamp_b64
        from ui.canvas import PageCanvas
        PageCanvas.pending_signature = stamp_b64(T(text), color)
        self.toolbox.activate("stamp")
        self._status(Tf("Sello «{0}»: haz clic donde colocarlo. V para terminar.", T(text.capitalize())))

    def _choose_fill(self, sym):
        from ui.canvas import PageCanvas
        from ui.canvas_fill import SYMBOLS
        PageCanvas.fill_symbol = sym
        self.toolbox.activate("fill")
        self._status(Tf("Rellenar y firmar: «{0}». Haz clic donde va; el tamaño sigue al tamaño de letra. V para terminar.", T(SYMBOLS[sym][0])))

    def _choose_measure(self, mode):
        from ui.canvas import PageCanvas
        from ui.canvas_measure import MODES, Scale, scale_dialog
        if mode == "scale":
            if scale_dialog(self):
                for cv in (self._viewer.canvases if self._viewer else []): cv.update()
                self._status(Tf("Escala de medición: {0}", Scale.label()))
            return
        PageCanvas.measure_mode = mode
        for cv in (self._viewer.canvases if self._viewer else []): cv._mpoly_reset(); cv._measure = None; cv.update()
        self.toolbox.activate("measure")
        how = T("arrastra de un punto a otro") if mode == "dist" else T("haz clic en cada vértice; doble clic o Intro termina, Retroceso quita el último")
        self._status(Tf("Medir {0}: {1}. Escala: {2}.", T(MODES[mode]).lower(), how, Scale.label()))

    def set_guide_option(self, key, on):
        """Mostrar guías / ajustar a guías / ajustar a objetos (se recuerdan)."""
        from ui.canvas import PageCanvas
        setattr(PageCanvas, key, bool(on)); self._settings.set_bool(key, bool(on))
        a = self._guide_acts.get(key)
        if a and a.isChecked() != bool(on): a.setChecked(bool(on))
        for i in range(self.doc_tabs.count()):
            for cv in self.doc_tabs.widget(i).canvases: cv.update()

    def set_page_layout(self, mode):
        """Una columna, dos páginas o dos páginas con portada (para todas las pestañas; se recuerda)."""
        self._settings.set_str("page_layout", mode)
        if mode in self._layout_acts: self._layout_acts[mode].setChecked(True)
        for i in range(self.doc_tabs.count()): self.doc_tabs.widget(i).set_page_layout(mode)

    def toggle_rulers(self):
        """Muestra u oculta las reglas en todas las pestañas (se recuerda)."""
        from ui.ruler import Ruler
        Ruler.shown = not Ruler.shown
        self._settings.set_rulers_shown(Ruler.shown)
        for i in range(self.doc_tabs.count()): self.doc_tabs.widget(i).set_rulers(Ruler.shown)

    def toggle_night(self):
        """Colores invertidos y suavizados para leer de noche (no cambia el PDF)."""
        from ui.canvas import PageCanvas
        PageCanvas.night = not PageCanvas.night
        for cv in self._viewer.canvases:
            if cv._base is not None: cv._render(); cv._redraw()
        self._status(T("Modo nocturno activado.") if PageCanvas.night else T("Modo nocturno desactivado."))

    def toggle_fullscreen(self):
        """F11: solo el documento; Esc o F11 para salir."""
        bars = [self.menuBar(), self._main_tb, self.toolbox, self.thumbs, self.statusBar(), self.tabs.tabBar()]
        if self.isFullScreen():
            for w, vis in self._fs_state: w.setVisible(vis)
            self.showNormal() if not self._fs_max else self.showMaximized()
            self._esc_fs.setEnabled(False)
        else:
            self._fs_state = [(w, w.isVisible()) for w in bars + [self._dock_toc, self._dock_form, self._dock_ocr]]
            self._fs_max = self.isMaximized()
            for w, _ in self._fs_state: w.setVisible(False)
            self.showFullScreen()
            self._esc_fs.setEnabled(True)

    def doc_properties(self):
        v = self._viewer
        if not (v and v.doc): return
        d, m = v.doc, v.doc.metadata or {}
        r = d[0].rect
        size = os.path.getsize(v.path) if v.path and os.path.exists(v.path) else 0
        fecha = lambda s: f"{s[8:10]}/{s[6:8]}/{s[2:6]} {s[10:12]}:{s[12:14]}" if s and s.startswith("D:") and len(s) >= 14 else (s or "—")
        rows = [("Archivo", v.path or "—"), ("Tamaño", f"{size / 1048576:.2f} MB" if size else "—"),
                ("Título", m.get("title") or "—"), ("Autor", m.get("author") or "—"), ("Asunto", m.get("subject") or "—"),
                ("Palabras clave", m.get("keywords") or "—"), ("Creado con", m.get("creator") or "—"),
                ("Productor PDF", m.get("producer") or "—"), ("Creado", fecha(m.get("creationDate"))),
                ("Modificado", fecha(m.get("modDate"))), ("Versión", m.get("format") or "—"),
                ("Páginas", Tf("{0}  ·  {1} × {2} mm (pág. 1)", len(d), f"{r.width / 72 * 25.4:.0f}", f"{r.height / 72 * 25.4:.0f}")),
                ("Seguridad", m.get("encryption") or T("Sin cifrar")),
                ("Formulario", T("Sí") if d.is_form_pdf else T("No")), ("Marcadores", str(len(d.get_toc()))),
                ("Adjuntos", str(d.embfile_count()))]
        from html import escape
        html = "".join(f"<tr><td style='padding-right:14px;color:gray'>{T(k)}</td><td>{escape(str(val))}</td></tr>" for k, val in rows)
        QMessageBox.about(self, T("Propiedades del documento"), f"<table>{html}</table>")

    def _on_tab(self, i):
        """Las barras, miniaturas y búsqueda del visor no aplican en Operaciones entre PDFs."""
        viewer = i == 0
        for w in (self._main_tb, self.toolbox, self.thumbs):
            w.setVisible(viewer)
        if not viewer: self.search_panel.setVisible(False)

    def _restart_prompt(self, msg):
        from PyQt6.QtCore import QProcess
        if QMessageBox.question(self, APP_NAME, msg) == QMessageBox.StandardButton.Yes and self.close():
            args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
            QProcess.startDetached(sys.executable, args)

    def _set_theme(self, key):
        from PyQt6.QtCore import QProcess
        from ui.styles import current_theme
        if key == current_theme(): return
        qsettings("PDFManager").setValue("theme", key)
        if QMessageBox.question(self, T("Tema"), Tf("El tema se aplica al reiniciar {0}. ¿Reiniciar ahora?", APP_NAME))                 == QMessageBox.StandardButton.Yes and self.close():     # close() pregunta por cambios sin guardar
            args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
            QProcess.startDetached(sys.executable, args)

    def _goto(self, idx):
        if self._viewer and self._viewer.canvases:
            self._viewer.go_to(max(0, min(idx, len(self._viewer.canvases) - 1)))

    def _on_count(self, n):
        self.pg_lbl.setText(f" / {n} ")
        self.pg_spin.setRange(1, max(n, 1))
        self._on_current(0)

    def _on_current(self, i):
        """La página visible cambió: sincroniza el número, las miniaturas y la barra de estado."""
        self.pg_spin.blockSignals(True)
        self.pg_spin.setValue(i + 1)
        self.pg_spin.blockSignals(False)
        self.thumbs.set_current(i)
        self._update_info()

    def _update_info(self):
        v = self._viewer
        if not (v and v.doc):
            self._sb_info.setText("")
            return
        lock = T("   ·   🔒 Protegido") if v.crypt or v.readonly else ""
        self._sb_info.setText(Tf("Página {0} de {1}   ·   {2} %{3}", v.current + 1, len(v.doc), round(v.zoom / 1.5 * 100), lock))

    def _set_zoom(self, z):
        if not self._viewer: return
        cur = self._viewer.current
        self._viewer.zoom_to(z)
        self._viewer.go_to(cur)
        self._zoom_changed()

    def _zoom_changed(self):
        self.zoom_lbl.setText(f"{round(self._viewer.zoom / 1.5 * 100)}%")
        self._update_info()

    def _fit(self, mode):
        if self._viewer and self._viewer.doc:
            self._viewer.fit(mode)
            self._zoom_changed()

    def _status(self, msg): self.statusBar().showMessage(f"  {msg}")

    def _rotate_pages_sig(self, indices, degrees):
        if not (self._viewer and self._viewer.doc): return
        self._viewer.rotate_pages(indices, degrees)
        self._status(Tf("Rotadas {0} página(s) {1}°.", len(indices), degrees))

    def _on_doc_replaced(self):
        """El visor cambió de objeto Document (p. ej. deshacer edición de texto)."""
        doc = self._viewer.doc
        self.thumbs.load(doc)
        self._form_panel.refresh()
        self._load_toc()
        self._ocr_panel.set_doc(doc, self._viewer.canvases)
        self.search_panel.set_doc(doc, self._viewer.zoom)

    def _open_path(self, path):
        if not os.path.exists(path):
            QMessageBox.warning(self, T("Advertencia"), Tf("No se encontró:\n{0}", path))
            return
        self.tabs.setCurrentIndex(0)
        same = lambda a, b: a and b and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
        tab = next((i for i in range(self.doc_tabs.count()) if same(self.doc_tabs.widget(i).path, path)), None)
        if tab is not None:                               # ya abierto: ir a él (y recargar si no tiene cambios)
            self.doc_tabs.setCurrentIndex(tab)
            if self._viewer.dirty: return
            self._viewer.close()
        elif self._viewer.doc is not None:
            self._new_viewer()
        v, pw = self._viewer, None
        while True:
            try:
                v.load(path, pw)
                break
            except PasswordRequired:
                msg = T("Contraseña incorrecta. Inténtalo de nuevo:") if pw is not None else T("Este documento está protegido. Contraseña:")
                pw, ok = QInputDialog.getText(self, T("Contraseña"), msg, QLineEdit.EchoMode.Password)
                if not ok:
                    if self.doc_tabs.count() > 1: self._close_tab(self.doc_tabs.currentIndex())
                    return
        self._settings.set_last_dir(path)
        self._settings.add_recent(path)
        self._refresh_doc_ui()
        self._restore_position(v, path)
        self._status(Tf("Abierto: {0}", path) + (T("   ·   🔒 Protegido: solo lectura") if v.readonly else ""))
        if self._form_panel.count:                # el PDF trae un formulario: mostrar el panel
            self._dock_form.setVisible(True)
            self._status(Tf("Este PDF tiene un formulario ({0} campos): rellénalo en el panel de la derecha.", self._form_panel.count))
        from core.signing import has_signatures
        if has_signatures(v.doc):                     # PDF firmado: mostrar sus firmas y su estado
            self._sigs.load(path, v.crypt["user_pw"] if v.crypt else None)
            self._dock_sigs.setVisible(True); self._dock_sigs.raise_()
            self._status(Tf("Documento con {0} firma(s) digital(es): revisa su estado en el panel Firmas.", self._sigs.count))
        log.info(f"PDF abierto: {path}")

    def _restore_position(self, v, path):
        """Vuelve a la página y al zoom donde se dejó el documento la última vez."""
        pos = self._settings.get_position(path)
        if not pos or not v.doc: return
        page, zoom = pos
        page = max(0, min(page, len(v.doc) - 1))
        if 0.2 <= zoom <= 12 and abs(zoom - v.zoom) > 1e-3:
            v.zoom_to(zoom); self._zoom_changed()
        if page:
            QTimer.singleShot(0, lambda: v.doc and v.go_to(page))      # cuando la vista ya tiene su tamaño
            self._status(Tf("Abierto en la página {0}, donde lo dejaste.", page + 1))

    def open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, T("Abrir PDF"), self._settings.get_last_dir(), T("PDF Files (*.pdf)"))
        if path: self._open_path(path)

    def save_pdf(self) -> bool:
        """Guarda en el archivo actual. Devuelve True si se guardó."""
        if not (self._viewer and self._viewer.doc):
            QMessageBox.warning(self, T("Sin documento"), T("Abre un PDF primero."))
            return False
        if not self._path:
            return self.save_pdf_as()
        return self._save_to(self._path)

    def save_pdf_as(self) -> bool:
        if not (self._viewer and self._viewer.doc): return False
        default = self._path or os.path.join(self._settings.get_last_dir(), "documento.pdf")
        path, _ = QFileDialog.getSaveFileName(self, T("Guardar como"), default, T("PDF Files (*.pdf)"))
        if not path: return False
        if not self._save_to(path): return False
        self._path = path
        self._settings.set_last_dir(path)
        self._settings.add_recent(path)
        self.setWindowTitle(f"{APP_NAME} — {os.path.basename(path)}")
        return True

    def _save_to(self, path) -> bool:
        from core.signing import has_signatures
        if has_signatures(self._viewer.doc) and QMessageBox.question(
                self, T("Documento firmado"), T("Este PDF tiene firmas digitales: guardar cambios las invalidará.\n\n"
                "¿Guardar de todas formas? (Para conservar el original firmado, usa «Guardar como» con otro nombre.)")) \
                != QMessageBox.StandardButton.Yes:
            return False
        if self._viewer.readonly:
            QMessageBox.information(self, T("Documento protegido"),
                                    T("El autor de este documento no permite modificarlo, así que no se puede guardar."))
            return False
        warn = crypt_warning(self._viewer.crypt)
        if warn and not getattr(self._viewer, "_crypt_ok", False):
            if QMessageBox.question(self, T("Documento con contraseña"), warn + T("\n\n¿Guardar?")) \
                    != QMessageBox.StandardButton.Yes:
                return False
            self._viewer._crypt_ok = True
        try:
            self._viewer.save(path)
            self._tab_title(self._viewer)
        except PermissionError:
            log.error(f"Guardar {path}: archivo en uso")
            QMessageBox.critical(self, T("No se pudo guardar"),
                Tf("El archivo está abierto en otro programa:\n{0}\n\nCiérralo o usa «Guardar como…».", path))
            return False
        except Exception as e:
            log.exception(f"Guardar {path}")
            QMessageBox.critical(self, T("No se pudo guardar"), f"{path}\n\n{e}")
            return False
        self._status(Tf("Guardado: {0}", path))
        return True

    def _confirm_discard(self) -> bool:
        """Si hay cambios sin guardar, pregunta. True = se puede continuar."""
        if not (self._viewer and self._viewer.doc and self._viewer.dirty):
            return True
        mb = QMessageBox(self)
        mb.setWindowTitle(T("Cambios sin guardar"))
        mb.setText(Tf("¿Guardar los cambios en «{0}»?", os.path.basename(self._path or 'documento')))
        mb.setIcon(QMessageBox.Icon.Question)
        btn_save = mb.addButton(T("Guardar"), QMessageBox.ButtonRole.AcceptRole)
        mb.addButton(T("No guardar"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = mb.addButton(T("Cancelar"), QMessageBox.ButtonRole.RejectRole)
        mb.setDefaultButton(btn_save)
        mb.exec()
        clicked = mb.clickedButton()
        if clicked is btn_cancel: return False
        if clicked is btn_save: return self.save_pdf()
        return True

    def close_pdf(self):
        self._close_tab(self.doc_tabs.currentIndex())

    # ── pestañas de documentos ────────────────────────────────────────────
    @property
    def _viewer(self):
        return self.doc_tabs.currentWidget() if hasattr(self, "doc_tabs") else None

    @property
    def _path(self):
        return self._viewer.path if self._viewer else None

    @_path.setter
    def _path(self, p):
        if self._viewer: self._viewer.path = p

    def _new_viewer(self):
        """Pestaña nueva con un visor; sus señales solo actúan si es la pestaña activa."""
        v = Viewer(self._props)
        def on(sig, fn): sig.connect(lambda *a, v=v: v is self._viewer and fn(*a))
        on(v.count_changed, self._on_count)
        on(v.current_changed, self._on_current)
        on(v.wheel_zoom, lambda d: self.zoom_in() if d > 0 else self.zoom_out())
        on(v.doc_replaced, self._on_doc_replaced)
        on(v.pages_changed, lambda: self.thumbs.load(v.doc))
        on(v.toc_changed, lambda: self._toc.load(v))
        on(v.annotations_changed, lambda: self._dock_comments.isVisible() and self._comments.schedule())
        on(v.annotations_changed, lambda: self._thumb_timer.start())       # miniaturas con los objetos al día
        v.annotations_changed.connect(lambda v=v: self._tab_title(v))
        v.open_requested.connect(self.open_pdf)
        i = self.doc_tabs.addTab(v, get_icon("pdf_doc"), T("Inicio"))
        self.doc_tabs.setCurrentIndex(i)
        return v

    def _tab_title(self, v):
        i = self.doc_tabs.indexOf(v)
        if i < 0: return
        name = os.path.basename(v.path) if v.path else T("Inicio")
        self.doc_tabs.setTabText(i, ("• " if v.dirty else "") + name)
        self.doc_tabs.setTabToolTip(i, v.path or "")

    def _refresh_doc_ui(self):
        """Pone paneles, título y barras al día con el documento de la pestaña activa."""
        v = self._viewer
        doc = v.doc if v else None
        Ann.SCALE = v.zoom
        if doc: self.thumbs.load(doc)
        else: self.thumbs.clear()
        self.setWindowTitle(f"{APP_NAME} — {os.path.basename(v.path)}" if doc and v.path else APP_TITLE)
        self._ocr_panel.set_doc(doc, v.canvases)
        self.search_panel.set_doc(doc)
        self._load_toc()
        self._form_panel.set_viewer(v)
        self._comments.set_viewer(v)
        self.pg_lbl.setText(f" / {len(doc) if doc else 0} ")
        self.pg_spin.setRange(1, max(len(doc) if doc else 1, 1))
        self._tab_title(v)
        for a in getattr(self, "_doc_find", []): a.setEnabled(bool(doc))     # buscar en el documento: solo con uno abierto
        if hasattr(self, "_btn_search"): self._btn_search.setEnabled(bool(doc))
        for w_ in (getattr(self, "_quick", None), getattr(self, "_quick_prev", None), getattr(self, "_quick_next", None)):
            if w_ is not None: w_.setEnabled(bool(doc))
        if hasattr(self, "_qf"): self._qf.reset()
        if not doc: self.search_panel.hide()
        self._zoom_changed()
        self._on_current(v.current)

    def _on_doc_tab(self, i):
        v = self._viewer
        if not v or not hasattr(self, "pg_spin"): return
        Ann.SCALE = v.zoom
        for cv in v.canvases:                     # el zoom de texto es global: redibujar con el de esta pestaña
            if cv._base is not None: cv._redraw()
        v.set_tool(getattr(self.toolbox, "current", "select"))
        self._refresh_doc_ui()

    def _close_tab(self, i):
        v = self.doc_tabs.widget(i)
        if v is None: return
        if v.doc and v.dirty:
            self.doc_tabs.setCurrentIndex(i)
            if not self._confirm_discard(): return
        # primero quitar la pestaña (los paneles pasan al documento siguiente) y después cerrar el PDF:
        # al revés, miniaturas/búsqueda alcanzaban a usar el documento ya cerrado y la app se caía
        self.doc_tabs.removeTab(i)
        if self.doc_tabs.count() == 0: self._new_viewer()
        self._refresh_doc_ui()
        v.close()
        v.deleteLater()

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(".pdf") for u in ev.mimeData().urls()):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for u in ev.mimeData().urls():
            if u.toLocalFile().lower().endswith(".pdf"): self._open_path(u.toLocalFile())

    def print_pdf(self):
        if not (self._viewer and self._viewer.doc):
            QMessageBox.warning(self, T("Sin PDF"), T("Abre un PDF primero."))
            return
        self._viewer.print_doc()

    def zoom_in(self):
        if self._viewer: self._set_zoom(min(self._viewer.zoom + 0.25, 6.0))

    def zoom_out(self):
        if self._viewer: self._set_zoom(max(self._viewer.zoom - 0.25, 0.25))

    def zoom_reset(self):
        self._set_zoom(1.5)

    SHORTCUTS = [
        ("Archivo", [("Ctrl+O", "Abrir"), ("Ctrl+S", "Guardar"), ("Ctrl+Shift+S", "Guardar como"), ("Ctrl+P", "Imprimir")]),
        ("Edición", [("Ctrl+Z / Ctrl+Shift+Z", "Deshacer / Rehacer"), ("Ctrl+C / Ctrl+X / Ctrl+V", "Copiar / Cortar / Pegar"),
                     ("Ctrl+D", "Duplicar objeto"), ("Supr", "Eliminar objeto"), ("Ctrl+A", "Seleccionar todo"),
                     ("Flechas (Shift = ×10)", "Mover objeto")]),
        ("Leer en voz alta", [("Ctrl+Shift+V", "Leer esta página"), ("Ctrl+Shift+B", "Leer hasta el final del documento"),
                              ("Ctrl+Shift+P / Ctrl+Shift+E", "Pausar o continuar / Detener")]),
        ("Vista", [("Ctrl+F", "Buscar"), ("Ctrl+G", "Ir a página"), ("Ctrl++ / Ctrl+-", "Zoom"), ("Ctrl+0", "Zoom 100 %"), ("Ctrl+R", "Reglas"), ("Ctrl+;", "Mostrar guías"), ("Alt (mantener)", "No ajustar al mover/dibujar")]),
        ("Herramientas", [("V / L / S / N / Q", "Seleccionar / Lazo / Texto / Mano / Medir"), ("T / X / M / H", "Texto / Caja / Comentario / Resaltar"),
                          ("I / A / D", "Línea / Flecha / Doble flecha"), ("R / U / C / G / F", "Rect. / Redondeado / Círculo / Triángulo / Figura flecha"),
                          ("P / O", "Imagen / Región OCR"), ("J", "Rellenar y firmar"),
                          ("Medir: Intro / Retroceso / Esc", "Terminar / quitar el último vértice / borrar")]),
        ("Ayuda", [("F1", "Ayuda de la ventana, panel o herramienta que estás usando"), ("Shift+F1", "Centro de ayuda (con buscador)"),
                   ("Ctrl+F1", "Atajos de teclado")]),
    ]

    def shortcuts_help(self):
        rows = "".join(f"<tr><td colspan=2><b>{T(g)}</b></td></tr>" +
                       "".join(f"<tr><td style='padding-right:18px'><code>{k}</code></td><td>{T(d)}</td></tr>" for k, d in items)
                       for g, items in self.SHORTCUTS)
        QMessageBox.about(self, T("Atajos de teclado"), Tf("<table cellspacing=3>{0}</table>", rows))

    def user_guide(self):
        """Abre la guía de usuario (PDF) en una pestaña de PDFRapid, en el idioma de la interfaz."""
        from core import guide, i18n
        try:
            self._open_path(guide.guide_pdf(i18n.lang()))
        except Exception as e:
            log.exception("guía de usuario")
            QMessageBox.warning(self, T("Guía de usuario"), Tf("No se pudo abrir la guía:\n{0}", e))

    def open_legal(self):
        """Carpeta con la política de privacidad (junto al .exe, o docs/legal en desarrollo)."""
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.join(base, "legal")))

    def about(self):
        QMessageBox.about(self, Tf("Acerca de {0}", APP_NAME),
            Tf("<h3>{0} {1}</h3><p>{2}.</p><p>Visor y editor de PDF libre: anotaciones, OCR y operaciones entre documentos.</p><p><b>Autor:</b> Fernando Erazo<br><b>Desarrollado con la asistencia de:</b> Claude (Anthropic)</p><p>© 2026 Fernando Erazo. Software libre bajo la licencia <a href='https://www.gnu.org/licenses/agpl-3.0.html'>GNU AGPL v3</a> o posterior; se distribuye SIN NINGUNA GARANTÍA.</p><p><b>Basado en:</b> PyMuPDF · pypdf · PyQt6</p>", APP_NAME, APP_VERSION, APP_TAGLINE)
            + Tf("<p><b>Código fuente:</b> <a href='{0}'>{0}</a></p>", SOURCE_URL)
            + Tf("<p>¿Te es útil? <a href='{0}'>Apoya el proyecto con una donación</a>.</p>", DONATE_URL))

    def autosave_all(self):
        for i in range(self.doc_tabs.count()): self.doc_tabs.widget(i).autosave()

    def _offer_recovery(self):
        """Al iniciar: ofrecer los cambios autoguardados de una sesión que se cerró de forma inesperada."""
        from core import recovery
        items = recovery.pending()
        if not items: return
        names = "\n".join("  • " + (os.path.basename(r["path"]) or T("(sin nombre)")) for r in items)
        ans = QMessageBox.question(self, APP_NAME, Tf("{0} se cerró de forma inesperada. Hay cambios sin guardar de:\n\n{1}\n\n¿Recuperarlos?", APP_NAME, names))
        if ans != QMessageBox.StandardButton.Yes:
            for r in items: recovery.remove(r["uid"])
            return
        for r in items:
            try:
                self._restore(r)
            except Exception as e:
                log.exception("recuperar")
                QMessageBox.warning(self, T("Advertencia"), Tf("No se pudo recuperar {0}:\n{1}", r["path"], e))
            recovery.remove(r["uid"])

    def _restore(self, r):
        if r["pdf"]:                                     # el contenido del PDF había cambiado: abrir la copia
            if self._viewer.doc is not None: self._new_viewer()
            v = self._viewer; v.load(r["pdf"]); v.path = r["path"] or None
            v._doc_rev = 1
            self._refresh_doc_ui()
        elif r["path"] and os.path.exists(r["path"]):
            self._open_path(r["path"]); v = self._viewer
            if os.path.normcase(os.path.abspath(v.path or "")) != os.path.normcase(os.path.abspath(r["path"])): return
        else:
            raise FileNotFoundError(r["path"])
        for i, cv in enumerate(v.canvases):
            cv.anns_from_page(r["pages"].get(i, []))
            if cv._base is not None: cv._redraw()
        v._mark_dirty(); self._tab_title(v)
        self._status(Tf("Recuperado: {0} (sin guardar)", r["path"]))

    def closeEvent(self, ev):
        try:
            for i in range(self.doc_tabs.count()):        # preguntar por cada documento con cambios
                v = self.doc_tabs.widget(i)
                if v.doc and v.dirty:
                    self.doc_tabs.setCurrentIndex(i)
                    if not self._confirm_discard():
                        ev.ignore()
                        return
            merge = getattr(self, "_merge_tab", None)
            if merge is not None and hasattr(merge, "confirm_close") and not merge.confirm_close():
                ev.ignore()
                return
            from core import recovery
            for i in range(self.doc_tabs.count()):
                self.doc_tabs.widget(i).remember_position()
                recovery.remove(self.doc_tabs.widget(i).uid)
            log.info(f"{APP_NAME} {APP_VERSION} cerrado")
            ev.accept()
        except Exception:
            log.exception("closeEvent")
            ev.accept()
