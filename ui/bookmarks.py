# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Panel de marcadores (índice del PDF) editable, como en Acrobat: añadir (con el texto seleccionado como título),
añadir dentro, renombrar (F2 o doble clic), eliminar (Supr), subir/bajar de nivel, reordenar arrastrando y
asignar la página actual. Cada cambio se aplica al documento con `Viewer.set_toc` (se puede deshacer)."""
from core.i18n import T, Tf
import pymupdf
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QTreeWidget, QTreeWidgetItem, QMenu,
                             QAbstractItemView, QLabel)
from ui.icons import get_icon

ROLE_PAGE = Qt.ItemDataRole.UserRole          # página (desde 0)
ROLE_DEST = Qt.ItemDataRole.UserRole + 1      # destino original (dict de get_toc) para no perder zoom/posición


class _Tree(QTreeWidget):
    dropped = pyqtSignal()

    def dropEvent(self, ev):
        super().dropEvent(ev)
        self.dropped.emit()


class BookmarksPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewer = None
        self._loading = False
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        bar = QHBoxLayout(); bar.setContentsMargins(4, 2, 4, 0); bar.setSpacing(2)
        self.btns = {}
        for key, icon, tip, fn in (
                ("add", "duplicate", T("Añadir marcador en la página actual (usa el texto seleccionado como título)"), self.add),
                ("child", "select_group", T("Añadir marcador dentro del seleccionado"), lambda: self.add(child=True)),
                ("rename", "text", T("Renombrar (F2)"), self.rename),
                ("left", "prev", T("Subir un nivel"), self.outdent),
                ("right", "next", T("Bajar un nivel"), self.indent),
                ("delete", "delete", T("Eliminar (Supr)"), self.delete)):
            b = QToolButton(); b.setIcon(get_icon(icon)); b.setToolTip(tip); b.setAutoRaise(True); b.clicked.connect(fn)
            bar.addWidget(b); self.btns[key] = b
        bar.addStretch(); lay.addLayout(bar)
        self.tree = _Tree(); self.tree.setHeaderHidden(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.DoubleClicked)
        self.tree.itemClicked.connect(self._jump)
        self.tree.itemChanged.connect(lambda *_: self._commit())
        self.tree.dropped.connect(self._commit)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.currentItemChanged.connect(lambda *_: self._update_buttons())
        lay.addWidget(self.tree, 1)
        self.empty = QLabel(T("Este documento no tiene marcadores. Usa + para añadir uno en la página actual."))
        self.empty.setWordWrap(True); self.empty.setObjectName("muted"); self.empty.setContentsMargins(8, 4, 8, 8)
        lay.addWidget(self.empty)
        for seq, fn in ((QKeySequence.StandardKey.Delete, self.delete), ("F2", self.rename)):
            sc = QShortcut(QKeySequence(seq), self.tree); sc.setContext(Qt.ShortcutContext.WidgetShortcut); sc.activated.connect(fn)
        self._update_buttons()

    # ── carga y guardado ──
    def editable(self) -> bool:
        v = self.viewer
        return bool(v and v.doc) and v.allows(pymupdf.PDF_PERM_MODIFY) and not v.readonly

    def load(self, viewer):
        self.viewer = viewer
        self._loading = True
        self.tree.clear()
        toc = viewer.doc.get_toc(simple=False) if viewer and viewer.doc else []
        parents = {0: self.tree.invisibleRootItem()}
        for row in toc:
            lvl, title, page = row[0], row[1], row[2]
            parent = parents.get(lvl - 1, self.tree.invisibleRootItem())
            it = self._item(parent, title, max(page - 1, 0), row[3] if len(row) > 3 else None)
            parents[lvl] = it
            for k in [k for k in parents if k > lvl]: del parents[k]
        self.tree.expandToDepth(0)
        self._loading = False
        self.empty.setVisible(not toc)
        self._update_buttons()
        return bool(toc)

    def _item(self, parent, title, page, dest=None, index=None):
        it = QTreeWidgetItem([title])
        it.setData(0, ROLE_PAGE, page); it.setData(0, ROLE_DEST, dest)
        it.setToolTip(0, Tf("{0}  (p. {1})", title, page + 1))
        flags = it.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
        if self.editable(): flags |= Qt.ItemFlag.ItemIsEditable
        it.setFlags(flags)
        if index is None: parent.addChild(it)
        else: parent.insertChild(index, it)
        return it

    def toc(self) -> list:
        """Árbol → lista de get_toc/set_toc: [nivel, título, página (desde 1), destino]."""
        out = []

        def walk(parent, lvl):
            for i in range(parent.childCount()):
                it = parent.child(i)
                dest = it.data(0, ROLE_DEST)
                row = [lvl, it.text(0).strip() or T("(sin título)"), it.data(0, ROLE_PAGE) + 1]
                if isinstance(dest, dict): row.append(dest)
                out.append(row)
                walk(it, lvl + 1)
        walk(self.tree.invisibleRootItem(), 1)
        return out

    def _commit(self):
        if self._loading or not self.editable(): return
        self.viewer.set_toc(self.toc())
        self.empty.setVisible(self.tree.topLevelItemCount() == 0)
        self._update_buttons()

    # ── acciones ──
    def _jump(self, it):
        if self.viewer: self.viewer.jump(it.data(0, ROLE_PAGE))

    def _update_buttons(self):
        ed, cur = self.editable(), self.tree.currentItem()
        self.btns["add"].setEnabled(ed)
        for k in ("child", "rename", "delete", "left", "right"): self.btns[k].setEnabled(ed and cur is not None)
        if cur is not None:
            self.btns["left"].setEnabled(ed and cur.parent() is not None)
            p = cur.parent() or self.tree.invisibleRootItem()
            self.btns["right"].setEnabled(ed and p.indexOfChild(cur) > 0)

    def add(self, child=False):
        if not self.editable(): return
        v = self.viewer
        cv = v.canvases[v.current] if v.canvases else None
        title = " ".join((getattr(cv, "_tsel_text", "") or "").split())[:120] or Tf("Página {0}", v.current + 1)
        cur = self.tree.currentItem()
        self._loading = True
        if child and cur is not None:
            it = self._item(cur, title, v.current); cur.setExpanded(True)
        elif cur is not None:
            p = cur.parent() or self.tree.invisibleRootItem()
            it = self._item(p, title, v.current, index=p.indexOfChild(cur) + 1)
        else:
            it = self._item(self.tree.invisibleRootItem(), title, v.current)
        self._loading = False
        self._commit()
        self.tree.setCurrentItem(it); self.tree.editItem(it, 0)

    def rename(self):
        it = self.tree.currentItem()
        if it is not None and self.editable(): self.tree.editItem(it, 0)

    def delete(self):
        it = self.tree.currentItem()
        if it is None or not self.editable(): return
        (it.parent() or self.tree.invisibleRootItem()).removeChild(it)
        self._commit()

    def indent(self):
        """Bajar un nivel: pasa a ser hijo del marcador anterior."""
        it = self.tree.currentItem()
        if it is None or not self.editable(): return
        p = it.parent() or self.tree.invisibleRootItem(); i = p.indexOfChild(it)
        if i <= 0: return
        prev = p.child(i - 1); p.takeChild(i); prev.addChild(it); prev.setExpanded(True)
        self.tree.setCurrentItem(it); self._commit()

    def outdent(self):
        """Subir un nivel: queda justo después de su padre."""
        it = self.tree.currentItem()
        if it is None or it.parent() is None or not self.editable(): return
        par = it.parent(); gp = par.parent() or self.tree.invisibleRootItem()
        par.removeChild(it); gp.insertChild(gp.indexOfChild(par) + 1, it)
        self.tree.setCurrentItem(it); self._commit()

    def set_current_page(self):
        it = self.tree.currentItem()
        if it is None or not self.editable(): return
        self._loading = True
        it.setData(0, ROLE_PAGE, self.viewer.current); it.setData(0, ROLE_DEST, None)
        it.setToolTip(0, Tf("{0}  (p. {1})", it.text(0), self.viewer.current + 1))
        self._loading = False
        self._commit()

    def _menu(self, pos):
        if not self.editable(): return
        m = QMenu(self); it = self.tree.itemAt(pos)
        if it is not None: self.tree.setCurrentItem(it)
        m.addAction(get_icon("duplicate"), T("Añadir marcador"), self.add)
        if it is not None:
            m.addAction(get_icon("select_group"), T("Añadir dentro"), lambda: self.add(child=True))
            m.addAction(get_icon("text"), T("Renombrar"), self.rename)
            m.addAction(get_icon("goto"), T("Ir a la página actual al hacer clic"), self.set_current_page)
            m.addSeparator()
            m.addAction(get_icon("delete"), T("Eliminar"), self.delete)
        m.exec(self.tree.viewport().mapToGlobal(pos))
