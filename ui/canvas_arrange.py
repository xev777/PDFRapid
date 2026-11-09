# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Organizar objetos: alinear, distribuir, voltear, agrupar, bloquear, ocultar, copiar formato y posición exacta.
Parte de PageCanvas (ui/canvas.py)."""
import base64
import uuid
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QSpinBox, QVBoxLayout, QLabel)
from PyQt6.QtCore import QPointF, QRectF, QBuffer, QIODevice
from PyQt6.QtGui import QImage
from core.i18n import T, Tf
from ui.icons import get_icon

LINE_KINDS = ("line", "arrow", "darrow", "arrow_shape")
NO_MIRROR = ("text", "textbox", "comment", "highlight", "underline", "strikeout", "redact", "signature")
NO_SIZE = ("text", "comment")             # su tamaño lo da el texto o el icono
STYLE_KEYS = ("stroke", "stroke_style", "stroke_width", "fill", "opacity", "font_name", "font_size", "font_bold",
              "font_italic", "font_underline", "text_color", "text_align", "box_bg", "box_border", "box_bw",
              "corner_r", "arrow_size")
ALIGN = {"left": "Alinear a la izquierda", "hcenter": "Centrar horizontalmente", "right": "Alinear a la derecha",
         "top": "Alinear arriba", "vcenter": "Centrar verticalmente", "bottom": "Alinear abajo"}


def gbox(a) -> QRectF:
    """Caja del objeto sin girar: la de sus puntos para líneas y flechas, la de dibujo para el resto."""
    if a.kind in LINE_KINDS:
        return QRectF(QPointF(min(a.x1, a.x2), min(a.y1, a.y2)), QPointF(max(a.x1, a.x2), max(a.y1, a.y2)))
    return a.brect()


def vbox(a) -> QRectF:
    """Caja que ocupa el objeto en la página tal como se ve (con su giro)."""
    r = gbox(a)
    if not a.rotation: return r
    pts = [a._rot(p, a.rotation) for p in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight())]
    xs, ys = [p.x() for p in pts], [p.y() for p in pts]
    return QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))


def union(anns) -> QRectF:
    r = QRectF()
    for a in anns: r = r.united(vbox(a)) if not r.isNull() else vbox(a)
    return r


def mirror(a, horizontal: bool):
    """Voltea el objeto sobre su centro. El texto no se voltea (quedaría ilegible)."""
    if a.kind in NO_MIRROR: return
    c = a.brect().center()
    if a.kind == "ink":
        a.points = [[2 * c.x() - x, y] if horizontal else [x, 2 * c.y() - y] for x, y in a.points]
    elif a.kind == "image" and a.image_data:
        img = QImage.fromData(base64.b64decode(a.image_data))
        if not img.isNull():
            out = img.mirrored(horizontal, not horizontal)
            buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly)
            out.save(buf, "PNG") if out.hasAlphaChannel() else out.save(buf, "JPG", 92)
            a.image_data = base64.b64encode(bytes(buf.data())).decode("ascii")
    elif a.kind in LINE_KINDS or a.kind == "triangle":
        if horizontal: a.x1, a.x2 = a.x2, a.x1
        else: a.y1, a.y2 = a.y2, a.y1
    a.rotation = (-a.rotation) % 360     # el espejo de un giro θ es un giro −θ


def set_box(a, new: QRectF):
    """Lleva el objeto a la caja `new` (sin girar), escalando sus puntos."""
    old = gbox(a)
    if a.kind in NO_SIZE:
        a.move(new.x() - old.x(), new.y() - old.y()); return

    def fx(x): return new.x() + (x - old.x()) * new.width() / old.width() if old.width() > 0.01 else x + new.x() - old.x()

    def fy(y): return new.y() + (y - old.y()) * new.height() / old.height() if old.height() > 0.01 else y + new.y() - old.y()
    a.x1, a.x2, a.y1, a.y2 = fx(a.x1), fx(a.x2), fy(a.y1), fy(a.y2)
    a.points = [[fx(x), fy(y)] for x, y in a.points]


class GeometryDialog(QDialog):
    """Posición, tamaño y giro exactos en milímetros (desde la esquina superior izquierda de la página)."""

    def __init__(self, a, k, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Posición y tamaño"))
        self.k = k                                        # píxeles por milímetro
        r = gbox(a)
        lay = QVBoxLayout(self); f = QFormLayout(); lay.addLayout(f)

        def spin(v, lo=-2000.0):
            s = QDoubleSpinBox(); s.setRange(lo, 5000); s.setDecimals(1); s.setSuffix(" mm"); s.setValue(v / k)
            return s
        self.x, self.y = spin(r.x()), spin(r.y())
        self.w, self.h = spin(r.width(), 0.1), spin(r.height(), 0.1)
        self._orig = [(s, s.value(), px) for s, px in
                      ((self.x, r.x()), (self.y, r.y()), (self.w, r.width()), (self.h, r.height()))]
        self.rot = QSpinBox(); self.rot.setRange(0, 359); self.rot.setSuffix("°"); self.rot.setWrapping(True)
        self.rot.setValue(round(a.rotation) % 360)
        f.addRow(T("Horizontal (X):"), self.x); f.addRow(T("Vertical (Y):"), self.y)
        f.addRow(T("Ancho:"), self.w); f.addRow(T("Alto:"), self.h); f.addRow(T("Giro:"), self.rot)
        if a.kind in NO_SIZE:
            self.w.setEnabled(False); self.h.setEnabled(False)
        lay.addWidget(QLabel(T("Medidas sin contar el giro, desde la esquina superior izquierda de la página.")))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); lay.addWidget(bb)

    def box(self) -> QRectF:
        """Caja nueva en píxeles; lo que no se cambió conserva su valor exacto (sin el redondeo a 0,1 mm)."""
        vals = [s.value() * self.k if s.value() != v0 else px for s, v0, px in self._orig]
        return QRectF(*vals)


class ArrangeMixin:
    def _targets(self):
        return self._sel_multi if self._sel_multi else ([self._sel] if self._sel else [])

    def _pick(self, a):
        """Selecciona `a`; si pertenece a un grupo, todo el grupo."""
        self._setsel(a)
        if a.group:
            self._sel_multi = [b for b in self.anns if b.group == a.group and not b.hidden]
            for b in self._sel_multi: b.selected = True

    def _change(self, fn):
        """Aplica `fn()` como un solo paso de deshacer."""
        self._snap(); fn(); self._redraw(); self._commit()

    # ── menú «Organizar» (menú contextual de uno o varios objetos) ──
    def _arrange_menu(self, menu, targets):
        n = len(targets)
        acts = {}
        am = menu.addMenu(get_icon("align"), T("Alinear y distribuir") if n > 1 else T("Alinear en la página"))
        for i, (key, txt) in enumerate(ALIGN.items()):
            if i == 3: am.addSeparator()
            acts[am.addAction(T(txt))] = lambda key=key: self._align(key)
        if n > 2:
            am.addSeparator()
            acts[am.addAction(T("Distribuir horizontalmente"))] = lambda: self._distribute(True)
            acts[am.addAction(T("Distribuir verticalmente"))] = lambda: self._distribute(False)
        fm = menu.addMenu(get_icon("flip"), T("Voltear"))
        acts[fm.addAction(T("Horizontalmente"))] = lambda: self._flip(True)
        acts[fm.addAction(T("Verticalmente"))] = lambda: self._flip(False)
        if n == 1:
            acts[menu.addAction(get_icon("ruler"), T("Posición y tamaño…"))] = lambda: self._geometry_dlg(targets[0])
        menu.addSeparator()
        if n > 1 and not (targets[0].group and all(a.group == targets[0].group for a in targets)):
            acts[menu.addAction(get_icon("group"), T("Agrupar"))] = self._group
        if any(a.group for a in targets):
            acts[menu.addAction(get_icon("ungroup"), T("Desagrupar"))] = self._ungroup
        acts[menu.addAction(get_icon("lock"), T("Bloquear"))] = lambda: self._set_flag("locked")
        acts[menu.addAction(get_icon("hide"), T("Ocultar"))] = lambda: self._set_flag("hidden")
        menu.addSeparator()
        if n == 1:
            acts[menu.addAction(get_icon("brush"), T("Copiar formato"))] = lambda: self._copy_fmt(targets[0])
        ap = menu.addAction(get_icon("brush"), T("Pegar formato"))
        ap.setEnabled(bool(type(self).fmt_clip))
        acts[ap] = self._paste_fmt
        return acts

    def _restore_menu(self, menu):
        """Menú sobre una zona vacía: recuperar los objetos bloqueados u ocultos."""
        acts = {}
        if any(a.locked for a in self.anns):
            acts[menu.addAction(get_icon("unlock"), T("Desbloquear todo"))] = lambda: self._clear_flag("locked")
        if any(a.hidden for a in self.anns):
            acts[menu.addAction(get_icon("show"), T("Mostrar objetos ocultos"))] = lambda: self._clear_flag("hidden")
        return acts

    # ── acciones ──
    def _align(self, how):
        t = self._targets()
        if not t: return
        ref = union(t) if len(t) > 1 else QRectF(0, 0, self._bw, self._bh)

        def fn():
            for a in t:
                r = vbox(a)
                dx = {"left": ref.left() - r.left(), "right": ref.right() - r.right(),
                      "hcenter": ref.center().x() - r.center().x()}.get(how, 0)
                dy = {"top": ref.top() - r.top(), "bottom": ref.bottom() - r.bottom(),
                      "vcenter": ref.center().y() - r.center().y()}.get(how, 0)
                a.move(dx, dy)
        self._change(fn)

    def _distribute(self, horizontal):
        """Mismo espacio entre objetos; el primero y el último no se mueven."""
        t = self._targets()
        if len(t) < 3: return
        pos = (lambda r: r.center().x()) if horizontal else (lambda r: r.center().y())
        t = sorted(t, key=lambda a: pos(vbox(a)))
        size = (lambda r: r.width()) if horizontal else (lambda r: r.height())
        start = (lambda r: r.left()) if horizontal else (lambda r: r.top())
        first, last = vbox(t[0]), vbox(t[-1])
        span = start(last) + size(last) - start(first)
        gap = (span - sum(size(vbox(a)) for a in t)) / (len(t) - 1)

        def fn():
            cur = start(first) + size(first) + gap
            for a in t[1:-1]:
                r = vbox(a)
                d = cur - start(r)
                a.move(d, 0) if horizontal else a.move(0, d)
                cur += size(r) + gap
        self._change(fn)

    def _flip(self, horizontal):
        t = self._targets()
        if not t: return
        c = union(t).center()

        def fn():
            for a in t:
                r = vbox(a).center()                       # varios objetos: también se refleja su posición
                a.move(2 * (c.x() - r.x()), 0) if horizontal else a.move(0, 2 * (c.y() - r.y()))
                mirror(a, horizontal)
        self._change(fn)

    def _geometry_dlg(self, a):
        k = self._bw / self._prect.width * 72 / 25.4
        dlg = GeometryDialog(a, k, self.window())
        if dlg.exec() != QDialog.DialogCode.Accepted: return

        def fn():
            set_box(a, dlg.box())
            a.rotation = float(dlg.rot.value())
        self._change(fn)

    def _group(self):
        t = self._targets()
        if len(t) < 2: return
        gid = uuid.uuid4().hex[:8]

        def fn():
            for a in t: a.group = gid
        self._change(fn)
        self._status(Tf("{0} objetos agrupados: se seleccionan y se mueven juntos.", len(t)))

    def _ungroup(self):
        t = self._targets()

        def fn():
            for a in t: a.group = ""
        self._change(fn)

    def _set_flag(self, name):
        t = self._targets()
        if not t: return

        def fn():
            for a in t: setattr(a, name, True)
        self._change(fn)
        self._desel(); self._redraw()
        self._status(T("Bloqueado. Para desbloquearlo: clic derecho en una zona vacía → Desbloquear todo.") if name == "locked"
                     else T("Oculto. Para verlo de nuevo: clic derecho en una zona vacía → Mostrar objetos ocultos."))

    def _clear_flag(self, name):
        def fn():
            for a in self.anns: setattr(a, name, False)
        self._change(fn)

    def _copy_fmt(self, a):
        type(self).fmt_clip = {k: getattr(a, k) for k in STYLE_KEYS}
        self._status(T("Formato copiado. Selecciona otros objetos y usa «Pegar formato»."))

    def _paste_fmt(self):
        t, fmt = self._targets(), type(self).fmt_clip
        if not (t and fmt): return

        def fn():
            for a in t:
                for k, v in fmt.items(): setattr(a, k, v)
        self._change(fn)

    def _status(self, msg):
        w = self.window()
        if hasattr(w, "_status"): w._status(msg)
