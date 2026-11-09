# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Reglas horizontal y vertical como en Word/Illustrator: el cero está en la esquina superior izquierda
de la página bajo el cursor (o de la página actual) y se alinea por coordenadas globales, así que
siempre coincide con el borde real de la página aunque cambien el zoom, el desplazamiento o el marco."""
from core.i18n import T
from PyQt6.QtWidgets import QWidget, QMenu, QToolButton
from PyQt6.QtCore import Qt, QPoint, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from ui.styles import C

# puntos PDF por unidad, nombre visible, subdivisiones por número
UNITS = {"mm": (72 / 25.4, "mm", 10), "cm": (72 / 2.54, "cm", 10), "in": (72.0, "in", 8)}
NICE = [0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000]
SIZE = 20


def to_unit(pt: float, unit: str) -> float:
    return pt / UNITS[unit][0]


def fmt(pt: float, unit: str) -> str:
    v = to_unit(pt, unit)
    return f"{v:.1f} {UNITS[unit][1]}" if unit == "mm" else f"{v:.2f} {UNITS[unit][1]}"


class Ruler(QWidget):
    unit = "mm"            # compartidos por todas las pestañas (se guardan como preferencia)
    shown = True
    _loaded = False

    def __init__(self, viewer, horizontal: bool):
        super().__init__(viewer)
        if not Ruler._loaded:
            from core.settings import AppSettings
            st = AppSettings(); Ruler.unit, Ruler.shown, Ruler._loaded = st.get_ruler_unit(), st.get_rulers_shown(), True
        self.v, self.h = viewer, horizontal
        self.cursor_g = None                # posición global del ratón sobre una página
        self.setFixedHeight(SIZE) if horizontal else self.setFixedWidth(SIZE)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setToolTip(T("Arrastra hasta la página para crear una guía · clic derecho: unidades"))
        self.customContextMenuRequested.connect(lambda p: unit_menu(self.v, self.mapToGlobal(p)))

    # arrastrar desde la regla crea una guía (horizontal desde la regla de arriba, vertical desde la izquierda)
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton: self._dragging = True

    def mouseMoveEvent(self, ev):
        if getattr(self, "_dragging", False):
            self.v.ruler_drag("h" if self.h else "v", ev.globalPosition().toPoint())

    def mouseReleaseEvent(self, ev):
        if getattr(self, "_dragging", False):
            self._dragging = False
            self.v.ruler_drag("h" if self.h else "v", ev.globalPosition().toPoint(), done=True)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C["group_hdr"]))
        cv = self.v.ruler_page()
        if cv is not None and cv._prect and cv._prect.width:
            self._paint_scale(p, cv)
        p.setPen(QColor(C["border"]))
        if self.h: p.drawLine(0, SIZE - 1, self.width(), SIZE - 1)
        else: p.drawLine(SIZE - 1, 0, SIZE - 1, self.height())
        p.end()

    def _paint_scale(self, p, cv):
        o = self.mapFromGlobal(cv.mapToGlobal(QPoint(0, 0)))
        org, length = (o.x(), cv.width()) if self.h else (o.y(), cv.height())
        span = self.width() if self.h else self.height()
        pts_unit, _, sub = UNITS[Ruler.unit]
        pxu = cv.width() / cv._prect.width * pts_unit            # píxeles por unidad
        # zona de la página más clara, como en Word
        band = QRectF(org, 2, length, SIZE - 4) if self.h else QRectF(2, org, SIZE - 4, length)
        p.fillRect(band, QColor(C["white"]))
        step = next((n for n in NICE if n * pxu >= 48), NICE[-1])   # números cada ≥48 px
        if step < 1 and Ruler.unit != "in": sub = 5
        elif Ruler.unit == "in" and step < 1: sub = 4
        minor = step / sub
        f = QFont(self.font()); f.setPointSizeF(7); p.setFont(f)
        p.setPen(QPen(QColor(C["muted"]), 1))
        first = int((0 - org) / (minor * pxu)) - 1
        last = int((span - org) / (minor * pxu)) + 1
        for k in range(first, last + 1):
            val = k * minor
            x = org + val * pxu
            if x < 0 or x > span: continue
            is_major = abs(val / step - round(val / step)) < 1e-6
            is_half = not is_major and sub % 2 == 0 and abs((val / step) * 2 - round((val / step) * 2)) < 1e-6
            tick = SIZE * (0.55 if is_major else 0.35 if is_half else 0.2)
            if self.h: p.drawLine(int(x), SIZE - 1, int(x), int(SIZE - 1 - tick))
            else: p.drawLine(SIZE - 1, int(x), int(SIZE - 1 - tick), int(x))
            if is_major:
                txt = f"{abs(val):g}"
                if self.h:
                    p.drawText(int(x) + 2, 9, txt)
                else:
                    p.save(); p.translate(9, int(x) + 2); p.rotate(90); p.drawText(0, 0, txt); p.restore()
        if self.cursor_g is not None:                    # marca de la posición del ratón
            c = self.mapFromGlobal(self.cursor_g)
            p.setPen(QPen(QColor(C["accent"]), 1))
            if self.h: p.drawLine(c.x(), 0, c.x(), SIZE)
            else: p.drawLine(0, c.y(), SIZE, c.y())


def unit_menu(viewer, gpos):
    """Clic derecho en la regla: elegir unidades (se guardan como preferencia)."""
    m = QMenu(viewer)
    for key, label in (("mm", T("Milímetros (mm)")), ("cm", T("Centímetros (cm)")), ("in", T("Pulgadas (in)"))):
        a = m.addAction(label); a.setCheckable(True); a.setChecked(Ruler.unit == key)
        a.triggered.connect(lambda _=False, k=key: set_unit(k))
    m.exec(gpos)


def set_unit(key):
    from core.settings import AppSettings
    Ruler.unit = key
    AppSettings().set_ruler_unit(key)
    from PyQt6.QtWidgets import QApplication
    for w in QApplication.allWidgets():
        if isinstance(w, (Ruler, RulerCorner)): w.update()


class RulerCorner(QToolButton):
    """Esquina entre las dos reglas: muestra la unidad y abre el menú para cambiarla."""
    def __init__(self, viewer):
        super().__init__(viewer)
        self.v = viewer
        self.setFixedSize(SIZE, SIZE); self.setAutoRaise(True)
        self.setToolTip(T("Unidades de la regla"))
        self.setStyleSheet(f"QToolButton {{ background:{C['group_hdr']}; color:{C['muted']}; border:none;"
                           f" border-right:1px solid {C['border']}; border-bottom:1px solid {C['border']}; font-size:8px; }}")
        self.clicked.connect(lambda: unit_menu(self.v, self.mapToGlobal(QPoint(0, SIZE))))

    def paintEvent(self, ev):
        self.setText(UNITS[Ruler.unit][1])
        super().paintEvent(ev)
