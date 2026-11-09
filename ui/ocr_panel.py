# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Panel de control OCR (RapidOCR, sin conexión ni programas externos)"""
from core.i18n import T, Tf
from core.logger import log
from core import ocr
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QPlainTextEdit, QProgressDialog, QFileDialog, QApplication, QMessageBox)
from PyQt6.QtCore import QThread, pyqtSignal as Signal
import pymupdf
import os
from ui.styles import C
from ui.icons import get_icon


class OcrWorker(QThread):
    finished = Signal(str, bytes)
    progress = Signal(int)

    def __init__(self, data: bytes, page_indices: list, region=None):
        super().__init__()
        self._data = data          # copia propia: el visor sigue usando su documento
        self._pages = page_indices
        self._region = region
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        doc = None
        try:
            doc = pymupdf.open(stream=self._data, filetype="pdf")
            texts, results = [], {}
            for i, pi in enumerate(self._pages):
                if self._cancel:
                    texts.append("— OCR cancelado —")
                    break
                lines = ocr.ocr_page(doc[pi], self._region)
                results[pi] = lines
                texts.append(f"--- Página {pi+1} ---\n" + "\n".join(t for _, t in lines) + "\n")
                self.progress.emit(int((i + 1) / len(self._pages) * 100))
            pdf = b""
            if results and not self._region:
                try:
                    pdf = ocr.searchable_pdf(doc, results)
                except Exception:
                    log.exception("OCR: no se pudo generar el PDF")
            self.finished.emit("\n".join(texts), pdf)
        except ImportError:
            self.finished.emit(T("⚠️ El OCR no está instalado.\nEjecuta: pip install -r requirements-ocr.txt"), b"")
        except Exception as e:
            log.exception("OCR")
            self.finished.emit(Tf("Error OCR: {0}", e), b"")
        finally:
            if doc: doc.close()


class OcrPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(280)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        hdr = QLabel(T("OCR — RECONOCIMIENTO DE TEXTO"))
        hdr.setStyleSheet(f"color:{C['accent']};font-size:10px;font-weight:700;letter-spacing:1px;")
        lay.addWidget(hdr)

        self.btn_all = QPushButton(T("OCR todo el documento"))
        self.btn_all.setIcon(get_icon("ocr_panel", color=C['icon_active']))
        self.btn_all.clicked.connect(self._ocr_all)
        lay.addWidget(self.btn_all)

        self.btn_region = QPushButton(T("OCR región seleccionada"))
        self.btn_region.setIcon(get_icon("ocr_region"))
        self.btn_region.setObjectName("flat")
        lay.addWidget(self.btn_region)
        self.btn_region.clicked.connect(self._ocr_region)

        self.lbl_status = QLabel(T("Idioma automático (español, inglés, francés, alemán, portugués, italiano, chino, japonés…). "
                                "Selecciona la herramienta OCR y dibuja un área, o usa 'Todo el documento'. "
                                "'Guardar PDF' crea una copia con texto buscable."))
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(f"color:{C['muted']};font-size:11px;")
        lay.addWidget(self.lbl_status)

        self.result = QPlainTextEdit()
        self.result.setPlaceholderText(T("El texto extraído aparecerá aquí..."))
        self.result.setStyleSheet(
            f"background:{C['white']};color:{C['text']};border:1px solid {C['border']};"
            "border-radius:5px;padding:6px;font-family:Consolas;font-size:11px;"
        )
        lay.addWidget(self.result, 1)

        btns = QHBoxLayout()
        self.btn_copy = QPushButton(T("Copiar"))
        self.btn_copy.setIcon(get_icon("copy"))
        self.btn_copy.setObjectName("flat")
        self.btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.result.toPlainText()))
        btns.addWidget(self.btn_copy)

        self.btn_save_pdf = QPushButton(T("Guardar PDF"))
        self.btn_save_pdf.setIcon(get_icon("save"))
        self.btn_save_pdf.setObjectName("flat")
        self.btn_save_pdf.clicked.connect(self._save_pdf)
        btns.addWidget(self.btn_save_pdf)
        lay.addLayout(btns)

        self._pdf_bytes = b""
        self._doc = None
        self._canvases = []
        self._worker = None
        self._prog = None

    def set_doc(self, doc, canvases: list):
        self._doc = doc
        self._canvases = canvases

    def _run_ocr(self, page_indices: list, region=None):
        if not self._doc:
            return
        if self._worker and self._worker.isRunning():
            return
        self._prog = QProgressDialog(T("Ejecutando OCR… (la primera vez puede tardar más)"), T("Cancelar"), 0, 100, self)
        self._prog.setWindowTitle(T("OCR"))
        self._prog.setMinimumWidth(320)
        self._prog.show()
        self._worker = OcrWorker(self._doc.tobytes(), page_indices, region)
        self._prog.canceled.connect(self._worker.cancel)
        self._worker.progress.connect(self._prog.setValue)
        self._worker.finished.connect(self._on_ocr_finished)
        self._worker.start()

    def _on_ocr_finished(self, txt, pdf):
        self.result.setPlainText(txt)
        self._pdf_bytes = pdf
        self.btn_save_pdf.setEnabled(len(pdf) > 0)
        if self._prog:
            self._prog.close()

    def _ocr_all(self):
        if not self._doc:
            self.lbl_status.setText(T("Abre un PDF primero."))
            return
        self._run_ocr(list(range(len(self._doc))))

    def _ocr_region(self):
        for cv in self._canvases:
            if cv._ocr_rect:
                r = cv._ocr_rect
                pr = cv._prect
                if pr:
                    w, h = cv._bw, cv._bh
                    pdf_r = pymupdf.Rect(
                        r.x()*pr.width/w, r.y()*pr.height/h,
                        (r.x()+r.width())*pr.width/w, (r.y()+r.height())*pr.height/h
                    )
                    self._run_ocr([cv.page_num], pdf_r)
                    return
        self.lbl_status.setText(T("Usa la herramienta OCR para dibujar una región primero."))

    def _save_pdf(self):
        if not self._pdf_bytes:
            return
        path, _ = QFileDialog.getSaveFileName(
            None, T("Guardar PDF OCR"), os.path.expanduser("~/ocr_resultado.pdf"), T("PDF Files (*.pdf)")
        )
        if path:
            with open(path, 'wb') as f:
                f.write(self._pdf_bytes)
            QMessageBox.information(None, T("Guardado"), Tf("PDF OCR guardado:\n{0}", path))