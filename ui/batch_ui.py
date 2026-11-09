# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Documento → Procesar por lotes: una acción sobre todos los PDF de una carpeta, en segundo plano."""
from core.i18n import T, Tf
import os
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton, QCheckBox,
                             QComboBox, QFileDialog, QMessageBox, QStackedWidget, QWidget, QLabel, QProgressDialog,
                             QPlainTextEdit, QDialogButtonBox)
from core import batch, pdf_tools
from core.constants import APP_NAME, APP_VERSION


class _Run(QThread):
    step = pyqtSignal(int, str)

    def __init__(self, files, folder, out_dir, action, opts):
        super().__init__()
        self.args, self.results, self.stop = (files, folder, out_dir, action, opts), [], False

    def run(self):
        files, folder, out_dir, action, opts = self.args
        self.results = batch.run(files, folder, out_dir, action, opts,
                                 progress=lambda i, src: self.step.emit(i, os.path.basename(src)),
                                 cancelled=lambda: self.stop)


class BatchDialog(QDialog):
    def __init__(self, parent, folder=""):
        super().__init__(parent)
        self.setWindowTitle(T("Procesar por lotes")); self.setMinimumWidth(520)
        lay = QVBoxLayout(self); form = QFormLayout()
        self.ed_in = QLineEdit(folder); bt_in = QPushButton(T("Elegir…"))
        bt_in.clicked.connect(lambda: self._pick(self.ed_in))
        row = QHBoxLayout(); row.addWidget(self.ed_in, 1); row.addWidget(bt_in)
        form.addRow(T("Carpeta con los PDF:"), row)
        self.cb_sub = QCheckBox(T("Incluir subcarpetas")); form.addRow(self.cb_sub)
        self.cb_action = QComboBox()
        for key, (name, _) in batch.ACTIONS.items(): self.cb_action.addItem(T(name), key)
        form.addRow(T("Acción:"), self.cb_action)
        self.stack = QStackedWidget()
        self.opt = {}
        for key in batch.ACTIONS:
            w = QWidget(); f = QFormLayout(w); f.setContentsMargins(0, 0, 0, 0)
            if key == "compress":
                c = QComboBox()
                for k, (name, _) in pdf_tools.LEVELS.items(): c.addItem(T(name), k)
                c.setCurrentIndex(1); f.addRow(T("Nivel:"), c); self.opt["level"] = c
            elif key == "watermark":
                e = QLineEdit(T("CONFIDENCIAL")); f.addRow(T("Texto:"), e); self.opt["text"] = e
            elif key == "number":
                e = QLineEdit(T("Página {n} de {total}")); f.addRow(T("Formato:"), e); self.opt["fmt"] = e
                c = QComboBox()
                for k, name in pdf_tools.POSITIONS.items(): c.addItem(T(name), k)
                c.setCurrentIndex(1); f.addRow(T("Posición:"), c); self.opt["pos"] = c
            elif key == "protect":
                e1, e2 = QLineEdit(), QLineEdit()
                for e in (e1, e2): e.setEchoMode(QLineEdit.EchoMode.Password)
                f.addRow(T("Contraseña para abrir:"), e1); f.addRow(T("Repetir:"), e2)
                self.opt["password"], self.opt["password2"] = e1, e2
            elif key == "ocr":
                f.addRow(QLabel(T("Solo se reconocen las páginas sin texto. Puede tardar varios minutos por documento.")))
            self.stack.addWidget(w)
        self.cb_action.currentIndexChanged.connect(self.stack.setCurrentIndex)
        form.addRow(self.stack)
        self.ed_out = QLineEdit(); bt_out = QPushButton(T("Elegir…"))
        bt_out.clicked.connect(lambda: self._pick(self.ed_out))
        row = QHBoxLayout(); row.addWidget(self.ed_out, 1); row.addWidget(bt_out)
        self.ed_out.setPlaceholderText(T("por defecto: subcarpeta «PDFRapid» dentro de la carpeta elegida"))
        form.addRow(T("Guardar resultados en:"), row)
        lay.addLayout(form)
        note = QLabel(T("Los archivos originales no se modifican: cada resultado se guarda en la carpeta de salida."))
        note.setWordWrap(True); lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(T("Procesar"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(T("Cancelar"))
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _pick(self, ed):
        d = QFileDialog.getExistingDirectory(self, T("Elegir carpeta"), ed.text() or self.ed_in.text())
        if d: ed.setText(os.path.normpath(d))

    def folder(self): return self.ed_in.text().strip()

    def out_dir(self): return self.ed_out.text().strip() or os.path.join(self.folder(), APP_NAME)

    def action(self): return self.cb_action.currentData()

    def options(self) -> dict:
        a, o = self.action(), self.opt
        if a == "compress": return {"level": o["level"].currentData()}
        if a == "watermark": return {"text": o["text"].text().strip()}
        if a == "number": return {"fmt": o["fmt"].text(), "pos": o["pos"].currentData()}
        if a == "protect": return {"password": o["password"].text()}
        if a == "pdfa": return {"producer": f"{APP_NAME} {APP_VERSION}"}
        return {}

    def accept(self):
        if not os.path.isdir(self.folder()):
            QMessageBox.warning(self, T("Procesar por lotes"), T("Elige una carpeta que exista.")); return
        a = self.action()
        if a == "protect":
            if not self.opt["password"].text():
                QMessageBox.warning(self, T("Contraseña"), T("Escribe una contraseña.")); return
            if self.opt["password"].text() != self.opt["password2"].text():
                QMessageBox.warning(self, T("Contraseña"), T("Las contraseñas no coinciden.")); return
        if a == "watermark" and not self.opt["text"].text().strip():
            QMessageBox.warning(self, T("Marca de agua"), T("Escribe el texto de la marca de agua.")); return
        if a == "number":
            try:
                self.opt["fmt"].text().format(n=1, total=1)
            except (KeyError, ValueError, IndexError):
                QMessageBox.warning(self, T("Formato"), T("Formato no válido. Usa {n} para el número y {total} para el total.")); return
        super().accept()


def batch_dialog(win):
    v = win._viewer
    start = os.path.dirname(v.path) if v and v.path else ""
    dlg = BatchDialog(win, start)
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    folder, out_dir, action = dlg.folder(), dlg.out_dir(), dlg.action()
    out_abs = os.path.abspath(out_dir)
    files = [f for f in batch.find_pdfs(folder, dlg.cb_sub.isChecked())
             if not os.path.abspath(f).startswith(out_abs + os.sep)]           # no reprocesar resultados anteriores
    if not files:
        QMessageBox.information(win, T("Procesar por lotes"), T("No hay archivos PDF en esa carpeta.")); return
    job = _Run(files, folder, out_dir, action, dlg.options())
    prog = QProgressDialog(T("Preparando…"), T("Cancelar"), 0, len(files), win)
    prog.setWindowTitle(T("Procesar por lotes")); prog.setMinimumDuration(0)
    job.step.connect(lambda i, name: (prog.setValue(i), prog.setLabelText(Tf("{0} de {1}: {2}", i + 1, len(files), name))))
    prog.canceled.connect(lambda: setattr(job, "stop", True))
    from PyQt6.QtCore import QEventLoop
    loop = QEventLoop(); job.finished.connect(loop.quit); job.start(); loop.exec()
    prog.close()
    show_report(win, job.results, out_dir, len(files))


def show_report(win, results, out_dir, total):
    ok = [r for r in results if not r[2]]
    bad = [r for r in results if r[2]]
    lines = [Tf("Procesados: {0} de {1}. Con errores: {2}.", len(ok), total, len(bad))]
    if len(results) < total: lines.append(T("Cancelado antes de terminar."))
    lines += [f"✗ {os.path.basename(src)}: {T(err)}" for src, _, err, _ in bad]
    dlg = QDialog(win); dlg.setWindowTitle(T("Procesar por lotes")); dlg.setMinimumSize(520, 300)
    lay = QVBoxLayout(dlg)
    txt = QPlainTextEdit("\n".join(lines)); txt.setReadOnly(True); lay.addWidget(txt, 1)
    row = QHBoxLayout()
    if ok and os.path.isdir(out_dir):
        b = QPushButton(T("Abrir carpeta de resultados")); b.clicked.connect(lambda: os.startfile(out_dir)); row.addWidget(b)
    row.addStretch(1)
    c = QPushButton(T("Cerrar")); c.clicked.connect(dlg.accept); row.addWidget(c)
    lay.addLayout(row)
    dlg.exec()
