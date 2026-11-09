# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Panel de archivos adjuntos del PDF (como el clip de Acrobat): ver, añadir, guardar, abrir y eliminar.
Los cambios se aplican con `Viewer.apply_doc_change` (se pueden deshacer). Por seguridad, solo se abren desde aquí
los tipos de documento conocidos (marcados como descargados de internet); el resto solo se puede guardar."""
from core.i18n import T, Tf
import os
import tempfile
import pymupdf
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QTreeWidget, QTreeWidgetItem,
                             QFileDialog, QMessageBox, QLabel, QAbstractItemView)
from ui.icons import get_icon

# Solo se abren tipos de documento conocidos (lista de permitidos: una lista de prohibidos siempre se queda corta,
# p. ej. .iso, .url, .chm, .msix…). Los documentos de Office con macros (.docm, .xlsm…) no están. El resto se guarda.
SAFE = {".pdf", ".txt", ".csv", ".rtf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp",
        ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt", ".odt", ".ods", ".odp", ".xml", ".json", ".md",
        ".mp3", ".wav", ".mp4", ".zip"}


def can_open(fname: str) -> bool:
    return os.path.splitext(fname)[1].lower() in SAFE


def mark_downloaded(path: str):
    """Marca el archivo como «descargado de internet» (Mark of the Web): Office lo abre en Vista protegida y
    Windows SmartScreen lo revisa, como un adjunto de correo."""
    try:
        with open(path + ":Zone.Identifier", "w") as f: f.write("[ZoneTransfer]\nZoneId=3\n")
    except OSError:
        pass                                            # unidades sin NTFS: sin marca


def _size(n): return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{max(n, 1) / 1024:.0f} KB"


class AttachmentsPanel(QWidget):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        bar = QHBoxLayout(); bar.setContentsMargins(4, 2, 4, 0); bar.setSpacing(2); self.btns = {}
        for key, icon, tip, fn in (("add", "duplicate", T("Adjuntar archivo…"), self.add),
                                   ("save", "save", T("Guardar como…"), self.save),
                                   ("open", "open", T("Abrir"), self.open),
                                   ("delete", "delete", T("Eliminar"), self.delete)):
            b = QToolButton(); b.setIcon(get_icon(icon)); b.setToolTip(tip); b.setAutoRaise(True); b.clicked.connect(fn)
            bar.addWidget(b); self.btns[key] = b
        bar.addStretch(); lay.addLayout(bar)
        self.list = QTreeWidget(); self.list.setHeaderLabels([T("Nombre"), T("Tamaño"), T("Descripción")])
        self.list.setRootIsDecorated(False); self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.itemDoubleClicked.connect(lambda *_: self.open())
        self.list.currentItemChanged.connect(lambda *_: self._update())
        lay.addWidget(self.list, 1)
        self.empty = QLabel(T("Este documento no tiene archivos adjuntos.")); self.empty.setObjectName("muted")
        self.empty.setWordWrap(True); self.empty.setContentsMargins(8, 4, 8, 8); lay.addWidget(self.empty)
        self._update()

    @property
    def v(self): return self.win._viewer

    def editable(self):
        return bool(self.v and self.v.doc) and self.v.allows(pymupdf.PDF_PERM_MODIFY) and not self.v.readonly

    def load(self) -> int:
        self.list.clear()
        doc = self.v.doc if self.v else None
        names = doc.embfile_names() if doc else []
        for n in names:
            info = doc.embfile_info(n)
            it = QTreeWidgetItem([info.get("filename") or n, _size(info.get("size") or info.get("length") or 0),
                                  info.get("desc") or ""])
            it.setData(0, Qt.ItemDataRole.UserRole, n); self.list.addTopLevelItem(it)
        for c in range(3): self.list.resizeColumnToContents(c)
        self.empty.setVisible(not names); self._update()
        return len(names)

    def _current(self):
        it = self.list.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def _update(self):
        has, ed = self._current() is not None, self.editable()
        self.btns["add"].setEnabled(ed)
        for k in ("save", "open"): self.btns[k].setEnabled(has)
        self.btns["delete"].setEnabled(has and ed)

    def add(self, path=None):
        if not self.editable(): return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, T("Adjuntar archivo"), self.win._settings.get_last_dir())
            if not path: return
        with open(path, "rb") as f: data = f.read()
        base = os.path.basename(path); name, i = base, 2
        existing = set(self.v.doc.embfile_names())
        while name in existing: name = f"{os.path.splitext(base)[0]} ({i}){os.path.splitext(base)[1]}"; i += 1
        self.v.apply_doc_change(lambda d: d.embfile_add(name, data, filename=base, desc=""))
        self.load(); self.win._status(Tf("Adjuntado: {0}", base))

    def _data(self, name):
        return self.v.doc.embfile_get(name), self.v.doc.embfile_info(name).get("filename") or name

    def save(self):
        name = self._current()
        if not name: return
        data, fname = self._data(name)
        out, _ = QFileDialog.getSaveFileName(self, T("Guardar adjunto"), os.path.join(self.win._settings.get_last_dir(), fname))
        if out:
            with open(out, "wb") as f: f.write(data)
            self.win._status(Tf("Guardado: {0}", out))

    def open(self):
        name = self._current()
        if not name: return
        data, fname = self._data(name)
        if not can_open(fname):
            QMessageBox.warning(self, T("Adjuntos"), Tf("Por seguridad, «{0}» no se abre desde el PDF (puede ser un "
                                                        "programa). Usa «Guardar como…» si confías en el archivo.", fname))
            return
        d = tempfile.mkdtemp(prefix="pdfrapid_adj_"); p = os.path.join(d, os.path.basename(fname))
        with open(p, "wb") as f: f.write(data)
        mark_downloaded(p)
        QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def delete(self):
        name = self._current()
        if not name or not self.editable(): return
        self.v.apply_doc_change(lambda d: d.embfile_del(name))
        self.load()
