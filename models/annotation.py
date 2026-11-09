# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Modelo de Anotación (Ann)"""
import copy
import math
from PyQt6.QtCore import QRectF, QPointF
from PyQt6.QtGui import QFont, QFontMetrics
from core.constants import HS

KIND_NAMES = {"line": "Línea", "rect": "Rectángulo", "rrect": "Rect. redondeado", "circle": "Círculo",
              "triangle": "Triángulo", "text": "Texto", "textbox": "Caja de texto", "highlight": "Resaltado",
              "comment": "Comentario", "arrow": "Flecha", "darrow": "Doble flecha", "arrow_shape": "Figura flecha",
              "image": "Imagen", "ink": "Dibujo a mano", "underline": "Subrayado", "strikeout": "Tachado",
              "signature": "Firma", "redact": "Tachado pendiente"}


# Estados de revisión de un comentario (modelo «Review» de PDF, como en Acrobat): clave → (texto, /State)
REVIEW_STATES = {"": ("Sin estado", "None"), "accepted": ("Aceptado", "Accepted"), "rejected": ("Rechazado", "Rejected"),
                 "cancelled": ("Cancelado", "Cancelled"), "completed": ("Completado", "Completed")}


class Ann:
    _n = 0
    SCALE = 1.5     # píxeles de pantalla por punto PDF; el visor lo actualiza con el zoom
    
    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        Ann._n += 1
        instance.id = Ann._n
        return instance

    def __init__(self, kind: str, **kw):
        self.kind = kind
        self.x1 = float(kw.get("x1", 0))
        self.y1 = float(kw.get("y1", 0))
        self.x2 = float(kw.get("x2", 0))
        self.y2 = float(kw.get("y2", 0))
        self.rotation = float(kw.get("rotation", 0))
        self.stroke = kw.get("stroke", "#0078d4")
        self.stroke_style = kw.get("stroke_style", "solid")
        self.stroke_width = max(0.5, float(kw.get("stroke_width", 1.5)))
        self.fill = kw.get("fill", None)
        self.opacity = max(0.1, min(1.0, float(kw.get("opacity", 1.0))))
        self.text = kw.get("text", "")
        self.font_name = kw.get("font_name", "Arial")
        self.font_size = max(4, int(kw.get("font_size", 12)))
        self.font_bold = bool(kw.get("font_bold", False))
        self.font_italic = bool(kw.get("font_italic", False))
        self.font_underline = bool(kw.get("font_underline", False))
        self.text_color = kw.get("text_color", "#000000")
        self.text_align = kw.get("text_align", "left")
        self.box_bg = kw.get("box_bg", None)
        self.box_border = kw.get("box_border", "#000000")
        self.box_bw = max(0.0, float(kw.get("box_bw", 1.0)))
        self.corner_r = float(kw.get("corner_r", 0))
        self.arrow_start = bool(kw.get("arrow_start", False))
        self.arrow_end = bool(kw.get("arrow_end", True))
        self.arrow_size = float(kw.get("arrow_size", 12))
        self.author = kw.get("author", "")
        self.date = kw.get("date", "")
        self.comment_visible = bool(kw.get("comment_visible", False))
        self.replies = [dict(r) for r in kw.get("replies", [])]   # comentario: [{author, date, text}]
        self.status = kw.get("status", "")                       # comentario: clave de REVIEW_STATES
        self.selected = False
        self.image_data = kw.get("image_data", "")
        self.points = [list(p) for p in kw.get("points", [])]     # trazo a mano (ink)
        self.group = kw.get("group", "")                         # objetos agrupados: mismo identificador
        self.locked = bool(kw.get("locked", False))              # bloqueado: no se selecciona ni se mueve
        self.hidden = bool(kw.get("hidden", False))              # oculto: no se ve ni se imprime

    def qfont(self) -> QFont:
        """Fuente en pantalla: `font_size` son puntos PDF, escalados al zoom actual (SCALE)."""
        f = QFont(self.font_name)
        f.setWeight(QFont.Weight.Bold if self.font_bold else QFont.Weight.Normal)
        f.setItalic(self.font_italic)
        f.setUnderline(self.font_underline)
        f.setPixelSize(max(1, round(self.font_size * Ann.SCALE)))
        return f

    def brect(self) -> QRectF:
        if self.kind == "text":
            try:
                fm = QFontMetrics(self.qfont())
                lines = (self.text or "").split('\n')
                tw = max((fm.horizontalAdvance(l) for l in lines), default=80) + 12
                th = fm.height() * len(lines) + 12
                return QRectF(self.x1, self.y1 - fm.ascent(), tw, th)
            except Exception:
                return QRectF(self.x1, self.y1, 120, 24)
        if self.kind in ("line", "arrow", "darrow"):
            pad = max(self.stroke_width, 10) + self.arrow_size
            return QRectF(min(self.x1, self.x2) - pad, min(self.y1, self.y2) - pad,
                          abs(self.x2 - self.x1) + 2 * pad, abs(self.y2 - self.y1) + 2 * pad)
        if self.kind == "image":
            return QRectF(min(self.x1, self.x2), min(self.y1, self.y2),
                          max(abs(self.x2 - self.x1), 10), max(abs(self.y2 - self.y1), 10))
        return QRectF(min(self.x1, self.x2), min(self.y1, self.y2),
                      max(abs(self.x2 - self.x1), 10), max(abs(self.y2 - self.y1), 10))

    def _rot(self, pt: QPointF, deg: float) -> QPointF:
        """Gira `pt` alrededor del centro del objeto (mismo sentido que QPainter.rotate)."""
        if not deg: return QPointF(pt)
        c = self.brect().center(); a = math.radians(deg)
        dx, dy = pt.x() - c.x(), pt.y() - c.y()
        return QPointF(c.x() + dx * math.cos(a) - dy * math.sin(a), c.y() + dx * math.sin(a) + dy * math.cos(a))

    def handles(self):
        """8 tiradores de tamaño, girados junto con el objeto (se rota desde las esquinas: rot_zone)."""
        r = self.brect()
        cx, cy = r.center().x(), r.center().y()
        pts = [
            QPointF(r.left(), r.top()), QPointF(cx, r.top()), QPointF(r.right(), r.top()),
            QPointF(r.left(), cy), QPointF(r.right(), cy),
            QPointF(r.left(), r.bottom()), QPointF(cx, r.bottom()), QPointF(r.right(), r.bottom()),
        ]
        return [self._rot(p, self.rotation) for p in pts]

    def hit(self, pt: QPointF, m=6) -> bool:
        if self.locked or self.hidden: return False
        return self.brect().adjusted(-m, -m, m, m).contains(self._rot(pt, -self.rotation))

    def rot_zone(self, pt: QPointF) -> bool:
        """Zona de giro: justo por fuera de cada esquina (como los graficadores profesionales)."""
        p = self._rot(pt, -self.rotation)
        r = self.brect().adjusted(-2, -2, 2, 2)
        if r.contains(p): return False
        return any(HS / 2 + 1 < math.hypot(p.x() - c.x(), p.y() - c.y()) <= 26
                   for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()))

    def hit_handle(self, pt: QPointF) -> int:
        h = HS / 2 + 2
        for i, p in enumerate(self.handles()):
            if QRectF(p.x() - h, p.y() - h, h * 2, h * 2).contains(pt):
                return i
        return -1

    def move(self, dx, dy):
        self.x1 += dx; self.y1 += dy; self.x2 += dx; self.y2 += dy
        self.points = [[x + dx, y + dy] for x, y in self.points]

    def fit_bbox(self):
        """Rectángulo = caja de los puntos del trazo."""
        xs, ys = [p[0] for p in self.points], [p[1] for p in self.points]
        self.x1, self.y1, self.x2, self.y2 = min(xs), min(ys), max(xs), max(ys)

    def resize(self, hi, dx, dy):
        ob = (self.x1, self.y1, self.x2, self.y2)
        if self.rotation:              # objeto girado: el arrastre va en su orientación y la esquina opuesta queda fija
            a = math.radians(-self.rotation)
            dx, dy = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
            opp = {0: 7, 1: 6, 2: 5, 3: 4, 4: 3, 5: 2, 6: 1, 7: 0}[hi]
            anchor = self.handles()[opp]
        self._resize(hi, dx, dy)
        if self.rotation:
            new = self.handles()[opp]
            self.x1 += anchor.x() - new.x(); self.x2 += anchor.x() - new.x()
            self.y1 += anchor.y() - new.y(); self.y2 += anchor.y() - new.y()
        if self.points:                       # el trazo se escala con su caja
            ox1, oy1, ox2, oy2 = ob
            sx = (self.x2 - self.x1) / ((ox2 - ox1) or 1)
            sy = (self.y2 - self.y1) / ((oy2 - oy1) or 1)
            self.points = [[self.x1 + (x - ox1) * sx, self.y1 + (y - oy1) * sy] for x, y in self.points]

    def _resize(self, hi, dx, dy):
        if self.kind == "text":
            if hi in (0, 3, 5): self.x1 += dx
            if hi in (2, 4, 7): self.x2 += dx
            if hi in (0, 1, 2): self.y1 += dy
            if hi in (5, 6, 7): self.y2 += dy
            return
        # el tirador mueve el borde que se ve a ese lado (los objetos volteados tienen x1 > x2 o y1 > y2)
        lx, rx = ("x1", "x2") if self.x1 <= self.x2 else ("x2", "x1")
        ty, by = ("y1", "y2") if self.y1 <= self.y2 else ("y2", "y1")
        if hi in (0, 3, 5): setattr(self, lx, getattr(self, lx) + dx)
        if hi in (2, 4, 7): setattr(self, rx, getattr(self, rx) + dx)
        if hi in (0, 1, 2): setattr(self, ty, getattr(self, ty) + dy)
        if hi in (5, 6, 7): setattr(self, by, getattr(self, by) + dy)

        if self.kind not in ("line", "arrow", "darrow", "image", "triangle", "arrow_shape"):
            if self.x1 > self.x2: self.x1, self.x2 = self.x2, self.x1
            if self.y1 > self.y2: self.y1, self.y2 = self.y2, self.y1

    def thread_text(self) -> str:
        """Texto del comentario con sus respuestas, para el globo en pantalla."""
        out = [self.text]
        for r in self.replies:
            out.append(f"↳ {r.get('author') or '—'}: {r.get('text', '')}")
        return "\n".join(out)

    def clone(self):
        return copy.deepcopy(self)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != 'selected'}

    @classmethod
    def from_dict(cls, d: dict):
        a = cls(d['kind'], **{k: v for k, v in d.items() if k not in ('kind', 'id', 'selected')})
        a.id = d.get('id', a.id)
        return a