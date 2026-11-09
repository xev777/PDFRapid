# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Texto: selección y copia, edición en línea, diálogos de texto, texto original del PDF y comentarios. Parte de PageCanvas (ui/canvas.py)."""
from core.i18n import T, Tf
from datetime import datetime
import pymupdf
from PyQt6.QtWidgets import (QLabel, QTextEdit, QDialog, QVBoxLayout,
                             QApplication, QMenu, QDialogButtonBox,
                             QMessageBox)
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor
from models.annotation import Ann
from dialogs.text_dialog import TextDialog
from dialogs.color_picker import pick_color

from core.logger import log
from core.settings import AppSettings
from ui.styles import C, MENU_SS, DIALOG_SS
from ui.icons import get_icon


class TextMixin:
    def _copy_text(self):
        """Copia el texto seleccionado si el documento lo permite."""
        if not self.doc.permissions & pymupdf.PDF_PERM_COPY:
            QMessageBox.information(self, T("Documento protegido"),
                                    T("El autor de este documento no permite copiar su texto."))
            return
        QApplication.clipboard().setText(self._tsel_text)

    def _open_inline(self, a):
        self._close_inline()
        r = a.brect()
        ed = QTextEdit(self)
        ed.setObjectName("inline")
        ed.setPlainText(a.text)
        ed.setGeometry(int(r.x()-2), int(r.y()-2), max(int(r.width()+4), 200), max(int(r.height()+4), 50))
        ed.setFont(a.qfont())
        ed.setStyleSheet("background:#ffffff;color:#111111;border:2px solid "+C['accent']+";border-radius:3px;padding:3px;")
        from ui import spell_ui; spell_ui.attach(ed)
        ed.show()
        ed.setFocus()
        ed.selectAll()
        self._inline = ed
        self._inline_ann = a
        orig = ed.focusOutEvent
        def _c(ev2):
            if ev2.reason() == Qt.FocusReason.PopupFocusReason: orig(ev2); return    # menú de ortografía: sigue editando
            self._commit_inline(); orig(ev2)
        ed.focusOutEvent = _c

    def _commit_inline(self):
        if self._inline and self._inline_ann:
            try:
                self._snap()
                self._inline_ann.text = self._inline.toPlainText()
                self._redraw()
                self._commit()
            except Exception:
                log.exception("commit_inline")
        self._close_inline()

    def _close_inline(self):
        if self._inline:
            try: self._inline.setParent(None); self._inline.deleteLater()
            except RuntimeError: pass  # widget ya destruido por Qt
            self._inline = None

    def _text_dlg(self, pt, ea=None):
        dlg = TextDialog(self, ea.text if ea else "", ea.font_name if ea else self.p_fname,
                         ea.font_size if ea else self.p_fsize, ea.text_color if ea else self.p_fcolor.name(),
                         ea.box_bg or "#ffffff" if ea else "#ffffff", ea.box_border if ea else "#000000",
                         ea.box_bw if ea else 0.0, box=bool(ea and ea.kind == "textbox"))
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        if not dlg.result_text.strip(): return
        self._snap()
        if ea:
            ea.text = dlg.result_text
            ea.font_name = dlg.result_font
            ea.font_size = dlg.result_size
            ea.text_color = dlg.result_color
            ea.font_bold = dlg.result_bold
            ea.font_italic = dlg.result_italic
            ea.font_underline = dlg.result_under
            ea.box_bg = dlg.result_bg
            ea.box_border = dlg.result_bd
            ea.box_bw = dlg.result_bw
            self._redraw()
            self._commit()
        else:
            a = Ann("text", x1=pt.x(), y1=pt.y(), x2=pt.x()+300, y2=pt.y()+30,
                    text=dlg.result_text, font_name=dlg.result_font, font_size=dlg.result_size,
                    text_color=dlg.result_color, font_bold=dlg.result_bold,
                    font_italic=dlg.result_italic, font_underline=dlg.result_under,
                    stroke=self.p_stroke.name(), opacity=self.p_opacity)
            self.anns.append(a)
            self._setsel(a)
            self._redraw()
            self._commit()

    def _edit_native(self, sp):
        if not self.doc.permissions & pymupdf.PDF_PERM_MODIFY:
            QMessageBox.information(self, T("Documento protegido"),
                                    T("El autor de este documento no permite modificar su contenido."))
            return
        ci = sp.get("color", 0)
        hex_c = QColor((ci >> 16) & 0xFF, (ci >> 8) & 0xFF, ci & 0xFF).name()
        dlg = TextDialog(self, sp["text"], sp["font"], int(sp["size"]), hex_c)
        dlg.setWindowTitle(T("Editar texto del documento"))
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        self.sig_before_doc_edit.emit(self.page_num)
        pg = self.doc[self.page_num]
        bb = sp["bbox"]
        ori = sp["origin"]
        pg.add_redact_annot(pymupdf.Rect(bb[0]-1, bb[1]-1, bb[2]+1, bb[3]+1), fill=(1,1,1))
        pg.apply_redactions()
        nc = QColor(dlg.result_color)
        fn = dlg.result_font.lower()
        ff = "tiro" if ("times" in fn or "serif" in fn) else "cour" if ("courier" in fn or "mono" in fn) else "helv"
        pg.insert_text(pymupdf.Point(ori[0], ori[1]), dlg.result_text, fontname=ff,
                       fontsize=dlg.result_size, color=(nc.redF(), nc.greenF(), nc.blueF()), overlay=True)
        self._render()
        self._load_text()
        self._redraw()
        self.sig_changed.emit(self.page_num)

    def _add_comment(self, pt):
        dlg = QDialog(self)
        dlg.setStyleSheet(DIALOG_SS)
        dlg.setWindowTitle(T("Agregar comentario"))
        dlg.setMinimumWidth(380)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(QLabel(T("Comentario:")))
        ed = QTextEdit()
        ed.setMaximumHeight(100)
        ed.setStyleSheet("background:#ffffff;color:#111111;border:1px solid #aaa;border-radius:4px;padding:4px;")
        from ui import spell_ui; spell_ui.attach(ed)
        lay.addWidget(ed)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Agregar"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(T("Cancelar"))
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        txt = ed.toPlainText().strip()
        if not txt: return
        self._snap()
        author = AppSettings().get_author()
        date = datetime.now().strftime("%d/%m/%Y %H:%M")
        a = Ann("comment", x1=pt.x(), y1=pt.y(), x2=pt.x()+28, y2=pt.y()+28,
                text=txt, author=author, date=date, stroke="#FFE066", comment_visible=True)
        self.anns.append(a)
        self._setsel(a)
        self._redraw()
        self._commit()

    def _edit_comment(self, a):
        """Editar el comentario, ver y añadir respuestas (hilo) y cambiar su estado de revisión."""
        from PyQt6.QtWidgets import QComboBox, QHBoxLayout
        from models.annotation import REVIEW_STATES
        dlg = QDialog(self)
        dlg.setStyleSheet(DIALOG_SS)
        dlg.setWindowTitle(T("Editar comentario"))
        dlg.setMinimumWidth(420)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(QLabel(Tf("Comentario de {0} ({1}):", a.author or "—", a.date) if a.date else T("Comentario:")))
        css = "background:#ffffff;color:#111111;border:1px solid #aaa;border-radius:4px;padding:4px;"
        ed = QTextEdit()
        ed.setPlainText(a.text)
        ed.setMaximumHeight(100)
        ed.setStyleSheet(css)
        from ui import spell_ui; spell_ui.attach(ed)
        lay.addWidget(ed)
        replies = [dict(r) for r in a.replies]
        if replies:
            lay.addWidget(QLabel(T("Respuestas:")))
            hist = QTextEdit(); hist.setReadOnly(True); hist.setMaximumHeight(120); hist.setStyleSheet(css)
            hist.setPlainText("\n\n".join(f"{r.get('author') or '—'} ({r.get('date', '')}):\n{r.get('text', '')}" for r in replies))
            lay.addWidget(hist)
        lay.addWidget(QLabel(T("Responder:")))
        ed_reply = QTextEdit(); ed_reply.setMaximumHeight(70); ed_reply.setStyleSheet(css); spell_ui.attach(ed_reply)
        ed_reply.setPlaceholderText(T("Escribe una respuesta (opcional)"))
        lay.addWidget(ed_reply)
        row = QHBoxLayout(); row.addWidget(QLabel(T("Estado:")))
        cb = QComboBox()
        for key, (name, _) in REVIEW_STATES.items(): cb.addItem(T(name), key)
        cb.setCurrentIndex(max(0, cb.findData(a.status)))
        row.addWidget(cb, 1); lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Guardar"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(T("Cancelar"))
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            reply = ed_reply.toPlainText().strip()
            if reply:
                replies.append({"author": AppSettings().get_author(), "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                "text": reply})
            if (ed.toPlainText(), replies, cb.currentData()) == (a.text, a.replies, a.status): return
            self._snap()
            a.text = ed.toPlainText(); a.replies = replies; a.status = cb.currentData()
            self._redraw()
            self._commit()

    def _word_at(self, pt):
        """Índice de la palabra bajo el punto o, si no hay, la más cercana (prioriza la misma línea)."""
        x, y = self._s2p(pt.x(), pt.y())
        best, bd = None, None
        for i, w in enumerate(self._words):
            dx = max(w[0] - x, 0, x - w[2])
            dy = max(w[1] - y, 0, y - w[3])
            d = dx * dx + (4 * dy) ** 2
            if bd is None or d < bd: best, bd = i, d
        return best

    def _update_tsel(self, p1, p2):
        try:
            i, j = self._word_at(p1), self._word_at(p2)
            if i is None: return
            if i > j: i, j = j, i
            rects, parts, prev = [], [], None
            for w in self._words[i:j + 1]:
                sx0, sy0 = self._p2s(w[0], w[1])
                sx1, sy1 = self._p2s(w[2], w[3])
                rects.append(QRectF(sx0, sy0, sx1 - sx0, sy1 - sy0))
                line = (w[5], w[6])               # bloque, línea
                if prev is not None: parts.append(" " if line == prev else "\n")
                parts.append(w[4])
                prev = line
            self._tsel_rects = rects
            self._tsel_text = "".join(parts)
            self._redraw()
        except Exception:
            log.exception("update_tsel")

    def _tsel_menu(self, gpt):
        prev = self._tsel_text[:70] + ("…" if len(self._tsel_text) > 70 else "")
        menu = QMenu(self)
        menu.setStyleSheet(MENU_SS)
        h = menu.addAction(f'"{prev}"')
        h.setEnabled(False)
        menu.addSeparator()
        ac = menu.addAction(get_icon("copy"), T("Copiar"))
        au = menu.addAction(get_icon("line"), T("Subrayar"))
        ast = menu.addAction(get_icon("line"), T("Tachar"))
        ard = menu.addAction(get_icon("redact"), T("Marcar para tachado definitivo"))
        ay = menu.addAction(get_icon("dot", color="#ffeb00"), T("Resaltar amarillo"))
        ag = menu.addAction(get_icon("dot", color="#64dc64"), T("Verde"))
        ab = menu.addAction(get_icon("dot", color="#0078d4"), T("Celeste"))
        ar = menu.addAction(get_icon("dot", color="#ff5050"), T("Rojo"))
        ah = menu.addAction(get_icon("format"), T("Color personalizado…"))
        menu.addSeparator()
        marks = self._marks_in_sel()
        aq = menu.addAction(get_icon("delete"), T("Quitar resaltado, subrayado y tachado"))
        aq.setEnabled(bool(marks))
        menu.addSeparator()
        axl = menu.addAction(get_icon("close"), T("Limpiar"))
        ch = menu.exec(gpt)
        if ch == ac: self._copy_text()
        elif ch == au: self._hl_sel(QColor(self.p_stroke), "underline")
        elif ch == ard: self._hl_sel(QColor("#c62828"), "redact")
        elif ch == ast: self._hl_sel(QColor("#d13438"), "strikeout")
        elif ch == ay: self._hl_sel(QColor(255, 235, 0, 160))
        elif ch == ag: self._hl_sel(QColor(100, 220, 100, 160))
        elif ch == ab: self._hl_sel(QColor(0, 120, 212, 160))
        elif ch == ar: self._hl_sel(QColor(255, 80, 80, 160))
        elif ch == ah:
            c = pick_color(self, QColor(255, 235, 0, 160), allow_alpha=True, title=T("Color personalizado"))
            if c is not None: self._hl_sel(c)
        elif ch == aq: self._remove_marks(marks)
        elif ch == axl:
            self._tsel_rects = []
            self._tsel_text = ""
            self._redraw()

    MARK_KINDS = ("highlight", "underline", "strikeout")

    def _marks_in_sel(self) -> list:
        """Resaltados, subrayados y tachados que tocan el texto seleccionado."""
        sel = [r.adjusted(1, 1, -1, -1) for r in self._tsel_rects]
        return [a for a in self.anns if a.kind in self.MARK_KINDS and any(a.brect().intersects(r) for r in sel)]

    def _remove_marks(self, marks):
        if not marks: return
        self._snap()
        self.anns = [a for a in self.anns if a not in marks]
        if self._sel in marks: self._desel()
        self._tsel_rects = []; self._tsel_text = ""
        self._redraw(); self._commit()

    def _hl_sel(self, color, kind="highlight"):
        """Resalta, subraya o tacha el texto seleccionado."""
        if not self._tsel_rects: return
        self._snap()
        for r in self._tsel_rects:
            self.anns.append(Ann(kind, x1=r.x(), y1=r.y(), x2=r.x()+r.width(), y2=r.y()+r.height(),
                                 stroke=color.name(), opacity=color.alpha()/255 if kind == "highlight" else 1.0))
        self._tsel_rects = []
        self._tsel_text = ""
        self._redraw()
        self._commit()
