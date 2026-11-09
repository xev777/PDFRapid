# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Rellenar y firmar (como en Acrobat): símbolos de un clic (✓, ✗, punto, línea), fecha e iniciales, para
completar documentos que no tienen campos. Parte de PageCanvas (ui/canvas.py)."""
import datetime
import uuid
from PyQt6.QtWidgets import QInputDialog
from core.i18n import T, lang
from core.settings import AppSettings
from models.annotation import Ann

# clave → (texto del menú, icono)
SYMBOLS = {"check": ("Marca de verificación ✓", "select"), "cross": ("Cruz ✗", "close"), "dot": ("Punto ●", "dot"),
           "line": ("Línea", "line"), "date": ("Fecha de hoy", "text"), "initials": ("Mis iniciales", "signature")}
CHECK = [(0.0, 0.55), (0.38, 0.92), (1.0, 0.08)]     # trazo de la ✓ dentro de su caja (0-1)


def today() -> str:
    return datetime.date.today().strftime("%m/%d/%Y" if lang() == "en" else "%d/%m/%Y")


def initials(parent=None) -> str:
    """Iniciales guardadas, o las del nombre de Preferencias; si no hay, se preguntan una vez y se recuerdan."""
    s = AppSettings()
    ini = s.get_str("initials", "").strip()
    if ini: return ini
    name = s.get_author().strip()
    if name: return "".join(w[0].upper() + "." for w in name.split()[:3])
    ini, ok = QInputDialog.getText(parent, T("Mis iniciales"), T("Escribe tus iniciales (se recordarán):"))
    if ok and ini.strip():
        s.set_str("initials", ini.strip()); return ini.strip()
    return ""


class FillMixin:
    fill_symbol = "check"                   # símbolo elegido en el botón «Rellenar y firmar»

    def _fill_anns(self, pt, sym) -> list:
        """Objetos del símbolo `sym` centrados en `pt` (tamaño según el tamaño de letra de la barra de formato)."""
        s = max(6, self.p_fsize) * self.zoom            # lado de la caja en píxeles
        color = self.p_fcolor.name()
        x0, y0 = pt.x() - s / 2, pt.y() - s / 2
        w = max(1.2, s / 9)
        if sym == "check":
            pts = [[x0 + fx * s, y0 + fy * s] for fx, fy in CHECK]
            a = Ann("ink", points=pts, stroke=color, stroke_width=w); a.fit_bbox()
            return [a]
        if sym == "cross":
            g = uuid.uuid4().hex[:8]                    # dos líneas agrupadas: se mueven juntas
            return [Ann("line", x1=x0, y1=y0, x2=x0 + s, y2=y0 + s, stroke=color, stroke_width=w, group=g),
                    Ann("line", x1=x0 + s, y1=y0, x2=x0, y2=y0 + s, stroke=color, stroke_width=w, group=g)]
        if sym == "dot":
            r = s / 4
            return [Ann("circle", x1=pt.x() - r, y1=pt.y() - r, x2=pt.x() + r, y2=pt.y() + r, stroke=color, fill=color,
                        stroke_width=0.5)]
        if sym == "line":
            return [Ann("line", x1=pt.x() - 1.5 * s, y1=pt.y(), x2=pt.x() + 1.5 * s, y2=pt.y(), stroke=color, stroke_width=w)]
        text = today() if sym == "date" else initials(self.window())
        if not text: return []
        return [Ann("text", x1=pt.x(), y1=pt.y() + s / 3, x2=pt.x() + 200, y2=pt.y() + s, text=text,
                    font_name=self.p_fname, font_size=self.p_fsize, text_color=color)]

    def _place_fill(self, pt):
        anns = self._fill_anns(pt, type(self).fill_symbol)
        if not anns: return
        self._snap()
        self.anns.extend(anns)
        self._pick(anns[0])
        self._redraw(); self._commit()
