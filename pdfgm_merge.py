# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""
Pdfgm — Módulo de Operaciones entre PDFs v10.001
- Integración con sistema de traducción (i18n)
- Usa la paleta gris única de ui/styles.py (sin tema oscuro)
- Botón de cierre con detección de cambios (_is_dirty)
- Ejecución independiente o integrada en Pdfgm
"""
from core.i18n import T, Tf
import sys
import os
import pymupdf
from io import BytesIO
import json
from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QAbstractItemView,
    QFileDialog, QMessageBox, QFrame, QStatusBar, QToolBar,
    QDialog, QGroupBox, QSpinBox, QMenu, QDialogButtonBox, QCheckBox, QInputDialog, QLineEdit,
    QSizePolicy, QToolButton, QSlider, QRadioButton, QScrollArea
)
from PyQt6.QtCore import (
    Qt, QSize, QPoint, QMimeData, QByteArray, pyqtSignal,
    QRect, QTimer
)
from PyQt6.QtGui import (
    QPixmap, QImage, QIcon, QPainter, QPen, QBrush, QColor,
    QFont, QDrag
)

# ══════════════════════════════════════════════════════════
# TRADUCTOR Y PALETA (misma fuente que main.py, sin tema oscuro)
# ══════════════════════════════════════════════════════════
from core.translator import translator
from ui.styles import C, SS, MENU_SS
from ui.icons import get_icon
from core.pdf_io import open_pdf, save_pdf, PasswordRequired
from core.pages import parse_ranges, groups_every, groups_ranges, extract as extract_pages, combine as combine_docs

MIME_PAGES = "application/x-pdfgm-pages"

THUMB_W, THUMB_H = 130, 165

# ═════════════════════════════════════════════════════════
# GENERADOR DE MINIATURAS
# ══════════════════════════════════════════════════════════
def make_thumbnail(page: pymupdf.Page, w=THUMB_W, h=THUMB_H) -> QPixmap:
    try:
        pr = page.rect
        scale = min((w - 8) / pr.width, (h - 8) / pr.height)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        pm_page = QPixmap.fromImage(img)
        result = QPixmap(w, h)
        result.fill(Qt.GlobalColor.transparent)
        p = QPainter(result)
        x = (w - pm_page.width()) // 2
        y = (h - pm_page.height()) // 2
        p.fillRect(x + 3, y + 3, pm_page.width(), pm_page.height(), QColor(0, 0, 0, 50))   # sombra
        p.drawPixmap(x, y, pm_page)
        p.setPen(QPen(QColor(C['border']), 1))
        p.drawRect(x, y, pm_page.width() - 1, pm_page.height() - 1)
        p.end()
        return result
    except Exception:
        pm = QPixmap(w, h); pm.fill(Qt.GlobalColor.transparent); return pm


def open_for_pages(parent, path):
    """Abre un PDF pidiendo contraseña si hace falta; None si se cancela o el autor no permite
    reorganizar sus páginas."""
    pw = None
    while True:
        try:
            doc = open_pdf(path, pw)
            break
        except PasswordRequired:
            pw, ok = QInputDialog.getText(parent, T("Contraseña"), Tf("{0} está protegido. Contraseña:", os.path.basename(path)),
                                          QLineEdit.EchoMode.Password)
            if not ok: return None
    if not doc.permissions & pymupdf.PDF_PERM_ASSEMBLE:
        doc.close()
        QMessageBox.information(parent, T("Documento protegido"),
                                Tf("El autor de {0} no permite reorganizar ni extraer sus páginas.", os.path.basename(path)))
        return None
    return doc


def _blank_thumb(w=THUMB_W, h=THUMB_H) -> QPixmap:
    pm = QPixmap(w, h); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setPen(QPen(QColor(C['border']), 1))
    p.fillRect(14, 4, w - 28, h - 8, QColor(C['white'])); p.drawRect(14, 4, w - 29, h - 9); p.end()
    return pm

# ══════════════════════════════════════════════════════════
# ITEM DE PÁGINA DRAG & DROP
# ══════════════════════════════════════════════════════════
class PageItem(QListWidgetItem):
    def __init__(self, page_num: int, total: int, thumb: QPixmap, doc_id: int):
        super().__init__()
        self.page_num = page_num; self.doc_id = doc_id
        self.setText(str(page_num + 1))
        self.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip(Tf("Página {0} de {1}", page_num + 1, total))
        self.set_thumb(thumb)
    def set_thumb(self, thumb):
        """`thumb` = None: miniatura aún no generada (se genera al hacerse visible)."""
        self._thumb = thumb
        self.setIcon(QIcon(thumb if thumb is not None else _blank_thumb()))
    @property
    def thumb(self) -> QPixmap: return self._thumb if self._thumb is not None else self.icon().pixmap(THUMB_W, THUMB_H)

# ══════════════════════════════════════════════════════════
# LISTA DE PÁGINAS CON DRAG & DROP
# ══════════════════════════════════════════════════════════
class PageList(QListWidget):
    pages_dropped = pyqtSignal(object, list, int, bool)
    file_dropped = pyqtSignal(str)       # PDF arrastrado desde el Explorador
    def __init__(self, doc_id: int, parent=None):
        super().__init__(parent)
        self.doc_id = doc_id; self.doc = None; self._drop_idx = -1; self._drag_src = None
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(THUMB_W, THUMB_H))
        self.setGridSize(QSize(THUMB_W + 16, THUMB_H + 30))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Snap)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(True); self.setSpacing(4)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True); self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.verticalScrollBar().valueChanged.connect(self._render_visible)
        self.tw = THUMB_W

    def set_thumb_size(self, w: int):
        """Cambia el tamaño de las miniaturas (se regeneran las visibles)."""
        self.tw = w
        h = int(w * THUMB_H / THUMB_W)
        self.setIconSize(QSize(w, h)); self.setGridSize(QSize(w + 16, h + 30))
        for i in range(self.count()): self.item(i).set_thumb(None)
        QTimer.singleShot(0, self._render_visible)

    @staticmethod
    def _pdf_urls(md):
        return [u.toLocalFile() for u in md.urls() if u.toLocalFile().lower().endswith(".pdf")] if md.hasUrls() else []

    def load_doc(self, doc: pymupdf.Document):
        """Crea las entradas al instante; las miniaturas se generan al hacerse visibles."""
        self.doc = doc; self.clear(); total = len(doc)
        for i in range(total):
            self.addItem(PageItem(i, total, None, self.doc_id))
        QTimer.singleShot(0, self._render_visible)

    def _render_visible(self):
        if not self.doc or self.doc.is_closed or not self.count(): return
        n = len(self.doc)                                   # la lista puede ir un paso por detrás del documento
        vp = self.viewport().rect()
        first = self.indexAt(QPoint(4, 4)).row()
        first = max(first, 0)
        hits = 0
        for i in range(first, self.count()):
            it = self.item(i)
            if not self.visualItemRect(it).intersects(vp):
                if hits: break
                continue
            hits += 1
            if it._thumb is None and i < n:
                it.set_thumb(make_thumbnail(self.doc[i], self.tw, int(self.tw * THUMB_H / THUMB_W)))
        for i in range(self.count()):                       # liberar las lejanas
            it = self.item(i)
            if it._thumb is not None and abs(i - first) > 300:
                it.set_thumb(None)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        QTimer.singleShot(0, self._render_visible)

    def selected_page_nums(self) -> list:
        return sorted(self.row(it) for it in self.selectedItems())

    def startDrag(self, supported_actions):
        selected = self.selected_page_nums()
        if not selected: return
        mime = QMimeData()
        data = json.dumps({"doc_id": self.doc_id, "pages": selected})
        mime.setData(MIME_PAGES, QByteArray(data.encode()))
        first_item = self.item(selected[0])
        if first_item:
            pm = first_item.thumb.scaled(80, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            if len(selected) > 1:
                badge_pm = QPixmap(pm.size()); badge_pm.fill(Qt.GlobalColor.transparent)
                bp = QPainter(badge_pm); bp.drawPixmap(0, 0, pm)
                bp.setBrush(QBrush(QColor(C['accent']))); bp.setPen(Qt.PenStyle.NoPen)
                bp.drawEllipse(pm.width() - 22, 0, 22, 22)
                bp.setPen(QPen(QColor("white"))); bp.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                bp.drawText(QRect(pm.width()-22, 0, 22, 22), Qt.AlignmentFlag.AlignCenter, str(len(selected)))
                bp.end(); pm = badge_pm
        drag = QDrag(self); drag.setMimeData(mime); drag.setPixmap(pm)
        drag.setHotSpot(QPoint(pm.width() // 2, pm.height() // 2))
        self._drag_src = self
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        self._drop_idx = -1; self.update()

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(MIME_PAGES) or self._pdf_urls(ev.mimeData()): ev.acceptProposedAction()
        else: ev.ignore()

    def dragMoveEvent(self, ev):
        if ev.mimeData().hasFormat(MIME_PAGES):
            ev.acceptProposedAction()
            pos = ev.position().toPoint(); idx = self._drop_position(pos)
            if idx != self._drop_idx: self._drop_idx = idx; self.update()
        elif self._pdf_urls(ev.mimeData()): ev.acceptProposedAction()
        else: ev.ignore()

    def dragLeaveEvent(self, ev): self._drop_idx = -1; self.update()

    def dropEvent(self, ev):
        urls = self._pdf_urls(ev.mimeData())
        if urls and not ev.mimeData().hasFormat(MIME_PAGES):
            ev.acceptProposedAction(); self.file_dropped.emit(urls[0]); return
        if not ev.mimeData().hasFormat(MIME_PAGES): ev.ignore(); return
        data = json.loads(bytes(ev.mimeData().data(MIME_PAGES)).decode())
        src_doc_id = data["doc_id"]; page_nums = data["pages"]
        insert_idx = self._drop_idx if self._drop_idx >= 0 else self.count()
        move = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self._drop_idx = -1; self.update()
        if src_doc_id == self.doc_id: self.pages_dropped.emit(self, page_nums, insert_idx, False)
        else: self.pages_dropped.emit(self, page_nums, insert_idx, move)
        ev.acceptProposedAction()

    def _drop_position(self, pos: QPoint) -> int:
        item = self.itemAt(pos)
        if item is None: return self.count()
        idx = self.row(item); rect = self.visualItemRect(item)
        if pos.x() > rect.center().x(): idx += 1
        return idx

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._drop_idx < 0: return
        p = QPainter(self.viewport()); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(C['drop_ok']), 3); pen.setStyle(Qt.PenStyle.SolidLine); p.setPen(pen)
        if self._drop_idx == 0:
            if self.count() > 0:
                r = self.visualItemRect(self.item(0)); x = r.left() - 4
                p.drawLine(x, r.top() + 4, x, r.bottom() - 4)
            else: p.drawLine(8, 8, 8, self.viewport().height() - 8)
        elif self._drop_idx >= self.count():
            last = self.item(self.count() - 1)
            if last: r = self.visualItemRect(last); x = r.right() + 4; p.drawLine(x, r.top() + 4, x, r.bottom() - 4)
        else:
            item = self.item(self._drop_idx - 1)
            if item: r = self.visualItemRect(item); x = r.right() + 4; p.drawLine(x, r.top() + 4, x, r.bottom() - 4)
        p.end()

# ══════════════════════════════════════════════════════════
# PANEL DE UN DOCUMENTO
# ══════════════════════════════════════════════════════════
class DocPanel(QFrame):
    changed = pyqtSignal()
    status = pyqtSignal(str)     # mensajes para la barra de estado (sin ventanas emergentes)
    def __init__(self, doc_id: int, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("panel_frame")
        self.doc_id = doc_id; self.doc = None; self.path = None; self.crypt = None
        self._history = []; self._is_dirty = False  # NUEVO: Bandera de cambios
        self._build_ui(title)

    def _mark_dirty(self):
        self._is_dirty = True
        self.changed.emit()

    def _build_ui(self, title: str):
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 10, 10, 10); lay.setSpacing(8)
        hdr = QHBoxLayout(); hdr.setSpacing(8)
        self.lbl_title = ElidedLabel(title); self.lbl_title.setObjectName("panel_title"); hdr.addWidget(self.lbl_title, 1)
        self.lbl_count = QLabel(translator.tr("no_pages_count", "No document")); self.lbl_count.setObjectName("page_count"); hdr.addWidget(self.lbl_count)
        lay.addLayout(hdr)
        btns = QHBoxLayout(); btns.setSpacing(6)
        self.btn_open = _op_button("open", T("Abrir"), translator.tr("open_pdf_btn", "Open PDF"), self.open_doc); btns.addWidget(self.btn_open)
        self.btn_save = _op_button("save", T("Guardar"), translator.tr("save_btn_doc", "Save"), self.save_doc); btns.addWidget(self.btn_save)
        self.btn_save_as = _op_button("save", T("Guardar como…"), translator.tr("save_as_btn", "Save as…"), self.save_doc_as); btns.addWidget(self.btn_save_as)
        btns.addStretch()
        lay.addLayout(btns)
        self.lbl_path = QLabel(" "); self.lbl_path.hide()     # la ruta se muestra al pasar el ratón por el nombre
        self.lbl_path.setText = lambda t: self.lbl_title.setToolTip(t)
        self.page_list = PageList(self.doc_id)
        self.page_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.page_list.customContextMenuRequested.connect(self._ctx_menu)
        self.page_list.file_dropped.connect(self.open_doc)
        self.page_list.itemDoubleClicked.connect(lambda it: self._preview(self.page_list.row(it)))
        lay.addWidget(self.page_list, 1)
        act_bar = QHBoxLayout(); act_bar.setSpacing(6)
        self.btn_undo = _op_button("undo", T("Deshacer"), translator.tr("undo_page", "Undo"), self.undo); self.btn_undo.setEnabled(False); act_bar.addWidget(self.btn_undo)
        self.btn_more = QToolButton(); self.btn_more.setText(T("Más")); self.btn_more.setObjectName("op_more")
        self.btn_more.setIcon(get_icon("ops")); self.btn_more.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more = QMenu(self.btn_more); more.setStyleSheet(MENU_SS); more.aboutToShow.connect(lambda: self._fill_more(more))
        self.btn_more.setMenu(more); act_bar.addWidget(self.btn_more)
        self.sld_size = QSlider(Qt.Orientation.Horizontal); self.sld_size.setRange(70, 260); self.sld_size.setValue(THUMB_W)
        self.sld_size.setFixedWidth(80); self.sld_size.setToolTip(T("Tamaño de las miniaturas"))
        self.sld_size.valueChanged.connect(lambda v: self._size_timer.start())
        self._size_timer = QTimer(self); self._size_timer.setSingleShot(True); self._size_timer.setInterval(150)
        self._size_timer.timeout.connect(lambda: self.page_list.set_thumb_size(self.sld_size.value()))
        act_bar.addWidget(self.sld_size)
        act_bar.addStretch()
        self.btn_rotate_cw = _op_button("rotate_cw", "", translator.tr("rotate_cw_page", "Rotate 90°"), lambda: self.rotate_selected(90)); act_bar.addWidget(self.btn_rotate_cw)
        self.btn_rotate_ccw = _op_button("rotate_ccw", "", translator.tr("rotate_ccw_page", "Rotate -90°"), lambda: self.rotate_selected(-90)); act_bar.addWidget(self.btn_rotate_ccw)
        self.btn_del_page = _op_button("delete", T("Eliminar"), translator.tr("delete_page", "Delete page"), self.delete_selected, danger=True); act_bar.addWidget(self.btn_del_page)
        lay.addLayout(act_bar)
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool):
        for b in [self.btn_save, self.btn_save_as, self.btn_rotate_cw, self.btn_rotate_ccw, self.btn_del_page, self.btn_more]: b.setEnabled(enabled)

    @property
    def has_doc(self) -> bool: return self.doc is not None

    def open_doc(self, path: str = None):
        if not path: path, _ = QFileDialog.getOpenFileName(self, translator.tr("open_pdf", "🗂 Open PDF…"), os.path.expanduser("~"), T("PDF Files (*.pdf)"))
        if not path: return
        if self.doc and self._is_dirty and QMessageBox.question(
                self, T("Cambios sin guardar"), Tf("¿Descartar los cambios en {0}?", self.lbl_title.text())) \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            doc = open_for_pages(self, path)
            if doc is None: return
            if self.doc: self.doc.close()
            self.doc = doc; self.path = path
            self.crypt = doc.pdfgm_crypt     # se pierde al deshacer (el documento se reabre desde memoria)
            self.lbl_title.setText(os.path.basename(path)); self.lbl_path.setText(path)
            self._update_count(); self.page_list.load_doc(self.doc)
            self._set_enabled(True); self._history.clear(); self.btn_undo.setEnabled(False)
            self._is_dirty = False  # Abrir no es un cambio
            self.changed.emit()
        except Exception as e: QMessageBox.critical(self, translator.tr("error", "Error"), Tf("No se pudo abrir el PDF:\n{0}", e))

    def save_doc(self) -> bool:
        if not self.doc or not self.path: return self.save_doc_as()
        try:
            save_pdf(self.doc, self.path, self.crypt)
            self._is_dirty = False  # Guardar resetea la bandera
            self.status.emit(translator.tr("exported_msg", "PDF saved:\n{path}").format(path=self.path).replace("\n", " "))
            return True
        except Exception as e:
            QMessageBox.critical(self, translator.tr("error", "Error"), Tf("No se pudo guardar:\n{0}", e))
            return False

    def save_doc_as(self) -> bool:
        if not self.doc: return False
        default = self.path or os.path.expanduser("~/documento.pdf")
        path, _ = QFileDialog.getSaveFileName(self, translator.tr("save_as", " Save as…"), default, T("PDF Files (*.pdf)"))
        if not path: return False
        try:
            save_pdf(self.doc, path, self.crypt); self.path = path
            self.lbl_title.setText(os.path.basename(path)); self.lbl_path.setText(path)
            self._is_dirty = False
            self.status.emit(translator.tr("exported_msg", "PDF saved:\n{path}").format(path=path).replace("\n", " "))
            return True
        except Exception as e:
            QMessageBox.critical(self, translator.tr("error", "Error"), str(e))
            return False

    def _snapshot(self):
        if not self.doc: return
        buf = BytesIO(); self.doc.save(buf); self._history.append(buf.getvalue())
        if len(self._history) > 20: self._history.pop(0)
        self.btn_undo.setEnabled(True)

    def undo(self):
        if not self._history: return
        try:
            buf = self._history.pop()
            if self.doc: self.doc.close()
            self.doc = pymupdf.open(stream=buf, filetype="pdf")
            self.page_list.load_doc(self.doc); self._update_count()
            self.btn_undo.setEnabled(bool(self._history)); self.changed.emit()
        except Exception as e: QMessageBox.critical(self, translator.tr("error", "Error"), Tf("No se pudo deshacer:\n{0}", e))

    def _update_count(self):
        if self.doc:
            n = len(self.doc)
            s = translator.tr("s_plural", "s") if n != 1 else translator.tr("s_singular", "")
            self.lbl_count.setText(translator.tr("pages_count", "  {n} page{s}").format(n=n, s=s))
        else: self.lbl_count.setText(translator.tr("no_pages_count", "No document"))

    def insert_pages_from(self, src_doc: pymupdf.Document, page_nums: list, insert_at: int, move: bool = False, src_panel: 'DocPanel' = None):
        if not self.doc: QMessageBox.warning(self, translator.tr("no_document", "No document"), translator.tr("dest_not_open", "The destination document is not open.")); return
        self._snapshot(); self._mark_dirty()
        if src_panel: src_panel._snapshot()
        try:
            at = min(insert_at, len(self.doc))
            for offset, pg_num in enumerate(sorted(page_nums)):
                self.doc.insert_pdf(src_doc, from_page=pg_num, to_page=pg_num, start_at=at + offset)
            if move and src_panel and src_panel.doc:
                for pg_num in sorted(page_nums, reverse=True): src_panel.doc.delete_page(pg_num)
                src_panel.page_list.load_doc(src_panel.doc); src_panel._update_count(); src_panel.changed.emit()
            self.page_list.load_doc(self.doc); self._update_count(); self.changed.emit()
        except Exception as e: QMessageBox.critical(self, translator.tr("error", "Error"), Tf("Error al insertar páginas:\n{0}", e))

    def reorder_pages(self, original_indices: list, insert_at: int):
        if not self.doc: return
        self._snapshot(); self._mark_dirty()
        try:
            n = len(self.doc)
            remaining = [i for i in range(n) if i not in original_indices]
            adj_idx = insert_at - sum(1 for i in original_indices if i < insert_at)
            new_order = remaining[:adj_idx] + original_indices + remaining[adj_idx:]
            self.doc.select(new_order); self.page_list.load_doc(self.doc); self._update_count(); self.changed.emit()
        except Exception as e: QMessageBox.critical(self, translator.tr("error", "Error"), Tf("Error al reordenar:\n{0}", e))

    def rotate_selected(self, degrees: int):
        if not self.doc: return
        sel = self.page_list.selected_page_nums()
        if not sel: QMessageBox.information(self, translator.tr("no_selection_msg", "No selection"), translator.tr("select_pages_to_rotate", "Select pages to rotate.")); return
        self._snapshot(); self._mark_dirty()
        for pg_num in sel:
            page = self.doc[pg_num]; page.set_rotation((page.rotation + degrees) % 360)
        self.page_list.load_doc(self.doc)
        for pg_num in sel: self.page_list.item(pg_num).setSelected(True)   # conservar la selección
        self.changed.emit()

    def delete_selected(self):
        if not self.doc: return
        sel = self.page_list.selected_page_nums()
        if not sel: QMessageBox.information(self, translator.tr("no_selection_msg", "No selection"), translator.tr("select_pages_to_delete", "Select pages to delete.")); return
        if len(sel) >= len(self.doc): QMessageBox.warning(self, translator.tr("warning", "Warning"), translator.tr("cannot_delete_all", "You cannot delete all pages.")); return
        r = QMessageBox.question(self, translator.tr("confirm", "Confirm"), translator.tr("confirm_delete_pages", "Delete {n} page(s) from the document?").format(n=len(sel)), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes: return
        self._snapshot(); self._mark_dirty()
        for pg_num in sorted(sel, reverse=True): self.doc.delete_page(pg_num)
        self.page_list.load_doc(self.doc); self._update_count(); self.changed.emit()

    def _ctx_menu(self, pos):
        sel = self.page_list.selected_page_nums(); menu = QMenu(self); menu.setStyleSheet(MENU_SS)
        if sel:
            n = len(sel)
            hdr = menu.addAction(Tf("  {0} página(s) seleccionada(s)", n)); hdr.setEnabled(False)
            hf = hdr.font(); hf.setBold(True); hdr.setFont(hf); menu.addSeparator()
            menu.addAction(get_icon("rotate_cw"), translator.tr("rotate_right", "Rotate 90° right")).triggered.connect(lambda: self.rotate_selected(90))
            menu.addAction(get_icon("rotate_ccw"), translator.tr("rotate_left", "Rotate 90° left")).triggered.connect(lambda: self.rotate_selected(-90))
            menu.addAction(get_icon("rotate_cw"), translator.tr("rotate_180", "Rotate 180°")).triggered.connect(lambda: self.rotate_selected(180))
            menu.addSeparator()
            menu.addAction(get_icon("copy"), translator.tr("copy_page_nums", "Copy page numbers")).triggered.connect(lambda: QApplication.clipboard().setText(", ".join(str(p + 1) for p in sorted(sel))))
            menu.addSeparator()
            menu.addAction(get_icon("delete"), translator.tr("delete_pages", "Delete page(s)")).triggered.connect(self.delete_selected)
        if self.doc:
            menu.addSeparator(); self._fill_more(menu, clear=False)
        if menu.isEmpty(): menu.addAction(translator.tr("no_pages_selected_ctx", "(No pages selected)")).setEnabled(False)
        menu.exec(self.page_list.mapToGlobal(pos))

    # ── funciones extra: rangos, página en blanco, invertir, dividir, vista previa ──────────
    def _fill_more(self, menu, clear=True):
        if clear: menu.clear()
        menu.addAction(get_icon("range_select"), T("Seleccionar páginas…  (ej. 1-5, 8)")).triggered.connect(self.select_range)
        menu.addAction(get_icon("pdf_doc"), T("Insertar página en blanco")).triggered.connect(self.insert_blank)
        menu.addAction(get_icon("swap"), T("Invertir orden (selección o todo)")).triggered.connect(self.reverse_pages)
        menu.addSeparator()
        menu.addAction(get_icon("ops"), T("Dividir en varios PDFs…")).triggered.connect(self.split_dialog)

    def _edit(self, fn):
        """Aplica una modificación con deshacer y marca cambios."""
        self._snapshot(); fn(); self._mark_dirty()
        self.page_list.load_doc(self.doc); self._update_count(); self.changed.emit()

    def select_range(self):
        if not self.doc: return
        txt, ok = QInputDialog.getText(self, T("Seleccionar páginas"), Tf("Páginas (1–{0}), ej. 1-5, 8, 10-12:", len(self.doc)))
        if not ok: return
        try:
            sel = parse_ranges(txt, len(self.doc))
        except ValueError as e:
            QMessageBox.warning(self, T("Rango no válido"), str(e)); return
        self.page_list.clearSelection()
        for i in sel: self.page_list.item(i).setSelected(True)
        self.page_list.scrollToItem(self.page_list.item(sel[0]))

    def insert_blank(self):
        if not self.doc: return
        sel = self.page_list.selected_page_nums()
        ref = sel[-1] if sel else len(self.doc) - 1
        r = self.doc[ref].rect
        self._edit(lambda: self.doc.new_page(pno=ref + 1, width=r.width, height=r.height))
        self.page_list.item(ref + 1).setSelected(True)

    def reverse_pages(self):
        if not self.doc: return
        sel = self.page_list.selected_page_nums() or list(range(len(self.doc)))
        order = list(range(len(self.doc)))
        for i, j in zip(sel, reversed(sel)): order[i] = j
        self._edit(lambda: self.doc.select(order))

    def split_dialog(self):
        if not self.doc: return
        dlg = SplitDialog(self, len(self.doc), self.path, self.doc.get_toc())
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        try:
            groups = dlg.groups()
        except ValueError as e:
            QMessageBox.warning(self, T("Rango no válido"), str(e)); return
        base = os.path.splitext(os.path.basename(self.path or "documento.pdf"))[0]
        names = dlg.names()
        for k, g in enumerate(groups, 1):
            part = extract_pages(self.doc, g)
            name = f"{base}_{k:02d} {names[k - 1]}.pdf" if names else f"{base}_parte{k}.pdf"
            try:
                save_pdf(part, os.path.join(dlg.folder, name), self.crypt)
            finally:
                part.close()
        self.status.emit(Tf("{0} archivo(s) creados en {1}", len(groups), dlg.folder))

    def _preview(self, i):
        if self.doc: PagePreview(self, self.doc, i).exec()

# ══════════════════════════════════════════════════════════
# PANEL CENTRAL DE OPERACIONES
# ══════════════════════════════════════════════════════════
class OperationsPanel(QFrame):
    """Columna central: todas las operaciones en un solo lugar (antes repetidas en una barra superior)."""
    op_requested = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ops_panel")
        self.setMinimumWidth(150)                     # se ensancha si los textos lo necesitan
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 12, 10, 12); lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        def title(txt):
            t = QLabel(txt); t.setObjectName("ops_title"); t.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.addWidget(t)

        def btn(icon, text, tip, op, danger=False):
            b = _op_button(icon, text, tip, lambda: self.op_requested.emit(op), danger)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed); lay.addWidget(b); return b

        title(T("A  →  B"))
        self.btn_copy_lr = btn("copy", T("Copiar →"), translator.tr("copy_a_b_tip", "Copy selected pages A→B"), "copy_lr")
        self.btn_move_lr = btn("cut", T("Mover →"), translator.tr("move_a_b_tip", "Move selected pages A→B"), "move_lr")
        lay.addSpacing(8)
        title(T("B  →  A"))
        self.btn_copy_rl = btn("copy", T("← Copiar"), translator.tr("copy_b_a_tip", "Copy selected pages B→A"), "copy_rl")
        self.btn_move_rl = btn("cut", T("← Mover"), translator.tr("move_b_a_tip", "Move selected pages B→A"), "move_rl")
        lay.addSpacing(8)
        title(T("AMBOS"))
        btn("swap", T("Intercambiar"), translator.tr("swap_tip", "Swap both docs"), "swap")
        btn("merge", T("Combinar A+B…"), translator.tr("merge_new_tip", "Create new combined PDF"), "merge")
        btn("merge", T("Combinar varios…"), T("Combinar más de dos PDFs en uno, eligiendo el orden"), "merge_many")
        btn("close", T("Cerrar"), translator.tr("close_all_tip", "Close documents"), "close")
        lay.addStretch()
        hint = QLabel(T("Arrastra miniaturas entre documentos.\nShift al soltar = mover.\nCtrl/Shift + clic = varias."))
        hint.setObjectName("ops_hint"); hint.setWordWrap(True); lay.addWidget(hint)

    def set_enabled_lr(self, enabled: bool): self.btn_copy_lr.setEnabled(enabled); self.btn_move_lr.setEnabled(enabled)
    def set_enabled_rl(self, enabled: bool): self.btn_copy_rl.setEnabled(enabled); self.btn_move_rl.setEnabled(enabled)


class SplitDialog(QDialog):
    """Elegir cómo dividir: cada N páginas, por rangos o una página por archivo."""
    def __init__(self, parent, total, path, toc=None):
        super().__init__(parent)
        self.setWindowTitle(T("Dividir PDF")); self.setMinimumWidth(380); self.total = total; self.toc = toc or []
        self.folder = os.path.dirname(path) if path else os.path.expanduser("~")
        lay = QVBoxLayout(self)
        self.r_every = QRadioButton(T("Cada")); self.r_ranges = QRadioButton(T("Por rangos (un archivo por rango):"))
        self.r_single = QRadioButton(Tf("Una página por archivo ({0} archivos)", total)); self.r_every.setChecked(True)
        row = QHBoxLayout(); row.addWidget(self.r_every)
        self.sp_n = QSpinBox(); self.sp_n.setRange(1, max(total, 1)); self.sp_n.setValue(min(10, total))
        row.addWidget(self.sp_n); row.addWidget(QLabel(T("páginas"))); row.addStretch(); lay.addLayout(row)
        lay.addWidget(self.r_ranges)
        self.ed_ranges = QLineEdit(); self.ed_ranges.setPlaceholderText(T("ej. 1-3, 4-10, 11-")); lay.addWidget(self.ed_ranges)
        self.ed_ranges.textEdited.connect(lambda: self.r_ranges.setChecked(True))
        lay.addWidget(self.r_single)
        self.r_marks = QRadioButton(T("Por marcadores (un archivo por capítulo), hasta el nivel"))
        mrow = QHBoxLayout(); mrow.addWidget(self.r_marks)
        self.sp_level = QSpinBox(); self.sp_level.setRange(1, max([t[0] for t in self.toc] or [1]))
        self.sp_level.valueChanged.connect(lambda: (self.r_marks.setChecked(True), self._marks_info()))
        mrow.addWidget(self.sp_level); mrow.addStretch(); lay.addLayout(mrow)
        self.lbl_marks = QLabel(); self.lbl_marks.setObjectName("hint"); lay.addWidget(self.lbl_marks)
        if not self.toc:
            self.r_marks.setEnabled(False); self.sp_level.setEnabled(False)
            self.lbl_marks.setText(T("   (este documento no tiene marcadores)"))
        else:
            self._marks_info()
        frow = QHBoxLayout(); self.lbl_folder = ElidedLabel(self.folder); frow.addWidget(QLabel(T("Carpeta:"))); frow.addWidget(self.lbl_folder, 1)
        bf = QPushButton(T("Cambiar…")); bf.setObjectName("flat"); bf.clicked.connect(self._pick); frow.addWidget(bf); lay.addLayout(frow)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Dividir")); bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, T("Carpeta de destino"), self.folder)
        if d: self.folder = d; self.lbl_folder.setText(d)

    def _marks(self):
        from core.pages import groups_bookmarks
        return groups_bookmarks(self.toc, self.total, self.sp_level.value())

    def _marks_info(self):
        self.lbl_marks.setText("   " + Tf("{0} archivo(s), con el nombre de cada marcador", len(self._marks())))

    def names(self) -> list:
        from core.pages import safe_filename
        return [safe_filename(t) for t, _ in self._marks()] if self.r_marks.isChecked() else []

    def groups(self) -> list:
        if self.r_marks.isChecked():
            g = [p for _, p in self._marks()]
            if not g: raise ValueError(T("Los marcadores no apuntan a ninguna página de este documento."))
            return g
        if self.r_single.isChecked(): return [[i] for i in range(self.total)]
        if self.r_ranges.isChecked(): return groups_ranges(self.ed_ranges.text(), self.total)
        return groups_every(self.sp_n.value(), self.total)


class MergeManyDialog(QDialog):
    """Combinar varios PDFs: agregar, ordenar (arrastrando o con flechas) y guardar."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(T("Combinar varios PDFs")); self.resize(520, 420); self._win = parent
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(T("Archivos en el orden en que se combinarán (arrastra para reordenar):")))
        self.lst = QListWidget(); self.lst.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection); lay.addWidget(self.lst, 1)
        row = QHBoxLayout()
        for icon, txt, fn in (("open", "Agregar…", self._add), ("delete", "Quitar", self._remove),
                              ("prev", "Subir", lambda: self._move(-1)), ("next", "Bajar", lambda: self._move(1))):
            row.addWidget(_op_button(icon, txt, txt, fn))
        row.addStretch(); lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Combinar y guardar…"))
        bb.accepted.connect(self._combine); bb.rejected.connect(self.reject); lay.addWidget(bb)

    def paths(self): return [self.lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst.count())]

    def add_paths(self, paths):
        for p in paths:
            it = QListWidgetItem(get_icon("pdf_doc"), os.path.basename(p)); it.setToolTip(p)
            it.setData(Qt.ItemDataRole.UserRole, p); self.lst.addItem(it)

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, T("Agregar PDFs"), os.path.expanduser("~"), T("PDF Files (*.pdf)"))
        self.add_paths(paths)

    def _remove(self):
        for it in self.lst.selectedItems(): self.lst.takeItem(self.lst.row(it))

    def _move(self, d):
        r = self.lst.currentRow()
        if 0 <= r + d < self.lst.count():
            self.lst.insertItem(r + d, self.lst.takeItem(r)); self.lst.setCurrentRow(r + d)

    def _combine(self, out=None):
        paths = self.paths()
        if len(paths) < 2:
            QMessageBox.information(self, T("Combinar"), T("Agrega al menos dos PDFs.")); return
        out = out or QFileDialog.getSaveFileName(self, T("Guardar PDF combinado"),
                                                 os.path.join(os.path.dirname(paths[0]), "combinado.pdf"), T("PDF Files (*.pdf)"))[0]
        if not out: return
        docs = []
        try:
            for p in paths:
                d = open_for_pages(self, p)
                if d is None: return
                docs.append(d)
            res = combine_docs(docs)
            save_pdf(res, out); res.close()
        except Exception as e:
            QMessageBox.critical(self, T("Error"), Tf("No se pudo combinar:\n{0}", e)); return
        finally:
            for d in docs: d.close()
        self._win._status(Tf("PDF combinado guardado: {0}", out))
        self.accept()


class PagePreview(QDialog):
    """Vista previa grande de una página (doble clic en la miniatura). ← → para navegar."""
    def __init__(self, parent, doc, i):
        super().__init__(parent)
        self.doc, self.i = doc, i
        scr = QApplication.primaryScreen().availableGeometry()
        self.resize(int(scr.height() * 0.75), int(scr.height() * 0.88))
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        self.sc = QScrollArea(); self.sc.setWidgetResizable(True); self.sc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl = QLabel(); self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); self.sc.setWidget(self.lbl); lay.addWidget(self.sc)
        self._show()

    def _show(self):
        pg = self.doc[self.i]
        z = (self.height() - 30) / pg.rect.height
        pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
        self.lbl.setPixmap(QPixmap.fromImage(QImage(pix.samples, pix.width, pix.height, pix.stride,
                                                    QImage.Format.Format_RGB888).copy()))
        self.setWindowTitle(Tf("Página {0} de {1}  ·  ← → para cambiar, Esc para cerrar", self.i + 1, len(self.doc)))

    def keyPressEvent(self, ev):
        d = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_PageUp: -1, Qt.Key.Key_PageDown: 1}.get(ev.key())
        if d and 0 <= self.i + d < len(self.doc):
            self.i += d; self._show()
        else:
            super().keyPressEvent(ev)


class ElidedLabel(QLabel):
    """Etiqueta que recorta el texto con "…" si no cabe (nombres de archivo largos)."""
    def minimumSizeHint(self): return QSize(40, super().minimumSizeHint().height())
    def paintEvent(self, ev):
        p = QPainter(self); p.setPen(self.palette().color(self.foregroundRole()))
        p.setFont(self.font())
        txt = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideMiddle, self.width())
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), txt); p.end()


def _op_button(icon, text, tip, slot, danger=False) -> QPushButton:
    """Botón secundario uniforme (legible también deshabilitado y en modo gris)."""
    b = QPushButton(text); b.setObjectName("op_danger" if danger else "op")
    b.setIcon(get_icon(icon, color=C['danger'] if danger else None)); b.setToolTip(tip)
    b.clicked.connect(slot)
    return b

# ══════════════════════════════════════════════════════════
# VENTANA PRINCIPAL DE OPERACIONES ENTRE PDFs
# ═════════════════════════════════════════════════════════
class PDFMergeWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("PDFRapid — ") + translator.tr("pdf_operations", "PDF Operations"))
        self.setMinimumSize(1100, 720); self.resize(1400, 860)
        self._build_ui(); self._update_op_buttons()

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        main_lay = QVBoxLayout(central); main_lay.setContentsMargins(0, 0, 0, 0); main_lay.setSpacing(0)
        tb = QToolBar("Acciones"); tb.setMovable(False); self.addToolBar(tb)
        def tbtn(txt, tip, slot, icon=None):
            from PyQt6.QtWidgets import QToolButton
            b = QToolButton(); b.setText(txt); b.setToolTip(tip); b.clicked.connect(slot)
            if icon: b.setIcon(get_icon(icon)); b.setIconSize(QSize(18, 18))
            tb.addWidget(b); return b
        tbtn(translator.tr("open_left", "Open left"), translator.tr("open_left", "Open left"), lambda: self.panel_l.open_doc(), "open")
        tbtn(translator.tr("open_right", "Open right"), translator.tr("open_right", "Open right"), lambda: self.panel_r.open_doc(), "open")
        tb.addSeparator()
        tbtn(translator.tr("save_left", "Save left"), translator.tr("save_left", "Save left"), lambda: self.panel_l.save_doc(), "save")
        tbtn(translator.tr("save_right", "Save right"), translator.tr("save_right", "Save right"), lambda: self.panel_r.save_doc(), "save")
        tb.addSeparator()
        tbtn(translator.tr("copy_sel_right", "Copy sel. →"), translator.tr("copy_sel_right", "Copy sel. →"), lambda: self._do_op("copy_lr"), "copy")
        tbtn(translator.tr("copy_sel_left", "← Copy sel."), translator.tr("copy_sel_left", "← Copy sel."), lambda: self._do_op("copy_rl"), "copy")
        tb.addSeparator()
        tbtn(translator.tr("move_sel_right", "Move sel. →"), translator.tr("move_sel_right", "Move sel. →"), lambda: self._do_op("move_lr"), "cut")
        tbtn(translator.tr("move_sel_left", "← Move sel."), translator.tr("move_sel_left", "← Move sel."), lambda: self._do_op("move_rl"), "cut")
        tb.addSeparator()
        tbtn(translator.tr("swap_all", "Swap all"), translator.tr("swap_all", "Swap all"), self._swap_all, "swap")
        tbtn(translator.tr("merge_to_new", "Merge to new"), translator.tr("merge_to_new", "Merge to new"), self._merge_to_new, "merge")
        
        work = QWidget(); work_lay = QHBoxLayout(work); work_lay.setContentsMargins(8, 8, 8, 8); work_lay.setSpacing(8)
        self.panel_l = DocPanel(0, translator.tr("doc_a", "Document A — (not open)"))
        self.panel_r = DocPanel(1, translator.tr("doc_b", "Document B — (not open)"))
        for p in (self.panel_l, self.panel_r): p.status.connect(self._status)
        self.ops = OperationsPanel(); self.ops.op_requested.connect(self._do_op)
        self.panel_l.page_list.pages_dropped.connect(lambda dst, pgs, idx, mv: self._handle_drop(dst, pgs, idx, mv))
        self.panel_r.page_list.pages_dropped.connect(lambda dst, pgs, idx, mv: self._handle_drop(dst, pgs, idx, mv))
        self.panel_l.changed.connect(self._update_op_buttons); self.panel_r.changed.connect(self._update_op_buttons)
        work_lay.addWidget(self.panel_l, 3); work_lay.addWidget(self.ops); work_lay.addWidget(self.panel_r, 3)
        main_lay.addWidget(work, 1)
        sb = QStatusBar(); self.setStatusBar(sb)
        self._status(translator.tr("start_msg", "Open two PDFs to begin · Drag & Drop to move pages · Shift+Drop to move (deletes from source)"))

    def _do_op(self, op: str):
        if op == "swap": return self._swap_all()
        if op == "merge": return self._merge_to_new()
        if op == "merge_many": return MergeManyDialog(self).exec()
        if op == "close": return            # lo atiende PDFMergeWidget
        if op.endswith("_lr"): src_panel, dst_panel = self.panel_l, self.panel_r
        else: src_panel, dst_panel = self.panel_r, self.panel_l
        if not src_panel.doc: QMessageBox.warning(self, translator.tr("no_document", "No document"), translator.tr("source_not_open", "The source document is not open.")); return
        if not dst_panel.doc: QMessageBox.warning(self, translator.tr("no_document", "No document"), translator.tr("dest_not_open", "The destination document is not open.")); return
        sel = src_panel.page_list.selected_page_nums()
        if not sel: QMessageBox.information(self, translator.tr("no_selection_msg", "No selection"), translator.tr("select_pages_origin", "Select pages in the source document.")); return
        insert_at = self._ask_insert_position(dst_panel, len(sel))
        if insert_at is None: return
        move = op.startswith("move")
        dst_panel.insert_pages_from(src_panel.doc, sel, insert_at, move, src_panel if move else None)
        n = len(sel); action = translator.tr("moved", "Moved") if move else translator.tr("copied", "Copied")
        direction = translator.tr("left_to_right", "LEFT → RIGHT") if op.endswith("_lr") else translator.tr("right_to_left", "RIGHT → LEFT")
        self._status(Tf("{0} {1} página(s) {2} en posición {3}.", action, n, direction, insert_at + 1))

    def _handle_drop(self, dst_list: PageList, page_nums: list, insert_idx: int, move: bool):
        src_doc_id = page_nums[0] if isinstance(page_nums[0], int) else 0
        if dst_list is self.panel_l.page_list:
            dst_panel = self.panel_l; src_panel = self.panel_r if dst_list.doc_id != src_doc_id else self.panel_l
        else:
            dst_panel = self.panel_r; src_panel = self.panel_l if dst_list.doc_id != src_doc_id else self.panel_r
        if dst_list is src_panel.page_list: dst_panel.reorder_pages(page_nums, insert_idx)
        else:
            if not src_panel.doc or not dst_panel.doc: return
            dst_panel.insert_pages_from(src_panel.doc, page_nums, insert_idx, move, src_panel if move else None)
            action = translator.tr("moved", "Moved") if move else translator.tr("copied", "Copied")
            self._status(Tf("{0} {1} página(s) por drag & drop.", action, len(page_nums)))

    def _ask_insert_position(self, dst_panel: DocPanel, n_pages: int):
        if not dst_panel.doc: return 0
        total = len(dst_panel.doc)
        dlg = QDialog(self); dlg.setWindowTitle(translator.tr("position", "Position")); dlg.setMinimumWidth(340)
        lay = QVBoxLayout(dlg); lay.setSpacing(10); lay.setContentsMargins(14,12,14,12)
        lay.addWidget(QLabel(Tf("¿Dónde insertar {0} página(s) en '{1}'?", n_pages, dst_panel.lbl_title.text())))
        g = QGroupBox(translator.tr("position", "Position")); gl = QVBoxLayout(g); gl.setSpacing(8)
        self._ins_mode = "end"
        rb_end = QCheckBox(translator.tr("insert_at_end", "At the end of the document")); rb_end.setChecked(True); rb_end.clicked.connect(lambda: setattr(self, '_ins_mode', 'end')); gl.addWidget(rb_end)
        rb_begin = QCheckBox(translator.tr("insert_at_beginning", "At the beginning of the document")); rb_begin.clicked.connect(lambda: setattr(self, '_ins_mode', 'begin')); gl.addWidget(rb_begin)
        rb_custom = QCheckBox(translator.tr("insert_after_page", "After page:")); rb_custom.clicked.connect(lambda: setattr(self, '_ins_mode', 'custom'))
        row = QHBoxLayout(); row.addWidget(rb_custom)
        self._sp_pos = QSpinBox(); self._sp_pos.setRange(1, total); self._sp_pos.setValue(total); self._sp_pos.setFixedWidth(70)
        row.addWidget(self._sp_pos); row.addStretch(); gl.addLayout(row)
        def _excl(clicked_cb):
            for cb in [rb_end, rb_begin, rb_custom]:
                if cb is not clicked_cb: cb.setChecked(False)
            clicked_cb.setChecked(True)
        rb_end.clicked.connect(lambda: _excl(rb_end)); rb_begin.clicked.connect(lambda: _excl(rb_begin)); rb_custom.clicked.connect(lambda: _excl(rb_custom))
        lay.addWidget(g)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(translator.tr("insert", "Insert")); bb.button(QDialogButtonBox.StandardButton.Cancel).setText(translator.tr("cancel", "Cancel"))
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted: return None
        if self._ins_mode == "end": return total
        if self._ins_mode == "begin": return 0
        return self._sp_pos.value()

    def _swap_all(self):
        if not self.panel_l.doc or not self.panel_r.doc: QMessageBox.warning(self, translator.tr("no_document", "No document"), translator.tr("both_must_open", "Both panels must have a document open.")); return
        r = QMessageBox.question(self, translator.tr("swap_documents", "Swap documents"), translator.tr("swap_confirm", "Swap the content of both panels?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes: return
        self.panel_l.doc, self.panel_r.doc = self.panel_r.doc, self.panel_l.doc
        self.panel_l.path, self.panel_r.path = self.panel_r.path, self.panel_l.path
        tl = self.panel_l.lbl_title.text(); tr = self.panel_r.lbl_title.text()
        self.panel_l.lbl_title.setText(tr); self.panel_r.lbl_title.setText(tl)
        pl = self.panel_l.lbl_path.text(); pr = self.panel_r.lbl_path.text()
        self.panel_l.lbl_path.setText(pr); self.panel_r.lbl_path.setText(pl)
        self.panel_l.page_list.load_doc(self.panel_l.doc); self.panel_r.page_list.load_doc(self.panel_r.doc)
        self.panel_l._update_count(); self.panel_r._update_count()
        self._status(translator.tr("documents_swapped", "Documents swapped."))

    def _merge_to_new(self):
        if not self.panel_l.doc and not self.panel_r.doc: QMessageBox.warning(self, translator.tr("no_document", "No document"), translator.tr("open_at_least_one", "Open at least one PDF.")); return
        dlg = QDialog(self); dlg.setWindowTitle(translator.tr("merge_new", "Merge into new PDF")); dlg.setMinimumWidth(420)
        lay = QVBoxLayout(dlg); lay.setSpacing(10); lay.setContentsMargins(14,12,14,12)
        lay.addWidget(QLabel(translator.tr("merge_title", "Which pages to include in the new PDF?")))
        g = QGroupBox(translator.tr("merge_content", "CONTENT")); gl = QVBoxLayout(g); gl.setSpacing(6)
        cb_l = QCheckBox(Tf("Todo '{0}'", self.panel_l.lbl_title.text())); cb_l.setChecked(True); gl.addWidget(cb_l)
        cb_r = QCheckBox(Tf("Todo '{0}'", self.panel_r.lbl_title.text())); cb_r.setChecked(True); gl.addWidget(cb_r)
        cb_sel_l = QCheckBox(T("Solo páginas seleccionadas del panel izquierdo")); gl.addWidget(cb_sel_l)
        cb_sel_r = QCheckBox(T("Solo páginas seleccionadas del panel derecho")); gl.addWidget(cb_sel_r); lay.addWidget(g)
        g2 = QGroupBox(translator.tr("merge_order", "ORDER")); gl2 = QVBoxLayout(g2); gl2.setSpacing(4)
        rb_lr = QCheckBox(translator.tr("merge_left_first", "Left first, then right")); rb_lr.setChecked(True); gl2.addWidget(rb_lr)
        rb_rl = QCheckBox(translator.tr("merge_right_first", "Right first, then left")); gl2.addWidget(rb_rl)
        def _excl2(cb):
            for b in [rb_lr, rb_rl]: b.setChecked(b is cb)
        rb_lr.clicked.connect(lambda: _excl2(rb_lr)); rb_rl.clicked.connect(lambda: _excl2(rb_rl)); lay.addWidget(g2)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(translator.tr("merge_create", "Create PDF")); bb.button(QDialogButtonBox.StandardButton.Cancel).setText(translator.tr("cancel", "Cancel"))
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        new_doc = pymupdf.open()
        order = [("l", "r"), ("r", "l")][0 if rb_lr.isChecked() else 1]
        panel_map = {"l": self.panel_l, "r": self.panel_r}; cb_map = {"l": (cb_l, cb_sel_l), "r": (cb_r, cb_sel_r)}
        for key in order:
            p = panel_map[key]; cb_all, cb_sel = cb_map[key]
            if not p.doc: continue
            if cb_sel.isChecked(): pages = p.page_list.selected_page_nums()
            elif cb_all.isChecked(): pages = list(range(len(p.doc)))
            else: continue
            for pg_num in pages: new_doc.insert_pdf(p.doc, from_page=pg_num, to_page=pg_num)
        if len(new_doc) == 0: QMessageBox.information(self, translator.tr("no_pages", "No pages"), translator.tr("no_pages_selected_msg", "No pages were selected.")); new_doc.close(); return
        path, _ = QFileDialog.getSaveFileName(self, translator.tr("save_extract", "Save extraction"), os.path.expanduser("~/combinado.pdf"), T("PDF Files (*.pdf)"))
        if path:
            new_doc.save(path, garbage=4, deflate=True); new_doc.close()
            r = QMessageBox.question(self, translator.tr("pdf_created", "PDF created"), translator.tr("pdf_created_msg", "PDF created with {n} pages.\nOpen in left panel?").format(n=len(new_doc)), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r == QMessageBox.StandardButton.Yes: self.panel_l.open_doc(path)
            self._status(translator.tr("new_pdf_created", "New PDF created: {path}").format(path=path))
        else: new_doc.close()

    def _update_op_buttons(self):
        has_l = self.panel_l.has_doc; has_r = self.panel_r.has_doc
        self.ops.set_enabled_lr(has_l and has_r); self.ops.set_enabled_rl(has_l and has_r)
    def _status(self, msg: str): self.statusBar().showMessage(f"  {msg}")
    def open_left(self, path: str): self.panel_l.open_doc(path)
    def open_right(self, path: str): self.panel_r.open_doc(path)

# ══════════════════════════════════════════════════════════
# WIDGET INTEGRABLE EN Pdfgm (para usar como tab)
# ══════════════════════════════════════════════════════════
class PDFMergeWidget(QWidget):
    status = pyqtSignal(str)        # mensajes para la barra de estado de la ventana principal

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self._win = PDFMergeWindow()
        self._win.statusBar().messageChanged.connect(lambda m: m and self.status.emit(m))
        self._win.ops.op_requested.connect(lambda op: op == "close" and self._close_all())
        work_area = self._win.centralWidget(); work_area.setParent(self); lay.addWidget(work_area, 1)

    def confirm_close(self) -> bool:
        """Pregunta por cada documento con cambios. True = se puede cerrar."""
        for p in (self._win.panel_l, self._win.panel_r):
            if p._is_dirty and p.doc:
                mb = QMessageBox(self)
                mb.setWindowTitle(translator.tr("save_changes", "Guardar cambios"))
                mb.setText(translator.tr("save_changes_msg", "¿Desea guardar los cambios en '{name}' antes de cerrar?").format(name=p.lbl_title.text()))
                mb.setIcon(QMessageBox.Icon.Question)
                btn_save = mb.addButton(T("Guardar"), QMessageBox.ButtonRole.AcceptRole)
                mb.addButton(T("No guardar"), QMessageBox.ButtonRole.DestructiveRole)
                btn_cancel = mb.addButton(T("Cancelar"), QMessageBox.ButtonRole.RejectRole)
                mb.exec()
                clicked = mb.clickedButton()
                if clicked is btn_cancel: return False
                if clicked is btn_save and not p.save_doc(): return False
                p._is_dirty = False
        return True

    def _close_all(self):
        """Cierra ambos documentos, preguntando si guardar solo si hay cambios."""
        if not self.confirm_close(): return
        for p in (self._win.panel_l, self._win.panel_r):
            if p.doc:
                p.doc.close()
                p.doc = None
                p.path = None
                p.lbl_title.setText(translator.tr("doc_a" if p.doc_id == 0 else "doc_b", "Document — (not open)"))
                p.lbl_path.setText(" ")
                p.page_list.clear()
                p._is_dirty = False
                p._set_enabled(False)
                p.crypt = None
        self.status.emit(translator.tr("documents_closed", "Documents closed."))

    def closeEvent(self, event):
        """Maneja el cierre de la pestaña o aplicación."""
        self._close_all()
        super().closeEvent(event)

    def open_left(self, path: str): self._win.open_left(path)
    def open_right(self, path: str): self._win.open_right(path)

# ═════════════════════════════════════════════════════════
# MAIN (ejecución independiente)
# ══════════════════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PDFRapid — " + translator.tr("pdf_operations", "PDF Operations"))
    app.setStyle("Fusion")
    app.setStyleSheet(SS)
    win = PDFMergeWindow(); win.show()
    args = sys.argv[1:]
    if len(args) >= 1 and os.path.exists(args[0]): win.open_left(args[0])
    if len(args) >= 2 and os.path.exists(args[1]): win.open_right(args[1])
    sys.exit(app.exec())

if __name__ == "__main__":
    main()