# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Diálogo de propiedades de objetos"""
from core.i18n import T, Tf
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QTabWidget, QGroupBox, QGridLayout,
                             QLabel, QDoubleSpinBox, QComboBox, QSpinBox, QCheckBox,
                             QHBoxLayout, QFontComboBox, QPushButton, QDialogButtonBox)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt
from utils.eyedropper import CPBtn, _eye
from utils.helpers import wire_toggle_style
from ui.icons import get_icon
from ui.styles import DIALOG_SS

class PropsDialog(QDialog):
    KIND_NAMES = {
        "line": "Línea", "rect": "Rectángulo", "rrect": "Rect. redondeado",
        "circle": "Círculo/Elipse", "triangle": "Triángulo", "text": "Texto",
        "textbox": "Caja de texto", "highlight": "Resaltado", "comment": "Comentario",
        "arrow": "Flecha", "darrow": "Flecha doble", "arrow_shape": "Figura flecha", "image": "Imagen"
    }

    def __init__(self, ann, parent=None):
        super().__init__(parent)
        self._ann = ann
        kind_name = T(self.KIND_NAMES.get(ann.kind, ann.kind))
        self.setWindowTitle(Tf("Formato — {0}", kind_name))
        self.setMinimumWidth(500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(DIALOG_SS)
        
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 12, 14, 12)
        
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        
        self._build_appearance(ann)
        self._build_text(ann)
        if ann.kind == "textbox": self._build_box(ann)
        if ann.kind in ("arrow", "darrow", "line"): self._build_arrow(ann)
        
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Aplicar"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(T("Cancelar"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _build_appearance(self, ann):
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(8); lay.setContentsMargins(10,10,10,10)
        g = QGroupBox(T("COLORES")); gl = QGridLayout(g); gl.setSpacing(8)
        gl.addWidget(QLabel(T("Borde / línea:")), 0, 0)
        self.c_stroke = CPBtn(QColor(ann.stroke), label="Borde")
        gl.addWidget(self.c_stroke, 0, 1); gl.addWidget(_eye(self.c_stroke.eyedrop), 0, 2)
        gl.addWidget(QLabel(T("Relleno:")), 1, 0)
        self.c_fill = CPBtn(QColor(ann.fill) if ann.fill else QColor(255,255,255,0), True, label="Relleno")
        gl.addWidget(self.c_fill, 1, 1); gl.addWidget(_eye(self.c_fill.eyedrop), 1, 2)
        gl.addWidget(QLabel(T("Texto:")), 2, 0)
        self.c_text = CPBtn(QColor(ann.text_color), label="Texto")
        gl.addWidget(self.c_text, 2, 1); gl.addWidget(_eye(self.c_text.eyedrop), 2, 2)
        lay.addWidget(g)
        
        g2 = QGroupBox(T("BORDE Y VISIBILIDAD")); gl2 = QGridLayout(g2); gl2.setSpacing(8)
        gl2.addWidget(QLabel(T("Grosor:")), 0, 0)
        self.s_w = QDoubleSpinBox(); self.s_w.setRange(0.5, 20); self.s_w.setValue(ann.stroke_width); self.s_w.setSuffix(" pt"); gl2.addWidget(self.s_w, 0, 1)
        gl2.addWidget(QLabel(T("Estilo borde:")), 1, 0)
        self.s_style = QComboBox(); self.s_style.addItems([T("Sólido"), T("Discontinuo"), T("Punteado")])
        style_map = {"solid":0, "dashed":1, "dotted":2}
        self.s_style.setCurrentIndex(style_map.get(ann.stroke_style, 0)); gl2.addWidget(self.s_style, 1, 1)
        gl2.addWidget(QLabel(T("Opacidad:")), 2, 0)
        self.s_op = QSpinBox(); self.s_op.setRange(10, 100); self.s_op.setValue(max(10, min(100, int(ann.opacity*100)))); self.s_op.setSuffix(" %"); gl2.addWidget(self.s_op, 2, 1)
        if ann.kind == "rrect":
            gl2.addWidget(QLabel(T("Radio esquinas:")), 3, 0)
            self.s_cr = QDoubleSpinBox(); self.s_cr.setRange(0, 50); self.s_cr.setValue(ann.corner_r); self.s_cr.setSuffix(" pt"); gl2.addWidget(self.s_cr, 3, 1)
        lay.addWidget(g2); lay.addStretch()
        self.tabs.addTab(w, get_icon("format"), T("Apariencia"))

    def _build_text(self, ann):
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(8); lay.setContentsMargins(10,10,10,10)
        g = QGroupBox(T("FUENTE")); gf = QGridLayout(g); gf.setSpacing(8)
        gf.addWidget(QLabel(T("Fuente:")), 0, 0)
        self.f_name = QFontComboBox(); self.f_name.setCurrentFont(QFont(ann.font_name)); gf.addWidget(self.f_name, 0, 1, 1, 3)
        gf.addWidget(QLabel(T("Tamaño:")), 1, 0)
        self.f_size = QSpinBox(); self.f_size.setRange(4, 288); self.f_size.setValue(max(4, ann.font_size)); self.f_size.setSuffix(" pt"); gf.addWidget(self.f_size, 1, 1)
        gf.addWidget(QLabel(T("Estilo:")), 2, 0)
        sr = QHBoxLayout()
        self.f_bold = QPushButton("N"); self.f_bold.setCheckable(True); self.f_bold.setChecked(ann.font_bold); self.f_bold.setFixedSize(32, 28); self.f_bold.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.f_ital = QPushButton("I"); self.f_ital.setCheckable(True); self.f_ital.setChecked(ann.font_italic); self.f_ital.setFixedSize(32, 28); self.f_ital.setFont(QFont("Arial", 10, QFont.Weight.Normal, True))
        self.f_under = QPushButton("S"); self.f_under.setCheckable(True); self.f_under.setChecked(ann.font_underline); self.f_under.setFixedSize(32, 28)
        for b in [self.f_bold, self.f_ital, self.f_under]: wire_toggle_style(b); sr.addWidget(b)
        sr.addStretch(); gf.addLayout(sr, 2, 1, 1, 3); lay.addWidget(g)
        g2 = QGroupBox(T("ALINEACIÓN")); ga = QHBoxLayout(g2)
        self.a_l = QPushButton(T("Izq")); self.a_c = QPushButton(T("Cen")); self.a_r = QPushButton(T("Der"))
        for b in [self.a_l, self.a_c, self.a_r]: b.setCheckable(True); b.clicked.connect(self._xalign); wire_toggle_style(b); ga.addWidget(b)
        {"left":self.a_l, "center":self.a_c, "right":self.a_r}.get(ann.text_align, self.a_l).setChecked(True)
        lay.addWidget(g2); lay.addStretch()
        self.tabs.addTab(w, get_icon("text"), T("Texto"))

    def _build_box(self, ann):
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(8); lay.setContentsMargins(10,10,10,10)
        g = QGroupBox(T("CAJA DE TEXTO")); gb = QGridLayout(g); gb.setSpacing(8)
        gb.addWidget(QLabel(T("Fondo:")), 0, 0)
        self.b_bg = CPBtn(QColor(ann.box_bg) if ann.box_bg else QColor(255,255,255,0), True, label="Fondo")
        gb.addWidget(self.b_bg, 0, 1); gb.addWidget(_eye(self.b_bg.eyedrop), 0, 2)
        gb.addWidget(QLabel(T("Borde:")), 1, 0)
        self.b_bd = CPBtn(QColor(ann.box_border), label="Borde caja")
        gb.addWidget(self.b_bd, 1, 1); gb.addWidget(_eye(self.b_bd.eyedrop), 1, 2)
        gb.addWidget(QLabel(T("Grosor:")), 2, 0)
        self.b_bw = QDoubleSpinBox(); self.b_bw.setRange(0, 10); self.b_bw.setValue(ann.box_bw); self.b_bw.setSuffix(" pt"); gb.addWidget(self.b_bw, 2, 1)
        lay.addWidget(g); lay.addStretch()
        self.tabs.addTab(w, get_icon("textbox"), T("Caja"))

    def _build_arrow(self, ann):
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(8); lay.setContentsMargins(10,10,10,10)
        g = QGroupBox(T("FLECHAS")); gv = QGridLayout(g); gv.setSpacing(8)
        gv.addWidget(QLabel(T("Flecha inicio:")), 0, 0)
        self.ar_start = QCheckBox(T("Mostrar")); self.ar_start.setChecked(ann.arrow_start); gv.addWidget(self.ar_start, 0, 1)
        gv.addWidget(QLabel(T("Flecha fin:")), 1, 0)
        self.ar_end = QCheckBox(T("Mostrar")); self.ar_end.setChecked(ann.arrow_end); gv.addWidget(self.ar_end, 1, 1)
        gv.addWidget(QLabel(T("Tamaño punta:")), 2, 0)
        self.ar_sz = QDoubleSpinBox(); self.ar_sz.setRange(4, 40); self.ar_sz.setValue(ann.arrow_size); self.ar_sz.setSuffix(" pt"); gv.addWidget(self.ar_sz, 2, 1)
        lay.addWidget(g); lay.addStretch()
        self.tabs.addTab(w, get_icon("arrow"), T("Flecha"))

    def _xalign(self):
        s = self.sender()
        for b in [self.a_l, self.a_c, self.a_r]:
            if b is not s: b.blockSignals(True); b.setChecked(False); b.blockSignals(False)

    def apply(self, ann):
        ann.stroke = self.c_stroke.color.name()
        fc = self.c_fill.color; ann.fill = fc.name() if fc.alpha() > 0 else None
        ann.text_color = self.c_text.color.name()
        ann.stroke_width = self.s_w.value()
        ann.stroke_style = ["solid", "dashed", "dotted"][self.s_style.currentIndex()]
        ann.opacity = self.s_op.value() / 100.0
        if hasattr(self, 's_cr'): ann.corner_r = self.s_cr.value()
        ann.font_name = self.f_name.currentFont().family()
        ann.font_size = self.f_size.value()
        ann.font_bold = self.f_bold.isChecked(); ann.font_italic = self.f_ital.isChecked(); ann.font_underline = self.f_under.isChecked()
        for b, a2 in [(self.a_l, "left"), (self.a_c, "center"), (self.a_r, "right")]:
            if b.isChecked(): ann.text_align = a2; break
        if ann.kind == "textbox" and hasattr(self, 'b_bg'):
            bg = self.b_bg.color; ann.box_bg = bg.name() if bg.alpha() > 0 else None
            ann.box_border = self.b_bd.color.name(); ann.box_bw = self.b_bw.value()
        if hasattr(self, 'ar_start'):
            ann.arrow_start = self.ar_start.isChecked(); ann.arrow_end = self.ar_end.isChecked(); ann.arrow_size = self.ar_sz.value()