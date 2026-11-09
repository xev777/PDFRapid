# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Panel de miniaturas de páginas"""
from core.i18n import T, Tf
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QAbstractItemView, QMenu, QDialog,
                             QGroupBox, QGridLayout, QSpinBox, QLineEdit, QDialogButtonBox)
from PyQt6.QtGui import QIcon, QPixmap, QImage, QPainter
from PyQt6.QtCore import pyqtSignal, Qt, QSize, QTimer
import pymupdf
from ui.styles import C, MENU_SS, DIALOG_SS
from ui.icons import get_icon
from utils.helpers import guard
from core.logger import log

class Thumbs(QWidget):
    clicked = pyqtSignal(int)
    rotate_pages = pyqtSignal(list, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(162)
        self.setStyleSheet(f"background:{C['panel']};border-right:1px solid {C['border']};")
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 8, 6, 8); lay.setSpacing(3)
        
        hdr = QLabel(T("PÁGINAS"))
        hdr.setStyleSheet(f"color:{C['muted']};font-size:10px;font-weight:700;letter-spacing:1px;")
        lay.addWidget(hdr)
        
        self.lst = QListWidget()
        self.lst.setViewMode(QListWidget.ViewMode.IconMode)    # miniatura centrada, número debajo
        self.lst.setFlow(QListWidget.Flow.TopToBottom)
        self.lst.setWrapping(False)
        self.lst.setMovement(QListWidget.Movement.Static)
        self.lst.setIconSize(QSize(110, 140))
        self.lst.setGridSize(QSize(136, 166))
        self.lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lst.itemClicked.connect(lambda it: self.clicked.emit(self.lst.row(it)))
        self.lst.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lst.customContextMenuRequested.connect(self._ctx)
        self.lst.verticalScrollBar().valueChanged.connect(self._render_visible)
        self._doc = None
        self._done = set()          # filas con miniatura ya generada
        self.overlay = None         # overlay(página, painter, escala): dibuja los objetos de PDFRapid
        self._blank = QIcon()
        lay.addWidget(self.lst)
        
        hint = QLabel(T("Ctrl+clic: múltiple\nShift+clic: rango"))
        hint.setStyleSheet(f"color:{C['muted']};font-size:9px;padding:2px 4px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

    @guard
    def load(self, doc):
        """Crea las entradas al instante; las imágenes se generan al hacerse visibles."""
        self.lst.clear(); self._doc = doc; self._done = set()
        blank = QPixmap(110, 140); blank.fill(Qt.GlobalColor.white); self._blank = QIcon(blank)
        for i in range(len(doc)):
            self.lst.addItem(QListWidgetItem(self._blank, str(i + 1)))
        QTimer.singleShot(0, self._render_visible)

    def _render_visible(self):
        if self._doc is None or self._doc.is_closed or not self.lst.count(): return
        vp = self.lst.viewport().rect()
        first = self.lst.indexAt(vp.topLeft()).row()
        last = self.lst.indexAt(vp.bottomLeft()).row()
        first = max(first, 0)
        if last < first: last = first + 15          # lista aún sin acomodar
        last = min(last, first + 40)                # tope de seguridad
        mat = pymupdf.Matrix(0.26, 0.26)
        for i in range(max(0, first - 2), min(self.lst.count(), last + 3)):
            if i in self._done: continue
            try:
                pix = self._doc[i].get_pixmap(matrix=mat, alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                if self.overlay:                     # objetos de PDFRapid (anotaciones) encima de la página
                    p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    self.overlay(i, p, 0.26); p.end()
                self.lst.item(i).setIcon(QIcon(QPixmap.fromImage(img)))
                self._done.add(i)
            except Exception:
                log.exception(f"miniatura p{i}")
        for i in [i for i in self._done if i < first - 60 or i > last + 60]:   # liberar lejanas
            self.lst.item(i).setIcon(self._blank); self._done.discard(i)

    def refresh(self):
        """Volver a dibujar las miniaturas visibles (cambiaron los objetos de alguna página)."""
        self._done.clear(); self._render_visible()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        QTimer.singleShot(0, self._render_visible)

    def set_current(self, i):
        """Marca la página visible sin emitir `clicked`."""
        if 0 <= i < self.lst.count() and self.lst.currentRow() != i:
            self.lst.blockSignals(True)
            self.lst.setCurrentRow(i)
            self.lst.blockSignals(False)
            self.lst.scrollToItem(self.lst.item(i))

    def clear(self): self.lst.clear(); self._doc = None; self._done = set()
    def selected_indices(self) -> list: return [self.lst.row(it) for it in self.lst.selectedItems()]

    def _ctx(self, pos):
        sel = self.selected_indices()
        if not sel: return
        menu = QMenu(self); menu.setStyleSheet(MENU_SS); n = len(sel)
        hdr = menu.addAction(Tf("  {0} página{1} seleccionada{2}", n, 's' if n > 1 else '', 's' if n > 1 else ''))
        hdr.setEnabled(False); hdr_f = hdr.font(); hdr_f.setBold(True); hdr.setFont(hdr_f)
        menu.addSeparator()
        rm = menu.addMenu(get_icon("rotate_cw"), T("Rotar página(s)"))
        a90 = rm.addAction(get_icon("rotate_cw"), T("90° derecha"))
        a180 = rm.addAction(get_icon("rotate_cw"), "180°")
        a270 = rm.addAction(get_icon("rotate_ccw"), T("90° izquierda"))
        menu.addSeparator()
        arng = menu.addAction(get_icon("range_select"), T("Seleccionar rango…"))
        aall = menu.addAction(get_icon("select_all"), T("Seleccionar todas"))
        ch = menu.exec(self.lst.mapToGlobal(pos))
        if ch == a90: self.rotate_pages.emit(sel, 90)
        elif ch == a180: self.rotate_pages.emit(sel, 180)
        elif ch == a270: self.rotate_pages.emit(sel, 270)
        elif ch == arng: self._range_dlg()
        elif ch == aall: self.lst.selectAll()

    def _range_dlg(self):
        total = self.lst.count()
        if total == 0: return
        dlg = QDialog(self); dlg.setWindowTitle(T("Seleccionar rango")); dlg.setMinimumWidth(300)
        dlg.setStyleSheet(DIALOG_SS)
        lay = QVBoxLayout(dlg); lay.setSpacing(8); lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(QLabel(Tf("Documento con {0} páginas.", total)))
        g = QGroupBox(T("RANGO")); gl = QGridLayout(g)
        gl.addWidget(QLabel(T("Desde:")), 0, 0); sf = QSpinBox(); sf.setRange(1, total); sf.setValue(1); gl.addWidget(sf, 0, 1)
        gl.addWidget(QLabel(T("Hasta:")), 1, 0); st = QSpinBox(); st.setRange(1, total); st.setValue(total); gl.addWidget(st, 1, 1)
        lay.addWidget(g)
        g2 = QGroupBox(T("ESPECÍFICAS")); g2l = QVBoxLayout(g2); g2l.addWidget(QLabel(T("Ej: 1,3,5-8")))
        spec = QLineEdit(); spec.setPlaceholderText("1,3,5-8"); g2l.addWidget(spec); lay.addWidget(g2)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Seleccionar")); bb.button(QDialogButtonBox.StandardButton.Cancel).setText(T("Cancelar"))
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        s = spec.text().strip()
        if s:
            idxs = set()
            for p in s.split(','):
                p = p.strip()
                if '-' in p:
                    a2, b2 = p.split('-', 1)
                    try: idxs.update(range(int(a2)-1, int(b2)))
                    except ValueError: pass  # rango mal escrito: se ignora
                else:
                    try: idxs.add(int(p)-1)
                    except ValueError: pass  # rango mal escrito: se ignora
            idxs = sorted(x for x in idxs if 0 <= x < total)
        else: idxs = list(range(sf.value()-1, st.value()))
        self.lst.clearSelection()
        for i in idxs:
            if 0 <= i < self.lst.count(): self.lst.item(i).setSelected(True)