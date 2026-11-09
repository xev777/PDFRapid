# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Panel de búsqueda de texto: opciones (mayúsculas, palabra completa) y lista de resultados con contexto."""
from core.i18n import T, Tf
from core.search import find_in_page, context
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QCheckBox,
                             QListWidget, QListWidgetItem, QApplication)
import time
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from ui.styles import C

MAX_RESULTS = 3000
LIST_MAX = 500           # filas con contexto en la lista (calcularlo es lo costoso)


class SearchPanel(QWidget):
    go_to_result = pyqtSignal(int, list)
    closed = pyqtSignal()                   # para quitar el resaltado amarillo (solo de pantalla)
    counter = pyqtSignal(str)               # «3 / 27» para la búsqueda rápida

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results = []          # [(página, Rect sin rotar)]
        self._idx = -1
        self._doc = None
        self._gen = 0               # para cancelar una búsqueda larga si se inicia otra
        self.setStyleSheet(f"background:{C['panel']};border-bottom:1px solid {C['border']};")
        outer = QVBoxLayout(self); outer.setContentsMargins(8, 6, 8, 6); outer.setSpacing(4)
        lay = QHBoxLayout(); lay.setSpacing(6); outer.addLayout(lay)
        self.search_box = QLineEdit(); self.search_box.setPlaceholderText(T("Buscar en el documento…  (Enter)"))
        self.search_box.returnPressed.connect(self._search)
        lay.addWidget(self.search_box, 3)
        self.cb_case = QCheckBox(T("Mayúsc./minúsc.")); self.cb_word = QCheckBox(T("Palabra completa"))
        self.cb_pages = QCheckBox(T("Por página")); self.cb_pages.setToolTip(T("Lista cada página donde aparece y cuántas veces"))
        self.cb_pages.toggled.connect(lambda: self._fill_list() if self._results else None)
        for cb in (self.cb_case, self.cb_word, self.cb_pages): lay.addWidget(cb)
        def btn(txt, tip, slot, w=32):
            b = QPushButton(txt); b.setObjectName("flat"); b.setToolTip(tip); b.setFixedWidth(w); b.clicked.connect(slot)
            lay.addWidget(b); return b
        btn("◀", T("Anterior  (Shift+F3)"), self._prev)
        btn("▶", T("Siguiente  (F3)"), self._next)
        self.btn_list = btn("☰", T("Mostrar/ocultar la lista de resultados"), lambda: self.results.setVisible(not self.results.isVisible()))
        self.lbl = QLabel(" "); self.lbl.setStyleSheet(f"color:{C['muted']};font-size:11px;"); lay.addWidget(self.lbl)
        self.btn_copy = btn("⧉", T("Copiar la lista de páginas (ej. 3, 7, 12)"), self._copy_pages)
        btn("✕", T("Cerrar  (Esc)"), self.close_panel, 28)
        self.results = QListWidget(); self.results.setMaximumHeight(150); self.results.hide()
        self.results.itemClicked.connect(lambda it: self._goto(it.data(Qt.ItemDataRole.UserRole)))
        outer.addWidget(self.results)
        self.hide()

    def close_panel(self):
        self.hide(); self._results = []; self._idx = -1; self.results.clear()
        self.counter.emit(""); self.closed.emit()

    def set_doc(self, doc, zoom: float = None):
        if doc is not self._doc:              # otro documento: cancelar la búsqueda en curso (su doc puede cerrarse)
            self._gen += 1; self._results = []; self._idx = -1; self.results.clear()
        self._doc = doc

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape: self.close_panel()
        else: super().keyPressEvent(ev)

    def _search(self, sync=False, on_done=None, start_page=None):
        """Busca por tramos de ~30 ms para no congelar la ventana en PDFs enormes; salta a la
        primera coincidencia en cuanto aparece. `sync=True` busca de una vez (pruebas)."""
        term = self.search_box.text().strip()
        self._results, self._idx, self._ctx = [], -1, {}
        self.results.clear()
        self._gen += 1
        if not term or not self._doc:
            self.lbl.setText(T("Sin resultados")); return
        case, whole = self.cb_case.isChecked(), self.cb_word.isChecked()
        pages = iter(enumerate(self._doc))
        gen, total = self._gen, len(self._doc)

        def step():
            if gen != self._gen: return                    # se inició otra búsqueda
            t0 = time.monotonic()
            for i, pg in pages:
                for r in find_in_page(pg, term, case, whole):
                    self._results.append((i, r))      # el contexto se calcula solo para las filas que se muestran
                if self._results and self._idx < 0:          # primera coincidencia (o la más cercana): mostrarla ya
                    k = 0 if start_page is None else next((k for k, (p, _) in enumerate(self._results) if p >= start_page), None)
                    if k is not None: self._idx = k; self._goto(k)
                if len(self._results) >= MAX_RESULTS: break
                if not sync and time.monotonic() - t0 > 0.03:
                    self.lbl.setText(Tf("Buscando… {0} %  ·  {1}", i * 100 // total, len(self._results)))
                    QTimer.singleShot(0, step); return
            if self._results:
                if self._idx < 0: self._idx = 0            # nada después de la página actual: volver al inicio
                self._fill_list()
                self.results.setVisible(len(self._results) > 1 and self.isVisible())
                self._goto()
            else:
                self.lbl.setText(T("Sin resultados")); self.counter.emit("0")
            if on_done: on_done()
        step()

    def _goto(self, idx=None):
        if not self._results: return
        if idx is not None: self._idx = idx
        page_num, r = self._results[self._idx]
        n = len(self._results)
        self.lbl.setText(f"{self._idx + 1} / {n}{'+' if n >= MAX_RESULTS else ''}")
        self.counter.emit(self.lbl.text())
        for k in range(self.results.count()):             # marcar la fila de esta coincidencia o su página
            it = self.results.item(k); nxt = self.results.item(k + 1)
            d, dn = it.data(Qt.ItemDataRole.UserRole), nxt.data(Qt.ItemDataRole.UserRole) if nxt else None
            if d is not None and d <= self._idx and (dn is None or dn > self._idx):
                self.results.setCurrentRow(k); break
        # search_for devuelve coordenadas sin rotar; el visor dibuja en coordenadas visibles
        self.go_to_result.emit(page_num, [r * self._doc[page_num].rotation_matrix])

    def pages(self) -> list:
        """Páginas (desde 1) donde aparece el texto buscado, sin repetir."""
        return sorted({p + 1 for p, _ in self._results})

    def _fill_list(self):
        """Lista de coincidencias o, con «Por página», una fila por página con su cantidad."""
        self.results.clear()
        if self.cb_pages.isChecked():
            first = {}
            for k, (p, _) in enumerate(self._results): first.setdefault(p, k)
            counts = {p: sum(1 for q, _ in self._results if q == p) for p in first}
            for p, k in first.items():
                it = QListWidgetItem(Tf("Página {0}  ·  {1} {2}  —  {3}", p + 1, counts[p], T('vez') if counts[p] == 1 else T('veces'), self._context(k)), self.results)
                it.setData(Qt.ItemDataRole.UserRole, k)
            self.lbl.setText(Tf("{0} páginas, {1} coincidencias", len(first), len(self._results)))
        else:
            for k, (p, _) in enumerate(self._results):
                if k >= LIST_MAX:
                    QListWidgetItem(Tf("… y {0} coincidencias más (usa ◀ ▶ o «Por página»)", len(self._results) - LIST_MAX), self.results)
                    break
                it = QListWidgetItem(Tf("p. {0}:  {1}", p + 1, self._context(k)), self.results); it.setData(Qt.ItemDataRole.UserRole, k)
        self.results.setVisible(True)

    def _context(self, k):
        if k not in self._ctx:
            p, r = self._results[k]
            self._ctx[k] = context(self._doc[p], r)
        return self._ctx[k]

    def _copy_pages(self):
        if self._results:
            QApplication.clipboard().setText(", ".join(map(str, self.pages())))
            self.lbl.setText(Tf("Copiadas {0} páginas", len(self.pages())))

    def _prev(self):
        if not self._results: return
        self._idx = (self._idx - 1) % len(self._results)
        self._goto()

    def _next(self):
        if not self._results: return
        self._idx = (self._idx + 1) % len(self._results)
        self._goto()
