# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Guías (arrastradas desde las reglas) y ajuste magnético a guías y a objetos, como en un programa de dibujo.
Las guías se guardan por página en puntos PDF (no dependen del zoom) y solo existen en pantalla: no van al PDF.
- Crear: arrastrar desde la regla hasta la página.  Mover: arrastrarlas con la herramienta Seleccionar.
- Borrar: arrastrarlas fuera de la página, clic derecho → Eliminar guía, o Vista → Guías → Borrar todas.
- Ajuste: al crear, mover o redimensionar objetos, los bordes y centros se pegan a guías/objetos cercanos.
  Alt mantenido lo desactiva momentáneamente."""
from core.i18n import T
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtWidgets import QMenu

GUIDE_COLOR = QColor("#00a8e8")
SNAP_COLOR = QColor("#e0218a")
SNAP_PX = 6        # distancia de atracción en pantalla
GRAB_PX = 4        # distancia para agarrar una guía


class GuidesMixin:
    guides_visible = True
    snap_guides = True
    snap_objects = True
    _opts_loaded = False

    @classmethod
    def load_guide_options(cls):
        if cls._opts_loaded: return
        from core.settings import AppSettings
        s = AppSettings()
        cls.guides_visible, cls.snap_guides, cls.snap_objects = s.get_bool("guides_visible", True), \
            s.get_bool("snap_guides", True), s.get_bool("snap_objects", True)
        cls._opts_loaded = True

    def init_guides(self):
        self.load_guide_options()
        self.guides = {"v": [], "h": []}      # el visor lo sustituye por su diccionario (sobrevive a reconstrucciones)
        self._guide_preview = None             # (eje, valor en pt) mientras se arrastra desde la regla
        self._gdrag = None                     # (eje, índice) de la guía que se está moviendo
        self._snap_lines = []                  # líneas magenta del ajuste en curso
        self._mv0 = None                       # (caja inicial, punto inicial) al mover objetos

    # ── conversión ──
    def _gk(self) -> float:
        return self._bw / self._prect.width if self._prect and self._prect.width else 1.0

    def _guide_at(self, pt):
        if not self.guides_visible: return None
        k = self._gk()
        for axis, coord in (("v", pt.x()), ("h", pt.y())):
            for i, g in enumerate(self.guides[axis]):
                if abs(g * k - coord) <= GRAB_PX: return axis, i
        return None

    def add_guide(self, axis, value_pt):
        self.guides[axis].append(value_pt)
        self.sig_changed.emit(self.page_num)
        self.update()

    def clear_guides(self):
        if self.guides["v"] or self.guides["h"]: self.sig_changed.emit(self.page_num)
        self.guides["v"].clear(); self.guides["h"].clear(); self.update()

    # ── ajuste magnético ──
    @staticmethod
    def _snap_box(a) -> QRectF:
        if a.kind in ("line", "arrow", "darrow"):
            return QRectF(QPointF(min(a.x1, a.x2), min(a.y1, a.y2)), QPointF(max(a.x1, a.x2), max(a.y1, a.y2)))
        return a.brect()

    def _snap_targets(self, exclude=()):
        """Coordenadas (px) a las que se pegan los objetos: guías, página y bordes/centros de otros objetos."""
        xs, ys = [], []
        k = self._gk()
        if self.snap_guides and self.guides_visible:
            xs += [g * k for g in self.guides["v"]]; ys += [g * k for g in self.guides["h"]]
        if self.snap_objects:
            xs += [0, self._bw / 2, self._bw]; ys += [0, self._bh / 2, self._bh]
            for a in self.anns:
                if a in exclude: continue
                r = self._snap_box(a)
                xs += [r.left(), r.center().x(), r.right()]; ys += [r.top(), r.center().y(), r.bottom()]
        return xs, ys

    @staticmethod
    def _nearest(values, targets):
        """Menor corrección (≤ SNAP_PX) que lleva alguno de `values` a algún objetivo: (delta, objetivo) o None."""
        best = None
        for v in values:
            for t in targets:
                d = t - v
                if abs(d) <= SNAP_PX and (best is None or abs(d) < abs(best[0])): best = (d, t)
        return best

    def _snapping(self, mods) -> bool:
        return (self.snap_guides or self.snap_objects) and not mods & Qt.KeyboardModifier.AltModifier

    def _magnet_pt(self, pt, mods, exclude=()):
        """Punto pegado a la guía/objeto más cercano (al dibujar o redimensionar)."""
        self._snap_lines = []
        if not self._snapping(mods): return pt
        xs, ys = self._snap_targets(exclude)
        x, y = pt.x(), pt.y()
        bx, by = self._nearest([x], xs), self._nearest([y], ys)
        if bx: x += bx[0]; self._snap_lines.append(("v", bx[1]))
        if by: y += by[0]; self._snap_lines.append(("h", by[1]))
        return QPointF(x, y)

    def _magnet_offset(self, box, off, mods, exclude):
        """Corrige el desplazamiento `off` para que bordes o centro de `box` (ya desplazada) se peguen."""
        self._snap_lines = []
        if not self._snapping(mods): return off
        xs, ys = self._snap_targets(exclude)
        bx = self._nearest([box.left(), box.center().x(), box.right()], xs)
        by = self._nearest([box.top(), box.center().y(), box.bottom()], ys)
        dx, dy = off.x(), off.y()
        if bx: dx += bx[0]; self._snap_lines.append(("v", bx[1]))
        if by: dy += by[0]; self._snap_lines.append(("h", by[1]))
        return QPointF(dx, dy)

    def _move_snapped(self, targets, pt, mods):
        """Mover objetos siguiendo al ratón desde donde se agarraron, con ajuste magnético."""
        union = lambda: _union([self._snap_box(a) for a in targets])
        if self._mv0 is None: self._mv0 = (union(), QPointF(self._dragl))
        r0, p0 = self._mv0
        off = pt - p0
        off = self._magnet_offset(r0.translated(off), off, mods, targets)
        d = (r0.topLeft() + off) - union().topLeft()
        for a in targets: a.move(d.x(), d.y())

    # ── ratón sobre guías ──
    def _guide_press(self, pt) -> bool:
        g = self._guide_at(pt)
        if not g or any(a.hit(pt) for a in self.anns): return False
        self._gdrag = g
        return True

    def _guide_move(self, pt) -> bool:
        if not self._gdrag: return False
        axis, i = self._gdrag; k = self._gk()
        self.guides[axis][i] = (pt.x() if axis == "v" else pt.y()) / k
        out = not self.rect().contains(pt.toPoint())           # fuera de la página: se borrará al soltar
        self.setCursor(Qt.CursorShape.ForbiddenCursor if out else
                       Qt.CursorShape.SplitHCursor if axis == "v" else Qt.CursorShape.SplitVCursor)
        self.update()
        return True

    def _guide_release(self, pt) -> bool:
        if not self._gdrag: return False
        axis, i = self._gdrag; self._gdrag = None
        if not self.rect().contains(pt.toPoint()): del self.guides[axis][i]
        self.sig_changed.emit(self.page_num)
        self.setCursor(getattr(self, "_tool_cursor", Qt.CursorShape.ArrowCursor)); self.update()
        return True

    def _guide_hover(self, pt) -> bool:
        g = self._guide_at(pt)
        if not g or any(a.hit(pt) for a in self.anns): return False
        self.setCursor(Qt.CursorShape.SplitHCursor if g[0] == "v" else Qt.CursorShape.SplitVCursor)
        return True

    def _guide_menu(self, pt, gpt) -> bool:
        g = self._guide_at(pt)
        if not g: return False
        m = QMenu(self)
        a_del = m.addAction(T("Eliminar guía")); a_all = m.addAction(T("Borrar las guías de esta página"))
        ch = m.exec(gpt)
        if ch == a_del: del self.guides[g[0]][g[1]]; self.update(); self.sig_changed.emit(self.page_num)
        elif ch == a_all: self.clear_guides()
        return True

    # ── dibujo ──
    def paint_guides(self, p: QPainter):
        k = self._gk()
        if self.guides_visible:
            p.setPen(QPen(GUIDE_COLOR, 1))
            for x in self.guides["v"]: p.drawLine(QPointF(x * k, 0), QPointF(x * k, self.height()))
            for y in self.guides["h"]: p.drawLine(QPointF(0, y * k), QPointF(self.width(), y * k))
        if self._guide_preview:
            axis, v = self._guide_preview
            p.setPen(QPen(GUIDE_COLOR, 1, Qt.PenStyle.DashLine))
            if axis == "v": p.drawLine(QPointF(v * k, 0), QPointF(v * k, self.height()))
            else: p.drawLine(QPointF(0, v * k), QPointF(self.width(), v * k))
        if self._snap_lines:
            p.setPen(QPen(SNAP_COLOR, 1, Qt.PenStyle.DashLine))
            for axis, v in self._snap_lines:
                if axis == "v": p.drawLine(QPointF(v, 0), QPointF(v, self.height()))
                else: p.drawLine(QPointF(0, v), QPointF(self.width(), v))


def _union(rects):
    r = QRectF(rects[0])
    for q in rects[1:]: r = r.united(q)
    return r
