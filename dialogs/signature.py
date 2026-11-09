# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Firma visual (como «Rellenar y firmar» de Acrobat Reader): dibujada, escrita o desde una imagen.
Es una imagen sobre la página, NO una firma digital con certificado."""
from core.portable import qsettings
from core.i18n import T, Tf
import base64
from PyQt6.QtCore import Qt, QPointF, QBuffer, QIODevice, QRect
from PyQt6.QtGui import QPainter, QPen, QPixmap, QImage, QFont, QFontDatabase, QColor, QPainterPath, QIcon
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLineEdit, QComboBox,
                             QPushButton, QLabel, QFileDialog, QCheckBox, QDialogButtonBox, QListWidget,
                             QListWidgetItem)

INK = QColor("#1a2b6b")          # azul tinta
SCRIPT_FONTS = ["Segoe Script", "Lucida Handwriting", "Ink Free", "Brush Script MT", "Segoe Print"]
MAX_SAVED = 4


def _png_b64(img: QImage) -> str:
    buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return base64.b64encode(bytes(buf.data())).decode()


def _crop(img: QImage) -> QImage:
    """Recorta el margen transparente alrededor del trazo."""
    xs, ys = [], []
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            if img.pixelColor(x, y).alpha() > 0:
                xs.append(x); ys.append(y)
    if not xs:
        return img
    return img.copy(QRect(min(xs), min(ys), max(xs) - min(xs) + 3, max(ys) - min(ys) + 3))


def saved_signatures() -> list:
    return list(qsettings("PDFManager").value("signatures", []) or [])


def _save(b64: str):
    sigs = [s for s in saved_signatures() if s != b64]
    qsettings("PDFManager").setValue("signatures", ([b64] + sigs)[:MAX_SAVED])


class SignaturePad(QWidget):
    """Área para dibujar la firma con el ratón (o lápiz de tableta)."""
    def __init__(self):
        super().__init__()
        self.setMinimumSize(460, 170)
        self.strokes = []
        self.setCursor(Qt.CursorShape.CrossCursor)

    def clear(self): self.strokes = []; self.update()

    def mousePressEvent(self, ev): self.strokes.append([ev.position()]); self.update()
    def mouseMoveEvent(self, ev):
        if self.strokes: self.strokes[-1].append(ev.position()); self.update()

    def _paint(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(INK, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for s in self.strokes:
            path = QPainterPath(s[0])
            for q in s[1:]: path.lineTo(q)
            if len(s) == 1: path.lineTo(s[0] + QPointF(0.5, 0.5))
            p.drawPath(path)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        p.setPen(QPen(QColor("#c0c4cc"), 1, Qt.PenStyle.DashLine))
        p.drawLine(20, self.height() - 40, self.width() - 20, self.height() - 40)
        self._paint(p); p.end()

    def image(self) -> QImage:
        img = QImage(self.size() * 2, QImage.Format.Format_ARGB32); img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img); p.scale(2, 2); self._paint(p); p.end()
        return _crop(img)


class SignatureDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Firmar")); self.result_b64 = None
        lay = QVBoxLayout(self)
        saved = saved_signatures()
        if saved:
            lay.addWidget(QLabel(T("Firmas guardadas (doble clic para usar):")))
            self.lst = QListWidget(); self.lst.setViewMode(QListWidget.ViewMode.IconMode)
            self.lst.setIconSize(QPixmap(160, 50).size()); self.lst.setFixedHeight(80)
            for b in saved:
                it = QListWidgetItem(QIcon(QPixmap.fromImage(QImage.fromData(base64.b64decode(b)))), "")
                it.setData(Qt.ItemDataRole.UserRole, b); self.lst.addItem(it)
            self.lst.itemDoubleClicked.connect(lambda it: self._done(it.data(Qt.ItemDataRole.UserRole), False))
            lay.addWidget(self.lst)
        self.tabs = QTabWidget(); lay.addWidget(self.tabs)
        # dibujar
        w = QWidget(); v = QVBoxLayout(w); self.pad = SignaturePad(); v.addWidget(self.pad)
        b = QPushButton(T("Borrar")); b.setObjectName("flat"); b.clicked.connect(self.pad.clear)
        h = QHBoxLayout(); h.addStretch(); h.addWidget(b); v.addLayout(h)
        self.tabs.addTab(w, T("Dibujar"))
        # escribir
        w = QWidget(); v = QVBoxLayout(w)
        self.ed_name = QLineEdit(); self.ed_name.setPlaceholderText(T("Tu nombre"))
        families = set(QFontDatabase.families())
        self.cb_font = QComboBox(); self.cb_font.addItems([f for f in SCRIPT_FONTS if f in families] or ["Segoe UI"])
        self.preview = QLabel(); self.preview.setMinimumHeight(90); self.preview.setStyleSheet("background:white;")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for wd in (self.ed_name, self.cb_font, self.preview): v.addWidget(wd)
        self.ed_name.textChanged.connect(self._update_preview); self.cb_font.currentTextChanged.connect(self._update_preview)
        self.tabs.addTab(w, T("Escribir"))
        # imagen
        w = QWidget(); v = QVBoxLayout(w)
        self.img_lbl = QLabel(T("Elige una imagen de tu firma (PNG con fondo transparente es lo ideal)"))
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); self.img_lbl.setMinimumHeight(120)
        bi = QPushButton(T("Elegir imagen…")); bi.clicked.connect(self._pick)
        v.addWidget(self.img_lbl); v.addWidget(bi); self.tabs.addTab(w, T("Imagen"))
        self._img = None
        self.cb_save = QCheckBox(T("Guardar esta firma para la próxima vez")); self.cb_save.setChecked(True)
        lay.addWidget(self.cb_save)
        lay.addWidget(QLabel(T("<small>Es una firma visual (imagen). Para validez legal se necesita una firma "
                             "digital con certificado.</small>")))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Usar firma")); bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject); lay.addWidget(bb)

    def _typed(self) -> QImage:
        f = QFont(self.cb_font.currentText(), 40)
        img = QImage(900, 160, QImage.Format.Format_ARGB32); img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setFont(f); p.setPen(INK)
        p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, self.ed_name.text()); p.end()
        return _crop(img)

    def _update_preview(self):
        self.preview.setPixmap(QPixmap.fromImage(self._typed()).scaledToHeight(80, Qt.TransformationMode.SmoothTransformation)
                               if self.ed_name.text().strip() else QPixmap())

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self, T("Imagen de la firma"), "", T("Imágenes (*.png *.jpg *.jpeg *.bmp)"))
        if path:
            self._img = QImage(path)
            self.img_lbl.setPixmap(QPixmap.fromImage(self._img).scaledToHeight(110, Qt.TransformationMode.SmoothTransformation))

    def _accept(self):
        i = self.tabs.currentIndex()
        img = self.pad.image() if i == 0 and self.pad.strokes else \
            self._typed() if i == 1 and self.ed_name.text().strip() else self._img if i == 2 else None
        if img is None or img.isNull():
            return
        self._done(_png_b64(img), self.cb_save.isChecked())

    def _done(self, b64, save):
        if save: _save(b64)
        self.result_b64 = b64
        self.accept()
