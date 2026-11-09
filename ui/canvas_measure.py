# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Herramienta Medir: distancia, perímetro (varios tramos) y área (polígono), a escala de plano (p. ej. 1 cm = 1 m).
Parte de PageCanvas (ui/canvas.py)."""
import json
import math
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from core.i18n import T, Tf

PT = {"mm": 72 / 25.4, "cm": 72 / 2.54, "m": 7200 / 2.54, "km": 7200000 / 2.54, "in": 72.0, "ft": 864.0, "yd": 2592.0,
      "pt": 1.0}                                    # puntos PDF por unidad
MODES = {"dist": "Distancia", "perim": "Perímetro (varios tramos)", "area": "Área (polígono)"}


def shoelace(pts) -> float:
    """Área de un polígono (fórmula del cordón de zapato), en las unidades de los puntos al cuadrado."""
    n = len(pts)
    return abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2


def length(pts, closed=False) -> float:
    segs = list(zip(pts, pts[1:])) + ([(pts[-1], pts[0])] if closed and len(pts) > 2 else [])
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs)


class Scale:
    """Escala de plano: `paper` (pt en el papel) equivale a `real` en la unidad `unit`. Sin escala, paper=0."""
    paper, real, unit, _loaded = 0.0, 1.0, "m", False
    paper_unit = "cm"

    @classmethod
    def load(cls):
        if cls._loaded: return
        cls._loaded = True
        from core.settings import AppSettings
        try:
            d = json.loads(AppSettings().get_str("measure_scale", "") or "{}")
            cls.paper, cls.paper_unit = float(d.get("paper", 0)), d.get("paper_unit", "cm")
            cls.real, cls.unit = float(d.get("real", 1)), d.get("unit", "m")
            if cls.unit not in PT or cls.paper_unit not in PT: cls.paper = 0.0
        except (ValueError, TypeError):
            cls.paper = 0.0

    @classmethod
    def set(cls, paper_val, paper_unit, real, unit):
        from core.settings import AppSettings
        cls.paper, cls.paper_unit, cls.real, cls.unit, cls._loaded = paper_val * PT[paper_unit], paper_unit, real, unit, True
        AppSettings().set_str("measure_scale", json.dumps({"paper": cls.paper, "paper_unit": paper_unit,
                                                           "real": real, "unit": unit}) if paper_val else "")

    @classmethod
    def clear(cls):
        from core.settings import AppSettings
        cls.paper, cls._loaded = 0.0, True
        AppSettings().set_str("measure_scale", "")

    @classmethod
    def active(cls) -> bool:
        cls.load(); return cls.paper > 0

    @classmethod
    def label(cls) -> str:
        if not cls.active(): return T("sin escala (medidas del papel)")
        return f"{cls.paper / PT[cls.paper_unit]:g} {cls.paper_unit} = {cls.real:g} {cls.unit}"

    @classmethod
    def length(cls, pt: float) -> str:
        """Largo en puntos del papel → texto en la unidad real (o la de las reglas sin escala)."""
        if cls.active():
            v = pt / cls.paper * cls.real
            return f"{v:.2f} {cls.unit}"
        from ui.ruler import Ruler, fmt
        return fmt(pt, Ruler.unit)

    @classmethod
    def area(cls, pt2: float) -> str:
        if cls.active():
            v = pt2 / cls.paper ** 2 * cls.real ** 2
            return f"{v:.2f} {cls.unit}²"
        from ui.ruler import Ruler
        u = Ruler.unit
        v = pt2 / PT[u] ** 2
        return f"{v:.1f} {u}²" if u == "mm" else f"{v:.2f} {u}²"


class MeasureMixin:
    measure_mode = "dist"                     # distancia | perim | area (compartido por las pestañas)

    def _mpoly_reset(self):
        self._mpoly, self._mhover, self._mdone = [], None, False

    def _mk(self) -> float:
        """Puntos PDF por píxel."""
        return self._prect.width / self._bw if self._prect and self._bw else 1.0

    def _mpoly_pts(self, with_hover=True):
        pts = list(getattr(self, "_mpoly", []))
        if with_hover and not self._mdone and self._mhover is not None and pts: pts.append(self._mhover)
        k = self._mk()
        return [(p.x() * k, p.y() * k) for p in pts]

    def _mpoly_snap(self, pt, mods):
        """Con Ctrl el tramo avanza en pasos de ángulo desde el último vértice."""
        if not self._mpoly or not mods & Qt.KeyboardModifier.ControlModifier: return pt
        a = self._mpoly[-1]
        d = math.hypot(pt.x() - a.x(), pt.y() - a.y()); step = self._step()
        ang = round(math.degrees(math.atan2(pt.y() - a.y(), pt.x() - a.x())) / step) * step
        return QPointF(a.x() + d * math.cos(math.radians(ang)), a.y() + d * math.sin(math.radians(ang)))

    def _mpoly_click(self, pt, mods):
        if getattr(self, "_mdone", False) or not hasattr(self, "_mpoly"): self._mpoly_reset()
        self._mpoly.append(self._mpoly_snap(pt, mods)); self._mhover = None; self.update()

    def _mpoly_move(self, pt, mods):
        if getattr(self, "_mpoly", None) and not self._mdone:
            self._mhover = self._mpoly_snap(pt, mods); self.update()

    def _mpoly_finish(self):
        if not getattr(self, "_mpoly", None) or self._mdone: return False
        # el doble clic añade el mismo punto dos veces: se quitan los repetidos al final
        while len(self._mpoly) > 1 and math.hypot(self._mpoly[-1].x() - self._mpoly[-2].x(),
                                                  self._mpoly[-1].y() - self._mpoly[-2].y()) < 2:
            self._mpoly.pop()
        self._mdone, self._mhover = True, None
        txt = self.mpoly_text()
        if txt: self._status(Tf("Medida: {0}  ·  Escala: {1}. Haz clic para medir otra; Esc borra.", txt, Scale.label()))
        self.update()
        return True

    def _mpoly_back(self):
        if getattr(self, "_mpoly", None) and not self._mdone:
            self._mpoly.pop(); self.update(); return True
        return False

    def mpoly_text(self) -> str:
        pts = self._mpoly_pts()
        if len(pts) < 2: return ""
        if type(self).measure_mode == "area":
            if len(pts) < 3: return Tf("perímetro {0}", Scale.length(length(pts)))
            return Tf("área {0}  ·  perímetro {1}", Scale.area(shoelace(pts)), Scale.length(length(pts, closed=True)))
        return Tf("{0} en {1} tramo(s)", Scale.length(length(pts)), len(pts) - 1)

    def _paint_mpoly(self):
        if not getattr(self, "_mpoly", None): return
        pts = list(self._mpoly) + ([self._mhover] if self._mhover is not None and not self._mdone else [])
        area = type(self).measure_mode == "area"
        acc = QColor(self._accent())
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if area and len(pts) > 2:
            fill = QColor(acc); fill.setAlpha(45); p.setBrush(fill); p.setPen(QPen(acc, 1.5))
            p.drawPolygon(QPolygonF(pts))
        else:
            p.setPen(QPen(acc, 1.5)); p.drawPolyline(QPolygonF(pts))
        p.setBrush(QColor("#ffffff")); p.setPen(QPen(acc, 1.2))
        for q in self._mpoly: p.drawEllipse(q, 3, 3)
        txt = self.mpoly_text()
        if txt:
            if not self._mdone: txt += "   " + T("(doble clic o Intro termina)")
            fm = p.fontMetrics(); w, h = fm.horizontalAdvance(txt) + 12, fm.height() + 6
            b = pts[-1]
            x = min(max(b.x() + 10, 2), self.width() - w - 2); y = min(max(b.y() + 10, 2), self.height() - h - 2)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(acc); p.drawRoundedRect(QRectF(x, y, w, h), 4, 4)
            p.setPen(QColor("#ffffff")); p.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, txt)
        p.end()

    def _accent(self):
        from ui.styles import C
        return C["accent"]


def scale_dialog(parent) -> bool:
    """Escala del plano: «1 cm en el papel = 1 m real». Devuelve True si se cambió."""
    from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                                 QVBoxLayout)
    Scale.load()
    dlg = QDialog(parent); dlg.setWindowTitle(T("Escala de medición")); lay = QVBoxLayout(dlg)
    info = QLabel(T("Para medir planos: indica cuánto mide en la realidad un tramo del papel.\n"
                    "Ejemplo: en un plano a escala 1:100, 1 cm del papel son 1 m reales."))
    info.setWordWrap(True); lay.addWidget(info)
    row = QHBoxLayout()
    sp_p = QDoubleSpinBox(); sp_p.setRange(0.001, 1e6); sp_p.setDecimals(3)
    cb_p = QComboBox(); cb_p.addItems(["mm", "cm", "in", "pt"])
    sp_r = QDoubleSpinBox(); sp_r.setRange(0.001, 1e9); sp_r.setDecimals(3)
    cb_r = QComboBox(); cb_r.addItems(["mm", "cm", "m", "km", "in", "ft", "yd"])
    if Scale.active():
        sp_p.setValue(Scale.paper / PT[Scale.paper_unit]); cb_p.setCurrentText(Scale.paper_unit)
        sp_r.setValue(Scale.real); cb_r.setCurrentText(Scale.unit)
    else:
        sp_p.setValue(1); cb_p.setCurrentText("cm"); sp_r.setValue(1); cb_r.setCurrentText("m")
    for w in (QLabel(T("En el papel")), sp_p, cb_p, QLabel("="), QLabel(T("en la realidad")), sp_r, cb_r): row.addWidget(w)
    lay.addLayout(row)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    b_none = bb.addButton(T("Sin escala"), QDialogButtonBox.ButtonRole.ResetRole)
    bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
    b_none.clicked.connect(lambda: dlg.done(2))
    lay.addWidget(bb)
    r = dlg.exec()
    if r == 2: Scale.clear(); return True
    if r != QDialog.DialogCode.Accepted: return False
    Scale.set(sp_p.value(), cb_p.currentText(), sp_r.value(), cb_r.currentText())
    return True
