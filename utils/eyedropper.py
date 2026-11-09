# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Cuentagotas y botón selector de color"""
from core.logger import log
from PyQt6.QtWidgets import QWidget, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QSize
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QGuiApplication, QPixmap

class Eyedropper(QWidget):
    picked = pyqtSignal(QColor)

    def __init__(self):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self._color = QColor(Qt.GlobalColor.white)
        self._pos = QPoint()
        try:
            geo = QRect()
            for s in QGuiApplication.screens():
                geo = geo.united(s.geometry())
            self.setGeometry(geo)
            self._shot = QGuiApplication.primaryScreen().grabWindow(0, geo.x(), geo.y(), geo.width(), geo.height())
        except Exception:
            self._shot = QPixmap(1, 1)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.showFullScreen()

    def mouseMoveEvent(self, ev):
        self._pos = ev.globalPosition().toPoint()
        loc = self._pos - self.geometry().topLeft()
        try:
            img = self._shot.toImage()
            if 0 <= loc.x() < img.width() and 0 <= loc.y() < img.height():
                self._color = QColor(img.pixel(loc.x(), loc.y()))
        except Exception:
            pass
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self._color)
        self.close()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape: self.close()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 80))
        cx, cy = self._pos.x(), self._pos.y()
        loc = QPoint(cx, cy) - self.geometry().topLeft()
        Z, N = 8, 13
        half, bw = N // 2, N * Z
        lx = cx + 20 if cx + 20 + bw < self.width() else cx - bw - 12
        ly = cy + 20 if cy + 20 + bw < self.height() else cy - bw - 12
        lx, ly = max(0, lx), max(0, ly)
        try:
            img = self._shot.toImage()
            for row in range(N):
                for col in range(N):
                    px, py = loc.x() - half + col, loc.y() - half + row
                    c = QColor(img.pixel(px, py)) if 0 <= px < img.width() and 0 <= py < img.height() else QColor(Qt.GlobalColor.gray)
                    p.fillRect(lx + col * Z, ly + row * Z, Z, Z, c)
        except Exception:
            pass
        mx, my = lx + half * Z, ly + half * Z
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawLine(mx - Z, my, mx + Z * 2, my)
        p.drawLine(mx, my - Z, mx, my + Z * 2)
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.drawLine(mx - Z + 1, my, mx + Z * 2 - 1, my)
        p.drawLine(mx, my - Z + 1, mx, my + Z * 2 - 1)
        p.setPen(QPen(QColor(40, 40, 40), 2))
        p.drawRect(lx, ly, bw, bw)
        r, g, b = self._color.red(), self._color.green(), self._color.blue()
        p.fillRect(lx, ly + bw + 2, 80, 22, self._color)
        lum = (r * 299 + g * 587 + b * 114) // 1000
        p.setPen(QPen(QColor(0, 0, 0) if lum > 128 else QColor(255, 255, 255)))
        p.setFont(QFont("Consolas", 9))
        p.drawText(QRect(lx, ly + bw + 2, 80, 22), Qt.AlignmentFlag.AlignCenter, f"#{r:02X}{g:02X}{b:02X}")
        p.end()


class CPBtn(QPushButton):
    changed = pyqtSignal(QColor)

    def __init__(self, color: QColor = None, alpha=False, label="", parent=None):
        super().__init__(parent)
        self._color = color or QColor("#000000")
        self._alpha = alpha
        self._lbl = label
        self._restyle()
        self.clicked.connect(self._pick)
        self.setFixedSize(42, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _pick(self):
        from dialogs.color_picker import pick_color  # import diferido: evita import circular
        c = pick_color(self, self._color, allow_alpha=self._alpha, title=self._lbl or "Color")
        if c is not None:
            self.set(c)

    def eyedrop(self):
        try:
            e = Eyedropper()
            e.picked.connect(self.set)
            e.show()
        except Exception as ex:
            log.error(f"Eyedropper: {ex}")

    def set(self, color: QColor):
        self._color = color
        self._restyle()
        self.changed.emit(color)

    def _restyle(self):
        r, g, b, a = self._color.red(), self._color.green(), self._color.blue(), self._color.alpha()
        lum = (r * 299 + g * 587 + b * 114) // 1000
        tc = "#111" if lum > 128 else "#eee"
        bg = f"rgba({r},{g},{b},{a})" if self._alpha else f"rgb({r},{g},{b})"
        # muestra de color (sin texto): el código va en la ayuda emergente
        self.setStyleSheet(f"QPushButton{{background:{bg};border:1px solid rgba(0,0,0,60);border-radius:6px;min-width:0;padding:0;}}"
                           f"QPushButton:hover{{border:2px solid {tc};}}")
        self.setText("")
        self.setToolTip(f"{self._lbl}  #{r:02X}{g:02X}{b:02X}".strip())

    @property
    def color(self):
        return self._color

def _eye(slot, tip="Cuentagotas"):
    from ui.icons import get_icon
    b = QPushButton()
    b.setIcon(get_icon("eyedropper"))
    b.setIconSize(QSize(15, 15))
    b.setObjectName("icon")
    b.setFixedSize(30, 30)
    b.setToolTip(tip)
    b.clicked.connect(slot)
    return b