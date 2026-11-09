# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Selector de color propio — reemplaza QColorDialog.

QColorDialog es en parte una ventana nativa/semi-nativa cuyo interior (vista previa,
botón "Agregar a colores personalizados", OK/Cancel) no respeta de forma confiable
el stylesheet de la aplicación en este entorno (PyQt6 + Fusion + Windows): los botones
quedan "huecos" (solo el borde, sin relleno ni texto). Este diálogo está hecho con
widgets simples, 100% estilizados a mano, así que su apariencia es predecible.
"""
from core.i18n import T, Tf
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                             QLineEdit, QPushButton, QSlider, QFrame)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, QSize
from ui.styles import C
from ui.icons import get_icon
from utils.eyedropper import Eyedropper

# Paleta de colores preestablecidos (igual de práctica que "Basic colors" de QColorDialog)
_PRESETS = [
    "#000000", "#424242", "#6b7280", "#9ca3af", "#dfe3e8", "#ffffff",
    "#d13438", "#e8a33d", "#f7d354", "#1e8e3e", "#34c759", "#0ea5e9",
    "#1565d8", "#0f52b5", "#6d28d9", "#a855f7", "#ec4899", "#f472b6",
    "#7c2d12", "#92400e", "#365314", "#134e4a", "#1e3a5f", "#111827",
]


class ColorPickerDialog(QDialog):
    def __init__(self, parent=None, initial: QColor = None, allow_alpha: bool = False, title: str = "Color"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(300)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._allow_alpha = allow_alpha
        self._color = QColor(initial) if initial else QColor("#1565d8")
        if not allow_alpha:
            self._color.setAlpha(255)

        # Estilo propio, inline, sin depender de la cascada global.
        self.setStyleSheet(f"""
            QDialog {{ background-color:{C['dialog_bg']}; }}
            QLabel {{ color:{C['dialog_text']}; background:transparent; }}
            QLineEdit {{ background-color:{C['white']}; color:{C['text']}; border:1px solid {C['border']}; border-radius:4px; padding:5px 8px; }}
            QLineEdit:focus {{ border-color:{C['accent']}; }}
        """)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 12, 14, 12)

        # Vista previa + HEX + cuentagotas
        row = QHBoxLayout(); row.setSpacing(8)
        self.preview = QFrame()
        self.preview.setFixedSize(40, 40)
        row.addWidget(self.preview)
        self.hex_in = QLineEdit()
        self.hex_in.textChanged.connect(self._on_hex_changed)
        row.addWidget(self.hex_in, 1)
        eye_btn = QPushButton()
        eye_btn.setIcon(get_icon("eyedropper"))
        eye_btn.setIconSize(QSize(14, 14))
        eye_btn.setFixedSize(32, 32)
        eye_btn.setStyleSheet(
            f"QPushButton{{background-color:transparent;border:1px solid {C['border']};border-radius:4px;}}"
            f"QPushButton:hover{{background-color:{C['hover']};}}"
        )
        eye_btn.clicked.connect(self._eyedrop)
        row.addWidget(eye_btn)
        root.addLayout(row)

        # Cuadrícula de colores preestablecidos
        grid = QGridLayout(); grid.setSpacing(4)
        for i, hexval in enumerate(_PRESETS):
            b = QPushButton()
            b.setFixedSize(28, 28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{background-color:{hexval};border:1px solid {C['border']};border-radius:4px;}}"
                f"QPushButton:hover{{border:2px solid {C['accent']};}}"
            )
            b.clicked.connect(lambda _, h=hexval: self._set_color(QColor(h)))
            grid.addWidget(b, i // 6, i % 6)
        root.addLayout(grid)

        if allow_alpha:
            arow = QHBoxLayout(); arow.setSpacing(8)
            arow.addWidget(QLabel(T("Opacidad:")))
            self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
            self.alpha_slider.setRange(0, 255)
            self.alpha_slider.setValue(self._color.alpha())
            self.alpha_slider.valueChanged.connect(self._on_alpha_changed)
            arow.addWidget(self.alpha_slider, 1)
            self.alpha_lbl = QLabel(f"{self._color.alpha()}")
            self.alpha_lbl.setFixedWidth(30)
            arow.addWidget(self.alpha_lbl)
            root.addLayout(arow)
        else:
            self.alpha_slider = None

        # Botones — estilo inline explícito, garantizado (no depende de :checked/cascada)
        btns = QHBoxLayout(); btns.setSpacing(8); btns.addStretch()
        cancel_btn = QPushButton(T("Cancelar"))
        cancel_btn.setStyleSheet(
            f"QPushButton{{background-color:transparent;border:1px solid {C['border']};border-radius:4px;"
            f"color:{C['muted']};padding:6px 16px;min-width:70px;}}"
            f"QPushButton:hover{{background-color:{C['hover']};color:{C['text']};}}"
        )
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton(T("Aceptar"))
        ok_btn.setStyleSheet(
            f"QPushButton{{background-color:{C['accent']};border:1px solid {C['accent']};border-radius:4px;"
            f"color:white;font-weight:600;padding:6px 16px;min-width:70px;}}"
            f"QPushButton:hover{{background-color:{C['accent2']};border-color:{C['accent2']};}}"
        )
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        root.addLayout(btns)

        self._set_color(self._color)

    def _set_color(self, c: QColor):
        c = QColor(c)
        if not self._allow_alpha:
            c.setAlpha(255)
        self._color = c
        r, g, b, a = c.red(), c.green(), c.blue(), c.alpha()
        self.preview.setStyleSheet(
            f"background-color:rgba({r},{g},{b},{a});border:1px solid {C['border']};border-radius:4px;"
        )
        self.hex_in.blockSignals(True)
        self.hex_in.setText(c.name())
        self.hex_in.blockSignals(False)
        if self.alpha_slider is not None:
            self.alpha_slider.blockSignals(True)
            self.alpha_slider.setValue(a)
            self.alpha_slider.blockSignals(False)
            self.alpha_lbl.setText(str(a))

    def _on_hex_changed(self, text: str):
        c = QColor(text)
        if c.isValid():
            c.setAlpha(self._color.alpha())
            self._color = c
            r, g, b, a = c.red(), c.green(), c.blue(), c.alpha()
            self.preview.setStyleSheet(
                f"background-color:rgba({r},{g},{b},{a});border:1px solid {C['border']};border-radius:4px;"
            )

    def _on_alpha_changed(self, val: int):
        self._color.setAlpha(val)
        self.alpha_lbl.setText(str(val))
        r, g, b = self._color.red(), self._color.green(), self._color.blue()
        self.preview.setStyleSheet(
            f"background-color:rgba({r},{g},{b},{val});border:1px solid {C['border']};border-radius:4px;"
        )

    def _eyedrop(self):
        ov = Eyedropper()
        ov.picked.connect(self._set_color)
        ov.show()

    def result_color(self) -> QColor:
        return self._color


def pick_color(parent, initial: QColor = None, allow_alpha: bool = False, title: str = "Color"):
    """Muestra el selector y devuelve el QColor elegido, o None si se canceló."""
    dlg = ColorPickerDialog(parent, initial, allow_alpha, title)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.result_color()
    return None
