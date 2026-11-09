# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Imprimir con opciones: páginas, con o sin comentarios, tamaño, varias páginas por hoja, folleto y póster.
Las hojas se componen en un PDF aparte (core/imposition.py) y se ven en la vista previa antes de imprimir."""
from core.i18n import T, Tf
import pymupdf
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainter, QImage, QPageLayout
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QCheckBox, QDoubleSpinBox,
                             QRadioButton, QButtonGroup, QLabel, QMessageBox, QDialogButtonBox, QStackedWidget, QWidget)
from core import imposition
from core.constants import APP_NAME
from core.logger import log
from core.pages import parse_ranges

MAX_DPI = 300                      # más resolución no se nota en papel y multiplica la memoria


class PrintDialog(QDialog):
    def __init__(self, parent, n_pages: int, current: int):
        super().__init__(parent)
        self.n = n_pages
        self.setWindowTitle(T("Imprimir")); self.setMinimumWidth(420)
        lay = QVBoxLayout(self); form = QFormLayout()
        self.rb_all, self.rb_cur, self.rb_range = (QRadioButton(T("Todas")), QRadioButton(Tf("Página actual ({0})", current + 1)),
                                                   QRadioButton(T("Páginas:")))
        self.current = current
        self.rb_all.setChecked(True)
        grp = QButtonGroup(self)
        for b in (self.rb_all, self.rb_cur, self.rb_range): grp.addButton(b)
        self.ed_range = QLineEdit(); self.ed_range.setPlaceholderText(T("ej. 1-3, 8"))
        self.ed_range.textEdited.connect(lambda: self.rb_range.setChecked(True))
        box = QVBoxLayout(); box.addWidget(self.rb_all); box.addWidget(self.rb_cur); box.addWidget(self.rb_range)
        box.addWidget(self.ed_range); form.addRow(T("Imprimir:"), box)
        self.cb_annots = QCheckBox(T("Con comentarios, marcas y formularios")); self.cb_annots.setChecked(True)
        form.addRow(self.cb_annots)
        self.cb_mode = QComboBox()
        for key, name in (("fit", T("Ajustar a la hoja")), ("actual", T("Tamaño real")), ("nup", T("Varias páginas por hoja")),
                          ("booklet", T("Folleto")), ("poster", T("Póster (varias hojas por página)"))):
            self.cb_mode.addItem(name, key)
        form.addRow(T("Tamaño y forma:"), self.cb_mode)
        self.stack = QStackedWidget()
        for key in ("fit", "actual", "nup", "booklet", "poster"):
            w = QWidget(); f = QFormLayout(w); f.setContentsMargins(0, 0, 0, 0)
            if key == "nup":
                self.cb_n = QComboBox()
                for n in imposition.GRIDS: self.cb_n.addItem(str(n), n)
                self.cb_n.setCurrentIndex(1)
                self.cb_border = QCheckBox(T("Borde alrededor de cada página")); self.cb_border.setChecked(True)
                f.addRow(T("Páginas por hoja:"), self.cb_n); f.addRow(self.cb_border)
            elif key == "booklet":
                hint = QLabel(T("Imprime a doble cara, volteando por el borde corto, y dobla las hojas por la mitad."))
                hint.setWordWrap(True); f.addRow(hint)
            elif key == "poster":
                self.sp_scale = QDoubleSpinBox(); self.sp_scale.setRange(110, 1000); self.sp_scale.setValue(200)
                self.sp_scale.setSuffix(" %"); self.sp_scale.setSingleStep(50)
                self.cb_marks = QCheckBox(T("Etiquetas para unir las hojas")); self.cb_marks.setChecked(True)
                hint = QLabel(T("Las hojas se solapan 6 mm para pegarlas."))
                f.addRow(T("Ampliación:"), self.sp_scale); f.addRow(self.cb_marks); f.addRow(hint)
            self.stack.addWidget(w)
        self.cb_mode.currentIndexChanged.connect(self.stack.setCurrentIndex)
        form.addRow(self.stack)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Vista previa…"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(T("Cancelar"))
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def pages(self):
        if self.rb_cur.isChecked(): return [self.current]
        if self.rb_range.isChecked() and self.ed_range.text().strip():
            return parse_ranges(self.ed_range.text(), self.n)
        return list(range(self.n))

    def accept(self):
        try:
            if not self.pages(): raise ValueError(T("No hay páginas que imprimir."))
        except ValueError as e:
            QMessageBox.warning(self, T("Páginas"), str(e)); return
        super().accept()

    def options(self) -> dict:
        return {"pages": self.pages(), "annots": self.cb_annots.isChecked(), "mode": self.cb_mode.currentData(),
                "n": self.cb_n.currentData(), "border": self.cb_border.isChecked(),
                "scale": self.sp_scale.value() / 100, "marks": self.cb_marks.isChecked()}


def compose(src_copy, opts: dict, sheet_size):
    """PDF con las hojas tal como se imprimirán. `src_copy` se modifica (aplanado y sin giros)."""
    imposition.prepare(src_copy, opts["annots"])
    pages, mode = opts["pages"], opts["mode"]
    if mode == "nup": return imposition.n_up(src_copy, pages, opts["n"], sheet_size, border=opts["border"])
    if mode == "booklet": return imposition.booklet(src_copy, pages, sheet_size)
    if mode == "poster": return imposition.poster(src_copy, pages, sheet_size, opts["scale"], marks=opts["marks"])[0]
    out = pymupdf.open()
    for p in pages: out.insert_pdf(src_copy, from_page=p, to_page=p)
    return out


def paint(pr: QPrinter, doc, actual_size: bool):
    """Dibuja cada hoja de `doc` en la impresora (respeta el intervalo elegido en el diálogo de impresión)."""
    pa = QPainter(pr)
    try:
        area = pr.pageRect(QPrinter.Unit.DevicePixel)
        dpi = min(pr.resolution(), MAX_DPI)
        k = pr.resolution() / dpi                    # de píxeles de la imagen a píxeles de la impresora
        first, last = pr.fromPage(), pr.toPage()
        idx = [i for i in range(len(doc)) if not first or first - 1 <= i <= last - 1]
        for n, i in enumerate(idx):
            if n: pr.newPage()
            try:
                pix = doc[i].get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
                w, h = pix.width * k, pix.height * k
                if not actual_size or w > area.width() or h > area.height():
                    s = min(area.width() / w, area.height() / h); w, h = w * s, h * s
                x, y = (area.width() - w) / 2, (area.height() - h) / 2
                pa.drawImage(QRectF(x, y, w, h), img)
            except Exception:
                log.exception(f"imprimir hoja {i}")
    finally:
        pa.end()


def print_viewer(viewer):
    """Archivo → Imprimir: opciones, vista previa e impresión."""
    dlg = PrintDialog(viewer, len(viewer.doc), max(0, viewer.current))
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    opts = dlg.options()
    pr = QPrinter(QPrinter.PrinterMode.HighResolution)
    paper = pr.pageLayout().fullRect(QPageLayout.Unit.Point)
    sheet = (paper.width(), paper.height())
    src = viewer.export_copy()
    try:
        doc = compose(src, opts, sheet)
    finally:
        src.close()
    if opts["mode"] in ("nup", "booklet", "poster"):           # la hoja compuesta ya tiene su orientación
        r = doc[0].rect
        pr.setPageOrientation(QPageLayout.Orientation.Landscape if r.width > r.height else QPageLayout.Orientation.Portrait)
    try:
        prev = QPrintPreviewDialog(pr, None)
        prev.setWindowTitle(Tf("Previsualización de impresión — {0}", APP_NAME))
        prev.setMinimumSize(1000, 720)
        prev.paintRequested.connect(lambda p: paint(p, doc, opts["mode"] == "actual"))
        prev.exec()
    finally:
        doc.close()
