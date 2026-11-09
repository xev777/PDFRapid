# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Recortar una imagen insertada: arrastrar para marcar el área, mover desde dentro y ajustar
desde bordes y esquinas (como en Word). Devuelve el rectángulo en píxeles de la imagen."""
from core.i18n import T, Tf
from PyQt6.QtCore import Qt, QRect, QRectF, QPointF, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QImage
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton, QDialogButtonBox
from ui.styles import C

H = 7          # radio de agarre de los tiradores (px)


class _CropArea(QWidget):
    def __init__(self, img: QImage, on_change):
        super().__init__()
        self.img, self.on_change = img, on_change
        self.pm = QPixmap.fromImage(img)
        self.crop = QRectF(0, 0, img.width(), img.height())     # en píxeles de la imagen
        self._drag = None
        self.setMouseTracking(True)
        self.setMinimumSize(320, 240)

    def sizeHint(self): return QSize(640, 460)

    # imagen ajustada al widget, centrada
    def _view(self) -> QRectF:
        s = min((self.width() - 20) / self.img.width(), (self.height() - 20) / self.img.height())
        w, h = self.img.width() * s, self.img.height() * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _k(self): return self._view().width() / self.img.width()

    def _to_view(self, r: QRectF) -> QRectF:
        v, k = self._view(), self._k()
        return QRectF(v.x() + r.x() * k, v.y() + r.y() * k, r.width() * k, r.height() * k)

    def _to_img(self, p: QPointF) -> QPointF:
        v, k = self._view(), self._k()
        return QPointF(min(max((p.x() - v.x()) / k, 0), self.img.width()), min(max((p.y() - v.y()) / k, 0), self.img.height()))

    def _hit(self, p: QPointF) -> str:
        """Qué parte del recorte está bajo el ratón: 'l','r','t','b' combinadas, 'move' o ''."""
        r = self._to_view(self.crop)
        e = ""
        if abs(p.y() - r.top()) <= H: e += "t"
        elif abs(p.y() - r.bottom()) <= H: e += "b"
        if abs(p.x() - r.left()) <= H: e += "l"
        elif abs(p.x() - r.right()) <= H: e += "r"
        inside_x = r.left() - H <= p.x() <= r.right() + H
        inside_y = r.top() - H <= p.y() <= r.bottom() + H
        if e and inside_x and inside_y: return e
        return "move" if r.contains(p) else ""

    CURSORS = {"t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
               "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
               "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
               "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
               "move": Qt.CursorShape.SizeAllCursor}

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton: return
        p = ev.position(); h = self._hit(p)
        if not h:                                      # fuera del recorte: empezar uno nuevo
            q = self._to_img(p); self.crop = QRectF(q, q); h = "br"
        self._drag = (h, self._to_img(p), QRectF(self.crop))

    def mouseMoveEvent(self, ev):
        p = ev.position()
        if not self._drag:
            self.setCursor(self.CURSORS.get(self._hit(p), Qt.CursorShape.CrossCursor)); return
        h, start, r0 = self._drag
        q = self._to_img(p); dx, dy = q.x() - start.x(), q.y() - start.y()
        W, Hh = self.img.width(), self.img.height()
        if h == "move":
            x = min(max(r0.x() + dx, 0), W - r0.width()); y = min(max(r0.y() + dy, 0), Hh - r0.height())
            self.crop = QRectF(x, y, r0.width(), r0.height())
        else:
            l, t, r, b = r0.left(), r0.top(), r0.right(), r0.bottom()
            if "l" in h: l = q.x()
            if "r" in h: r = q.x()
            if "t" in h: t = q.y()
            if "b" in h: b = q.y()
            self.crop = QRectF(QPointF(min(l, r), min(t, b)), QPointF(max(l, r), max(t, b)))
        self.update(); self.on_change()

    def mouseReleaseEvent(self, ev):
        self._drag = None
        if self.crop.width() < 2 or self.crop.height() < 2:     # clic suelto: volver a la imagen completa
            self.crop = QRectF(0, 0, self.img.width(), self.img.height())
        self.update(); self.on_change()

    def paintEvent(self, ev):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(C["canvas"]))
        v = self._view(); p.drawPixmap(v, self.pm, QRectF(self.pm.rect()))
        r = self._to_view(self.crop)
        shade = QColor(0, 0, 0, 120)                   # oscurece lo que se va a quitar
        p.fillRect(QRectF(v.left(), v.top(), v.width(), r.top() - v.top()), shade)
        p.fillRect(QRectF(v.left(), r.bottom(), v.width(), v.bottom() - r.bottom()), shade)
        p.fillRect(QRectF(v.left(), r.top(), r.left() - v.left(), r.height()), shade)
        p.fillRect(QRectF(r.right(), r.top(), v.right() - r.right(), r.height()), shade)
        p.setPen(QPen(QColor("#ffffff"), 1, Qt.PenStyle.DashLine)); p.drawRect(r)
        p.setPen(QPen(QColor(C["accent"]), 1)); p.setBrush(QColor("#ffffff"))
        for x in (r.left(), r.center().x(), r.right()):
            for y in (r.top(), r.center().y(), r.bottom()):
                if (x, y) != (r.center().x(), r.center().y()):
                    p.drawRect(QRectF(x - 4, y - 4, 8, 8))
        p.end()


class CropDialog(QDialog):
    def __init__(self, img: QImage, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Recortar imagen"))
        lay = QVBoxLayout(self)
        tip = QLabel(T("Arrastra para marcar el área que se conserva; ajústala desde los bordes o muévela desde dentro."))
        tip.setWordWrap(True); tip.setObjectName("muted"); lay.addWidget(tip)
        self.area = _CropArea(img, self._update_info); lay.addWidget(self.area, 1)
        row = QHBoxLayout()
        self.info = QLabel(); self.info.setObjectName("muted"); row.addWidget(self.info, 1)
        rst = QPushButton(T("Restablecer")); rst.setObjectName("flat"); rst.clicked.connect(self._reset); row.addWidget(rst)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Recortar"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(T("Cancelar"))
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); lay.addWidget(bb)
        self._update_info()

    def _reset(self):
        self.area.crop = QRectF(0, 0, self.area.img.width(), self.area.img.height())
        self.area.update(); self._update_info()

    def _update_info(self):
        r = self.crop_rect()
        self.info.setText(Tf("{0} × {1} px (de {2} × {3})", r.width(), r.height(), self.area.img.width(), self.area.img.height()))

    def crop_rect(self) -> QRect:
        """Recorte en píxeles enteros de la imagen, dentro de sus límites."""
        return self.area.crop.toAlignedRect().intersected(self.area.img.rect())
