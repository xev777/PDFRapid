# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Barra de herramientas de anotación: horizontal, solo iconos, agrupada por tareas
(como Acrobat/Foxit). Las formas comparten un botón con menú desplegable."""
from core.i18n import T, Tf
from PyQt6.QtWidgets import QToolBar, QToolButton, QMenu, QDoubleSpinBox, QSpinBox
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtCore import pyqtSignal, QSize
from ui.styles import C, MENU_SS
from ui.icons import get_icon, get_toggle_icon
from core.constants import (T_ARROW, T_ARROW_SHAPE, T_CIRCLE, T_COMMENT, T_DARROW, T_HAND, T_HL, T_IMAGE, T_INK, T_LASSO, T_LINE, T_MEASURE, T_OCR_REGION, T_QRLENS, T_RECT, T_REDACT, T_RRECT, T_SELECT, T_SIGN, T_STAMP, T_TEXT, T_TEXTBOX, T_TRI, T_TXTSEL, T_FILL)


class ToolsBar(QToolBar):
    tool_changed = pyqtSignal(str)
    format_changed = pyqtSignal(dict)       # {stroke, fill, width, opacity}: estilo elegido en la barra
    stamp_chosen = pyqtSignal(str, str)      # texto, color
    fill_chosen = pyqtSignal(str)            # símbolo de Rellenar y firmar
    measure_chosen = pyqtSignal(str)         # dist | perim | area | scale
    # Grupos separados por líneas: (id, icono, nombre, atajo)
    GROUPS = [
        [(T_SELECT, "select", "Seleccionar", "V"),
         (T_LASSO, "lasso", "Lazo (selección múltiple)", "L"),
         (T_TXTSEL, "txtsel", "Seleccionar texto", "S"),
         (T_HAND, "hand", "Mano: arrastrar para desplazarse", "N"),
         (T_MEASURE, "ruler", "Medir distancia, perímetro o área", "Q")],
        [(T_TEXT, "text", "Texto", "T"),
         (T_TEXTBOX, "textbox", "Caja de texto", "X"),
         (T_COMMENT, "comment", "Comentario", "M"),
         (T_HL, "highlight", "Resaltar área", "H")],
        [(T_LINE, "line", "Línea", "I"),
         (T_ARROW, "arrow", "Flecha", "A"),
         (T_DARROW, "darrow", "Doble flecha", "D"),
         (T_INK, "pencil", "Lápiz (dibujo a mano)", "B")],
        None,   # botón de formas
        "STAMPS",
        "FILL",
        [(T_REDACT, "redact", "Marcar zona para tachado definitivo", "E")],
        [(T_SIGN, "signature", "Firmar (dibujar, escribir o imagen)", "K"),
         (T_IMAGE, "image", "Insertar imagen", "P"),
         (T_OCR_REGION, "ocr_region", "OCR de una región", "O")],
    ]
    SHAPES = [(T_RECT, "rect", "Rectángulo", "R"),
              (T_RRECT, "rrect", "Rectángulo redondeado", "U"),
              (T_CIRCLE, "circle", "Círculo", "C"),
              (T_TRI, "triangle", "Triángulo", "G"),
              (T_ARROW_SHAPE, "arrow_shape", "Figura flecha", "F")]
    KEYS = {"v": T_SELECT, "l": T_LASSO, "t": T_TEXT, "x": T_TEXTBOX, "s": T_TXTSEL,
            "m": T_COMMENT, "h": T_HL, "i": T_LINE, "a": T_ARROW, "d": T_DARROW,
            "r": T_RECT, "u": T_RRECT, "c": T_CIRCLE, "g": T_TRI, "f": T_ARROW_SHAPE,
            "p": T_IMAGE, "o": T_OCR_REGION, "b": T_INK, "k": T_SIGN, "n": T_HAND, "e": T_REDACT, "q": T_MEASURE, "w": T_QRLENS, "j": T_FILL}   # la Lupa QR tiene su botón en la barra superior

    # Estilo por widget: en PyQt6/Fusion/Windows, QToolButton:checked en QSS a veces no
    # pinta el relleno y el botón queda "hueco".
    _OFF = (f"QToolButton{{background:transparent;border:1px solid transparent;border-radius:4px;padding:3px;}}"
            f"QToolButton:hover{{background:{C['hover']};border-color:{C['border']};}}")
    _ON = f"QToolButton{{background:{C['accent']};border:1px solid {C['accent']};border-radius:4px;padding:3px;}}"

    def __init__(self, parent=None):
        super().__init__("Herramientas", parent)
        self.setMovable(False)
        self.setIconSize(QSize(20, 20))
        self._btns = {}
        self._shape_ids = {s[0]: s for s in self.SHAPES}
        for gi, group in enumerate(self.GROUPS):
            if gi: self.addSeparator()
            if group is None:
                self._add_shapes()
                continue
            if group == "STAMPS":
                self._add_stamps()
                continue
            if group == "FILL":
                self._add_fill()
                continue
            for tid, icon, label, key in group:
                b = QToolButton()
                b.setIcon(get_toggle_icon(icon))
                b.setToolTip(f"{T(label)}  ({key})")
                b.setCheckable(True)
                b.setStyleSheet(self._OFF)
                b.clicked.connect(lambda _, t=tid: self.activate(t))
                self.addWidget(b)
                self._btns[tid] = b
        self._measure_menu()
        for k, t in self.KEYS.items():      # atajos de una letra (antes eran acciones de la barra: botones vacíos)
            QShortcut(QKeySequence(k.upper()), self, lambda tt=t: self.activate(tt))
        self.activate(T_SELECT)
        self._add_format()

    def _add_format(self):
        """Formato (como en Office): define el estilo de lo próximo que se dibuje o cambia el del objeto seleccionado."""
        from utils.eyedropper import CPBtn
        self.addSeparator()
        self.c_stroke = CPBtn(QColor(C['accent']), label="Color del trazo"); self.c_stroke.setFixedSize(30, 24)
        self.c_fill = CPBtn(QColor(255, 255, 255, 0), True, label="Relleno (transparente = sin relleno)"); self.c_fill.setFixedSize(30, 24)
        b_nofill = QToolButton(); b_nofill.setText("∅"); b_nofill.setToolTip(T("Sin relleno")); b_nofill.setStyleSheet(self._OFF)
        b_nofill.clicked.connect(lambda: self.c_fill.set(QColor(255, 255, 255, 0)))
        self.sp_width = QDoubleSpinBox(); self.sp_width.setRange(0.5, 20); self.sp_width.setSingleStep(0.5)
        self.sp_width.setValue(1.5); self.sp_width.setSuffix(" pt"); self.sp_width.setToolTip(T("Grosor del trazo")); self.sp_width.setFixedWidth(96)
        self.sp_op = QSpinBox(); self.sp_op.setRange(5, 100); self.sp_op.setValue(100); self.sp_op.setSuffix(" %")
        self.sp_op.setToolTip(T("Opacidad")); self.sp_op.setFixedWidth(84)
        for w in (self.c_stroke, self.c_fill, b_nofill, self.sp_width, self.sp_op): self.addWidget(w)
        self._loading = False
        for sig in (self.c_stroke.changed, self.c_fill.changed, self.sp_width.valueChanged, self.sp_op.valueChanged):
            sig.connect(self._emit_format)

    def _emit_format(self, *_):
        if self._loading: return
        f = self.c_fill.color
        self.format_changed.emit({"stroke": self.c_stroke.color, "fill": f if f.alpha() > 0 else None,
                                  "width": self.sp_width.value(), "opacity": self.sp_op.value() / 100})

    def show_format(self, ann):
        """Muestra el estilo del objeto seleccionado (sin aplicarlo de nuevo)."""
        if ann is None: return
        self._loading = True
        try:
            self.c_stroke.set(QColor(ann.stroke or C['accent']))
            self.c_fill.set(QColor(ann.fill) if ann.fill else QColor(255, 255, 255, 0))
            self.sp_width.setValue(ann.stroke_width); self.sp_op.setValue(round(ann.opacity * 100))
        finally:
            self._loading = False

    def _add_stamps(self):
        """Botón de sellos: elegir uno lo deja listo para colocarlo con un clic."""
        from ui.stamps import STAMPS
        b = QToolButton(); b.setCheckable(True); b.setIcon(get_toggle_icon("stamp"))
        b.setToolTip(T("Sellos (Aprobado, Revisado, Confidencial…)"))
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup); b.setStyleSheet(self._OFF)
        m = QMenu(b); m.setStyleSheet(MENU_SS)
        for text, color in STAMPS:
            m.addAction(get_icon("dot", color=color), T(text.capitalize())).triggered.connect(
                lambda _, t=text, c=color: self.stamp_chosen.emit(t, c))
        b.setMenu(m); self.addWidget(b); self._btns[T_STAMP] = b
        self.addSeparator()

    def _measure_menu(self):
        """Medir: clic = el último modo, flecha = distancia, perímetro, área o escala del plano."""
        from ui.canvas_measure import MODES
        b = self._btns[T_MEASURE]
        b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        m = QMenu(b); m.setStyleSheet(MENU_SS)
        icons = {"dist": "ruler", "perim": "perimeter", "area": "area"}
        for key, text in MODES.items():
            m.addAction(get_icon(icons[key]), T(text)).triggered.connect(lambda _=False, k=key: self.measure_chosen.emit(k))
        m.addSeparator()
        m.addAction(get_icon("scale"), T("Escala del plano…")).triggered.connect(lambda _=False: self.measure_chosen.emit("scale"))
        b.setMenu(m)

    def _add_fill(self):
        """Rellenar y firmar: clic = último símbolo usado, flecha = elegir otro (✓ ✗ ● línea, fecha, iniciales)."""
        from ui.canvas_fill import SYMBOLS
        b = QToolButton(); b.setCheckable(True); b.setIcon(get_toggle_icon("fill"))
        b.setToolTip(T("Rellenar y firmar: ✓, ✗, punto, línea, fecha e iniciales  (J)"))
        b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup); b.setStyleSheet(self._OFF)
        m = QMenu(b); m.setStyleSheet(MENU_SS)
        for key, (text, icon) in SYMBOLS.items():
            m.addAction(get_icon(icon), T(text)).triggered.connect(lambda _, k=key: self.fill_chosen.emit(k))
        b.setMenu(m); b.clicked.connect(lambda: self.activate(T_FILL))
        self.addWidget(b); self._btns[T_FILL] = b

    def _add_shapes(self):
        """Un botón para todas las formas: clic = última forma usada, flecha = elegir otra."""
        b = QToolButton()
        b.setCheckable(True)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        m = QMenu(b)
        m.setStyleSheet(MENU_SS)
        for tid, icon, label, key in self.SHAPES:
            m.addAction(get_icon(icon), f"{T(label)}  ({key})").triggered.connect(
                lambda _, t=tid: self.activate(t))
            self._btns[tid] = b
        b.setMenu(m)
        b.clicked.connect(lambda: self.activate(self._shape))
        self._shape_btn = b
        self._set_shape(T_RECT)
        self.addWidget(b)

    def _set_shape(self, tid):
        _, icon, label, key = self._shape_ids[tid]
        self._shape = tid
        self._shape_btn.setIcon(get_toggle_icon(icon))
        self._shape_btn.setToolTip(Tf("Formas: {0}  ({1})", T(label), key))

    def activate(self, tid: str):
        self.current = tid
        if tid in self._shape_ids:
            self._set_shape(tid)
        current = self._btns.get(tid)
        for b in set(self._btns.values()):
            on = b is current
            b.setChecked(on)
            b.setStyleSheet((self._ON if on else self._OFF) +
                            ("QToolButton{padding-right:14px;}" if b is self._shape_btn else ""))
        self.tool_changed.emit(tid)
