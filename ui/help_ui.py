# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Ayuda dentro de la app: Centro de ayuda (con buscador), botón ? en cada ventana y F1 según lo que se esté usando.
El contenido sale de core/help.py (docs/guia/ayuda.json), el mismo que la guía en PDF."""
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QDockWidget, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QSplitter, QTextBrowser, QToolButton, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)
from core import help as helpdoc
from core.i18n import T, lang
from ui.icons import get_icon

# ventana o panel (nombre de la clase) → ficha
CLASS_TOPICS = {
    "DonateDialog": "donar",
    "BatchDialog": "lotes", "GeometryDialog": "organizar", "CompareDialog": "comparar", "ProtectDialog": "proteger",
    "LinkDialog": "enlaces", "FieldDialog": "formularios", "FormPanel": "formularios", "CommentsPanel": "comentarios",
    "PageCropDialog": "recortar", "FolderSearchDialog": "buscar_carpeta", "PrintDialog": "imprimir",
    "SignDialog": "firma_digital", "SignaturesPanel": "firma_digital", "ColorPickerDialog": "formato",
    "CropDialog": "imagen", "PropsDialog": "formato", "SignatureDialog": "firma_manuscrita", "TextDialog": "texto",
    "OcrPanel": "ocr", "SearchPanel": "buscar", "BookmarksPanel": "marcadores", "AttachmentsPanel": "adjuntos",
    "Thumbs": "miniaturas", "Ruler": "reglas_guias", "PDFMergeWidget": "operaciones", "DocPanel": "operaciones",
    "OperationsPanel": "operaciones", "SplitDialog": "operaciones", "MergeManyDialog": "operaciones",
    "PagePreview": "operaciones", "QrLens": "qr",
}
# ventanas sin clase propia: título (texto original en español) → ficha
TITLE_TOPICS = {
    "Escala de medición": "medir", "Voz y velocidad": "leer_voz",
    "Detectar campos de formulario": "formularios", "Mis iniciales": "rellenar_firmar",
    "Convertir imagen en objeto": "imagenes_pdf", "Reemplazar imagen": "imagenes_pdf", "Guardar imagen": "imagenes_pdf",
    "Eliminar imagen": "imagenes_pdf",
    "Comprimir PDF": "comprimir", "Exportar a Word": "exportar", "Exportar páginas como imágenes": "exportar",
    "Enlaces del documento": "enlaces", "Marcar texto para tachado": "tachado", "Aplicar tachado definitivo": "tachado",
    "Marca de agua": "marca_agua", "Numeración de páginas / Bates": "numeracion", "Encabezado, pie y numeración": "numeracion",
    "Fondo de página": "fondo",
    "Propiedades del documento": "propiedades", "Preferencias": "preferencias", "Seleccionar rango": "miniaturas",
    "Procesar por lotes": "lotes", "Agregar comentario": "comentarios", "Editar comentario": "comentarios",
    "Editar texto": "texto", "Editar texto del documento": "texto", "Firmar": "firma_manuscrita",
    "Firmar con certificado digital": "firma_digital", "Imprimir": "imprimir", "Recortar imagen": "imagen",
    "Posición y tamaño": "organizar", "Combinar varios PDFs": "operaciones", "Dividir PDF": "operaciones",
    "Enlace": "enlaces", "Resumen de comentarios": "comentarios", "Proteger con contraseña": "proteger", "Recortar páginas": "recortar",
}
# herramienta activa en la página → ficha
TOOL_TOPICS = {
    "select": "seleccionar", "lasso": "seleccionar", "txtsel": "seleccionar", "hand": "seleccionar",
    "measure": "medir", "text": "texto", "textbox": "texto", "comment": "comentarios", "highlight": "resaltar",
    "line": "dibujo", "arrow": "dibujo", "darrow": "dibujo", "ink": "dibujo", "rect": "dibujo", "rrect": "dibujo",
    "circle": "dibujo", "triangle": "dibujo", "arrow_shape": "dibujo", "image": "imagen",
    "signature": "firma_manuscrita", "stamp": "sellos", "redact": "tachado", "ocr_region": "ocr", "qrlens": "qr",
    "fill": "rellenar_firmar",
}


def _canvas_topic(cv):
    if cv.tool == "select" and (cv._sel or cv._sel_multi): return "organizar"
    return TOOL_TOPICS.get(cv.tool, "seleccionar")


def topic_for(w) -> str:
    """Ficha de lo que el usuario está usando: el widget con el foco o la ventana, subiendo por sus contenedores."""
    titles = {T(k): v for k, v in TITLE_TOPICS.items()}
    while w is not None:
        name = type(w).__name__
        if name == "PageCanvas": return _canvas_topic(w)
        if name == "ToolsBar":
            v = getattr(w.window(), "_viewer", None)
            return TOOL_TOPICS.get(getattr(v, "tool", ""), "seleccionar")
        if name in CLASS_TOPICS: return CLASS_TOPICS[name]
        if isinstance(w, QDockWidget) and w.widget() is not None and type(w.widget()).__name__ in CLASS_TOPICS:
            return CLASS_TOPICS[type(w.widget()).__name__]
        if isinstance(w, QDialog):
            return titles.get(w.windowTitle())
        if hasattr(w, "tabs") and hasattr(w, "_viewer"):          # ventana principal sin foco en nada concreto
            if getattr(w, "_merge_tab", None) is not None and w.tabs.currentWidget() is w._merge_tab:
                return "operaciones"
            return TOOL_TOPICS.get(getattr(w._viewer, "tool", ""), "inicio") if w._viewer and w._viewer.doc else "inicio"
        w = w.parentWidget()
    return None


class HelpCenter(QDialog):
    """Centro de ayuda: fichas por grupos, buscador y acceso a la guía completa."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Centro de ayuda")); self.resize(880, 600); self.setSizeGripEnabled(True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        lay = QVBoxLayout(self)
        self.search = QLineEdit(); self.search.setPlaceholderText(T("Buscar en la ayuda (por ejemplo: firmar, tabla, contraseña)"))
        self.search.setClearButtonEnabled(True); self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        sp = QSplitter(); lay.addWidget(sp, 1)
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True); self.tree.setMinimumWidth(230)
        self.tree.currentItemChanged.connect(lambda it, _: it and it.data(0, Qt.ItemDataRole.UserRole) and self.show_topic(it.data(0, Qt.ItemDataRole.UserRole), False))
        self.view = QTextBrowser(); self.view.setOpenExternalLinks(False)
        sp.addWidget(self.tree); sp.addWidget(self.view); sp.setStretchFactor(1, 1); sp.setSizes([250, 630])
        row = QHBoxLayout()
        bg = QPushButton(get_icon("pdf_doc"), T("Guía completa (PDF)")); bg.clicked.connect(self._guide); self.btn_guide = bg
        bk = QPushButton(T("Atajos de teclado")); bk.clicked.connect(self._keys)
        bc = QPushButton(T("Cerrar")); bc.clicked.connect(self.close)
        row.addWidget(bg); row.addWidget(bk); row.addStretch(1); row.addWidget(bc); lay.addLayout(row)
        self._items = {}
        self._fill(None)

    def _fill(self, ids):
        self.tree.blockSignals(True); self.tree.clear(); self._items = {}
        lg = lang()
        for gid, gname in helpdoc.groups(lg):
            topics = [t for t in helpdoc.topics(gid) if ids is None or t["id"] in ids]
            if not topics: continue
            g = QTreeWidgetItem([gname]); f = g.font(0); f.setBold(True); g.setFont(0, f)
            g.setFlags(g.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(g)
            for t in topics:
                it = QTreeWidgetItem([helpdoc.title(t["id"], lg)]); it.setData(0, Qt.ItemDataRole.UserRole, t["id"])
                g.addChild(it); self._items[t["id"]] = it
            g.setExpanded(True)
        self.tree.blockSignals(False)

    def _filter(self, text):
        ids = helpdoc.search(text, lang()) if text.strip() else None
        self._fill(ids)
        if ids: self.show_topic(ids[0])
        elif ids == []: self.view.setHtml(f"<p>{T('No se encontró nada. Prueba con otra palabra.')}</p>")

    def show_topic(self, tid, select=True):
        if not helpdoc.topic(tid): tid = "inicio"
        self.view.setHtml(helpdoc.to_html(tid, lang()))
        if select and tid in self._items:
            self.tree.blockSignals(True); self.tree.setCurrentItem(self._items[tid]); self.tree.blockSignals(False)

    def _owner(self):
        return getattr(self, "_guide_owner", None) or _main_window()

    def _guide(self):
        w = self._owner()
        if w is not None: w.user_guide()

    def _keys(self):
        w = self._owner()
        if w is not None: w.shortcuts_help()


def _is_main(w):
    return w is not None and hasattr(w, "user_guide") and hasattr(w, "_viewer")


def _main_window(start=None):
    """Ventana principal de la que cuelga `start` (o la ventana activa); si no, la primera visible."""
    w = start or QApplication.activeWindow()
    while w is not None:
        if _is_main(w): return w
        w = w.parentWidget()
    tops = [w for w in QApplication.topLevelWidgets() if _is_main(w)]
    return next((w for w in tops if w.isVisible()), tops[0] if tops else None)


def show_help(tid=None, parent=None):
    """Abre el Centro de ayuda (no modal, uno solo) en la ficha `tid`."""
    win = parent or _main_window()
    modal = QApplication.activeModalWidget()
    if modal is not None and not isinstance(modal, HelpCenter):
        dlg = HelpCenter(modal)                 # hija de la ventana modal: si no, la modal bloquearía sus clics
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.btn_guide.hide()                    # la guía se abre en una pestaña del visor, que queda detrás de la modal
        dlg._guide_owner = win
    else:
        dlg = getattr(win, "_help_center", None) if win is not None else None
        if dlg is None:
            dlg = HelpCenter(win)
            if win is not None: win._help_center = dlg
        dlg._guide_owner = win
        dlg.search.blockSignals(True); dlg.search.clear(); dlg.search.blockSignals(False); dlg._fill(None)
    dlg.show_topic(tid or "inicio")
    dlg.show(); dlg.raise_(); dlg.activateWindow()
    return dlg


def context_help(widget=None):
    """F1: ayuda de lo que se está usando (widget con el foco o ventana activa)."""
    w = widget or QApplication.focusWidget() or QApplication.activeWindow()
    show_help(topic_for(w) or "inicio", _main_window(w))


def add_button(dlg):
    """Añade «?» a la botonera de una ventana si hay ficha para ella (una sola vez)."""
    if dlg.property("pdfrapid_help") or isinstance(dlg, HelpCenter): return
    tid = topic_for(dlg)
    if not tid: return
    dlg.setProperty("pdfrapid_help", tid)
    dlg.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
    for box in dlg.findChildren(QDialogButtonBox):
        b = box.addButton(QDialogButtonBox.StandardButton.Help)
        b.setText(T("Ayuda")); b.setToolTip(T("Qué hace esta ventana y cómo se usa (F1)"))
        b.clicked.connect(lambda _=False, t=tid: show_help(t, _main_window(dlg)))
        return


def dock_title(dock: QDockWidget, tid: str):
    """Barra de título del panel con «?» (ayuda del panel) y «×» (cerrar)."""
    bar = QWidget(); h = QHBoxLayout(bar); h.setContentsMargins(6, 2, 2, 2); h.setSpacing(2)
    lbl = QLabel(dock.windowTitle()); f = lbl.font(); f.setBold(True); lbl.setFont(f)
    dock.windowTitleChanged.connect(lbl.setText)
    h.addWidget(lbl); h.addStretch(1)
    for icon, tip, fn in (("help", T("Ayuda de este panel (F1)"), lambda: show_help(tid)), ("close", T("Cerrar"), dock.hide)):
        b = QToolButton(); b.setIcon(get_icon(icon, size=14)); b.setAutoRaise(True); b.setToolTip(tip); b.clicked.connect(fn)
        h.addWidget(b)
    dock.setTitleBarWidget(bar)


class HelpFilter(QObject):
    """Para toda la app: «?» en las ventanas al mostrarse y F1 dentro de ellas."""

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.Show and isinstance(obj, QDialog):
            add_button(obj)
        elif t == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_F1 and isinstance(obj, QWidget):
            win = obj.window()
            if isinstance(win, QDialog) and not isinstance(win, HelpCenter):
                if ev.modifiers() == Qt.KeyboardModifier.NoModifier:
                    show_help(topic_for(obj) or topic_for(win) or "inicio", _main_window(win)); return True
        return False


def install(app):
    import atexit
    f = HelpFilter(app); app.installEventFilter(f); app._help_filter = f

    def remove():                       # al cerrar Python, Qt no debe llamar a un filtro que ya no existe
        try:
            app.removeEventFilter(f)
        except RuntimeError:
            pass
    app.aboutToQuit.connect(remove); atexit.register(remove)
    return f
