# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Diálogo para insertar/editar texto: área de texto, barra de formato (como Word) y vista previa."""
from core.i18n import T, Tf
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QGroupBox, QHBoxLayout, QLabel, QTextEdit, QFontComboBox,
                             QSpinBox, QPushButton, QDialogButtonBox, QDoubleSpinBox, QFrame)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt
from utils.eyedropper import CPBtn, _eye
from utils.helpers import wire_toggle_style
from ui.styles import DIALOG_SS, C


def _swatch_row(label, btn):
    """«Etiqueta [■] [cuentagotas]» en una fila compacta."""
    h = QHBoxLayout(); h.setSpacing(6)
    lbl = QLabel(label); lbl.setObjectName("muted"); h.addWidget(lbl)
    h.addWidget(btn); h.addWidget(_eye(btn.eyedrop))
    return h


class TextDialog(QDialog):
    def __init__(self, parent=None, text="", font_name="Arial", font_size=12,
                 color="#111111", box_bg="#ffffff", box_border="#000000", box_bw=0.0, box=False):
        super().__init__(parent)
        self.setWindowTitle(T("Editar texto") if text else T("Insertar texto"))
        self.setMinimumWidth(520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(DIALOG_SS)
        lay = QVBoxLayout(self); lay.setSpacing(12); lay.setContentsMargins(18, 16, 18, 16)

        self.ed = QTextEdit(); self.ed.setPlainText(text); self.ed.setMinimumHeight(110)
        from ui import spell_ui; spell_ui.attach(self.ed)
        self.ed.setPlaceholderText(T("Escribe el texto aquí…"))
        self.ed.setObjectName("content")
        lay.addWidget(self.ed)

        # barra de formato
        bar = QHBoxLayout(); bar.setSpacing(6)
        self.fn = QFontComboBox(); self.fn.setCurrentFont(QFont(font_name)); bar.addWidget(self.fn, 1)
        self.fs = QSpinBox(); self.fs.setRange(4, 288); self.fs.setValue(max(4, font_size)); self.fs.setSuffix(" pt")
        self.fs.setFixedWidth(92); bar.addWidget(self.fs)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine); sep.setObjectName("sep"); bar.addWidget(sep)
        self.fb, self.fi, self.fu = (self._toggle("N", T("Negrita"), bold=True), self._toggle("K", T("Cursiva"), italic=True),
                                     self._toggle("S", T("Subrayado"), underline=True))
        for b in (self.fb, self.fi, self.fu): bar.addWidget(b)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine); sep.setObjectName("sep"); bar.addWidget(sep)
        self.cc = CPBtn(QColor(color), label="Color del texto"); self.cc.changed.connect(self._preview)
        bar.addLayout(_swatch_row("", self.cc))
        lay.addLayout(bar)

        # caja (solo para «Caja de texto»)
        self.cbg = CPBtn(QColor(box_bg) if box_bg else QColor(255, 255, 255), True, label="Fondo de la caja")
        self.cbd = CPBtn(QColor(box_border), label="Borde de la caja")
        self.sbw = QDoubleSpinBox(); self.sbw.setRange(0, 10); self.sbw.setValue(box_bw); self.sbw.setSuffix(" pt")
        self.sbw.setSingleStep(0.5); self.sbw.setFixedWidth(100)
        if box:
            g = QGroupBox(T("CAJA")); gl = QHBoxLayout(g); gl.setSpacing(14)
            gl.addLayout(_swatch_row(T("Fondo"), self.cbg)); gl.addLayout(_swatch_row(T("Borde"), self.cbd))
            h = QHBoxLayout(); h.setSpacing(6); lbl = QLabel(T("Grosor")); lbl.setObjectName("muted")
            h.addWidget(lbl); h.addWidget(self.sbw); gl.addLayout(h); gl.addStretch()
            lay.addWidget(g)
            for sig in (self.cbg.changed, self.cbd.changed, self.sbw.valueChanged): sig.connect(self._preview)

        cap = QLabel(T("VISTA PREVIA")); cap.setObjectName("caption"); lay.addWidget(cap)
        self.prev = QLabel(); self.prev.setMinimumHeight(56); self.prev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prev.setWordWrap(True); lay.addWidget(self.prev)
        self._box = box
        for sig in (self.ed.textChanged, self.fn.currentFontChanged, self.fs.valueChanged,
                    self.fb.toggled, self.fi.toggled, self.fu.toggled):
            sig.connect(self._preview)
        self._preview()

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Aceptar") if text else T("Insertar"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(T("Cancelar"))
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); lay.addWidget(bb)
        self.ed.setFocus()

    def _toggle(self, txt, tip, bold=False, italic=False, underline=False):
        b = QPushButton(txt); b.setCheckable(True); b.setFixedSize(34, 32); b.setToolTip(tip)
        f = QFont(); f.setBold(bold); f.setItalic(italic); f.setUnderline(underline); f.setPointSize(10); b.setFont(f)
        wire_toggle_style(b,
                          f"QPushButton{{background:{C['white']};border:1px solid {C['border']};border-radius:6px;color:{C['text']};min-width:32px;max-width:32px;padding:0;}}"
                          f"QPushButton:hover{{border-color:{C['accent']};}}",
                          f"QPushButton{{background:{C['accent_soft']};border:1px solid {C['accent']};border-radius:6px;color:{C['accent']};min-width:32px;max-width:32px;padding:0;font-weight:700;}}")
        return b

    def _preview(self, *_):
        txt = self.ed.toPlainText().split('\n')[0][:80] or "Vista previa"
        fam, sz = self.fn.currentFont().family(), self.fs.value()
        tc = self.cc.color
        w = "bold" if self.fb.isChecked() else "normal"
        fs = "italic" if self.fi.isChecked() else "normal"
        d = "underline" if self.fu.isChecked() else "none"
        if self._box:
            bg, bd, bw = self.cbg.color, self.cbd.color, self.sbw.value()
            border = f"{max(1, round(bw))}px solid {bd.name()}" if bw > 0 else f"1px dashed {C['border']}"
            back = f"rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()})"
        else:
            border, back = f"1px solid {C['border']}", "#ffffff"
        self.prev.setStyleSheet(f"background:{back};border:{border};border-radius:8px;padding:8px;")
        self.prev.setText(f'<span style="font-family:\'{fam}\';font-size:{min(sz, 28)}pt;font-weight:{w};'
                          f'font-style:{fs};text-decoration:{d};color:{tc.name()};">{txt}</span>')

    @property
    def result_text(self): return self.ed.toPlainText()
    @property
    def result_font(self): return self.fn.currentFont().family()
    @property
    def result_size(self): return self.fs.value()
    @property
    def result_color(self): return self.cc.color.name()
    @property
    def result_bold(self): return self.fb.isChecked()
    @property
    def result_italic(self): return self.fi.isChecked()
    @property
    def result_under(self): return self.fu.isChecked()
    @property
    def result_bg(self): return self.cbg.color.name()
    @property
    def result_bd(self): return self.cbd.color.name()
    @property
    def result_bw(self): return self.sbw.value()
