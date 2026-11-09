# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Ventana «Comparar documentos»: dos versiones lado a lado con lo eliminado (rojo) y lo agregado (verde)."""
from core.i18n import T, Tf
import csv
import html
import os
import pymupdf
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QScrollArea,
                             QSplitter, QWidget, QPushButton, QFileDialog, QCheckBox)
from core.compare import compare_docs
from ui.icons import get_icon
from ui.styles import C

RED, GREEN = QColor(220, 38, 38, 90), QColor(22, 163, 74, 90)


def render(page, rects, color, width):
    """Imagen de la página escalada a `width` con los rects (sin rotar) resaltados."""
    z = width / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
    p = QPainter(img)
    m = page.rotation_matrix * pymupdf.Matrix(z, z)
    for r in rects:
        q = r * m
        p.fillRect(int(q.x0) - 1, int(q.y0) - 1, int(q.width) + 2, int(q.height) + 2, color)
    p.end()
    return QPixmap.fromImage(img)


class CompareDialog(QDialog):
    def __init__(self, parent, doc_a, name_a, doc_b, name_b, results):
        super().__init__(parent)
        self.setWindowTitle(T("Comparar documentos")); self.resize(1200, 820); self.setSizeGripEnabled(True)
        self.a, self.b, self.na, self.nb, self.res = doc_a, doc_b, name_a, name_b, results
        lay = QVBoxLayout(self); lay.setContentsMargins(14, 12, 14, 12)
        changed = [r for r in results if r["status"] != "igual"]
        rem, add = sum(len(r["removed"]) for r in results), sum(len(r["added"]) for r in results)
        top = QLabel(Tf("<b>A:</b> {0} ({1} págs.) &nbsp;·&nbsp; <b>B:</b> {2} ({3} págs.)<br>{4} página(s) con diferencias &nbsp;·&nbsp; <span style='color:#dc2626'>■ {5} palabras eliminadas de A</span> &nbsp; <span style='color:#16a34a'>■ {6} agregadas en B</span>", html.escape(name_a), len(doc_a), html.escape(name_b), len(doc_b), len(changed), rem, add))
        top.setWordWrap(True); lay.addWidget(top)
        split = QSplitter(Qt.Orientation.Horizontal); lay.addWidget(split, 1)
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)
        self.cb_all = QCheckBox(T("Mostrar también las páginas iguales")); self.cb_all.toggled.connect(self._fill)
        self.lst = QListWidget(); self.lst.currentRowChanged.connect(self._show)
        self.changes = QListWidget(); self.changes.setWordWrap(True)
        ll.addWidget(self.cb_all); ll.addWidget(self.lst, 2); ll.addWidget(QLabel(T("Cambios en la página:"))); ll.addWidget(self.changes, 1)
        split.addWidget(left)
        self.view_a, self.view_b = self._pane(f"A · {name_a}"), self._pane(f"B · {name_b}")
        split.addWidget(self.view_a[0]); split.addWidget(self.view_b[0]); split.setSizes([260, 470, 470])
        self.view_a[1].verticalScrollBar().valueChanged.connect(self.view_b[1].verticalScrollBar().setValue)   # desplazamiento sincronizado
        row = QHBoxLayout(); row.addStretch()
        be = QPushButton(T("Exportar informe…")); be.setIcon(get_icon("save")); be.clicked.connect(self._export)
        bc = QPushButton(T("Cerrar")); bc.clicked.connect(self.accept)
        row.addWidget(be); row.addWidget(bc); lay.addLayout(row)
        self._refit = QTimer(self); self._refit.setSingleShot(True); self._refit.setInterval(120)
        self._refit.timeout.connect(lambda: self._show(self.lst.currentRow()))
        self._fill()

    def _pane(self, title):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        cap = QLabel(title); cap.setObjectName("caption"); v.addWidget(cap)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lbl = QLabel(); lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop); sc.setWidget(lbl)
        v.addWidget(sc, 1)
        return w, sc, lbl

    def _fill(self):
        self.lst.clear()
        for r in self.res:
            if r["status"] == "igual" and not self.cb_all.isChecked(): continue
            txt = {"igual": T("sin cambios"), "solo A": T("solo en A (eliminada)"), "solo B": T("solo en B (nueva)")}.get(
                r["status"], f"−{len(r['removed'])} / +{len(r['added'])}")
            it = QListWidgetItem(Tf("Página {0}  ·  {1}", r['page'] + 1, txt), self.lst); it.setData(Qt.ItemDataRole.UserRole, r)
        if self.lst.count(): self.lst.setCurrentRow(0)
        else:
            self.view_a[2].setText(T("Los documentos tienen el mismo texto.")); self.view_b[2].clear()

    def _show(self, row):
        it = self.lst.item(row)
        if it is None: return
        r = it.data(Qt.ItemDataRole.UserRole); i = r["page"]
        w = max(300, self.view_a[1].viewport().width() - 4)
        for doc, rects, color, (_, _, lbl) in ((self.a, r["removed"], RED, self.view_a), (self.b, r["added"], GREEN, self.view_b)):
            if i < len(doc): lbl.setPixmap(render(doc[i], rects, color, w))
            else: lbl.clear(); lbl.setText(T("— no existe esta página —"))
        self.changes.clear()
        for old, new in r["changes"]:
            QListWidgetItem(("− " + old if old else "") + ("\n" if old and new else "") + ("+ " + new if new else ""), self.changes)

    def showEvent(self, ev):
        super().showEvent(ev); self._refit.start()

    def resizeEvent(self, ev):
        super().resizeEvent(ev); self._refit.start()       # volver a ajustar las páginas al ancho del panel

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, T("Exportar informe"), "comparacion.csv", T("CSV para Excel (*.csv)"))
        if not path: return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([f"A: {self.na}", f"B: {self.nb}"]); w.writerow(["Página", "Estado", "Eliminado (A)", "Agregado (B)"])
            for r in self.res:
                if r["status"] == "igual": continue
                for old, new in r["changes"] or [("", "")]:
                    w.writerow([r["page"] + 1, r["status"], old, new])
        self.parent()._status(Tf("Informe de comparación exportado: {0}", path)) if hasattr(self.parent(), "_status") else None


def compare_with_file(win):
    """Documento → Comparar con otro PDF…: el abierto (A) contra el que se elija (B)."""
    from PyQt6.QtWidgets import QMessageBox
    from ui.doc_tools import run_with_progress
    from pdfgm_merge import open_for_pages
    v = win._viewer
    if not (v and v.doc): return
    if not v.allows(pymupdf.PDF_PERM_COPY):
        QMessageBox.information(win, T("Documento protegido"), T("El autor de este documento no permite extraer su texto.")); return
    path, _ = QFileDialog.getOpenFileName(win, T("PDF a comparar (versión B)"), os.path.dirname(v.path or ""), T("PDF Files (*.pdf)"))
    if not path: return
    b = open_for_pages(win, path)
    if b is None: return
    a = pymupdf.open(stream=v.doc.tobytes(), filetype="pdf")          # copia: el visor sigue usando el suyo
    res, err = run_with_progress(win, "Comparar documentos", "Comparando el texto página por página…", lambda: compare_docs(a, b))
    if err:
        QMessageBox.critical(win, T("Comparar"), str(err)); return
    name_a = os.path.basename(v.path) if v.path else "documento abierto"
    CompareDialog(win, a, name_a, b, os.path.basename(path), res).exec()
    a.close(); b.close()
