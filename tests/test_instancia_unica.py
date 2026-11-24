# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Una sola instancia: la segunda entrega sus PDF a la primera (pestañas) en vez de abrir otra ventana."""
import os
import subprocess
import sys
import time
import uuid

from PyQt6.QtWidgets import QApplication
from core.single_instance import SingleInstance, pdf_args


def test_rutas_pdf(tmp_path):
    a = tmp_path / "a.pdf"; a.write_bytes(b"%PDF-1.4"); (tmp_path / "b.txt").write_text("x")
    assert pdf_args([str(a), str(tmp_path / "b.txt"), str(tmp_path / "no.pdf"), "--selftest"]) == [str(a)]


def test_segunda_instancia_entrega_archivos(qapp):
    base = "PDFRapidTest-" + uuid.uuid4().hex[:8]
    first = SingleInstance(base)
    recibido = []
    first.files.connect(recibido.extend)
    try:
        assert first.start([]) and first.primary
        codigo = ("import sys; from PyQt6.QtCore import QCoreApplication; app = QCoreApplication([]);"
                  "from core.single_instance import SingleInstance;"
                  f"sys.exit(0 if SingleInstance({base!r}, timeout=5).start([r'C:\\docs\\uno.pdf', r'C:\\docs\\dos.pdf']) is False else 3)")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        proc = subprocess.Popen([sys.executable, "-c", codigo], cwd=root)    # otro proceso, como desde el Explorador
        fin = time.monotonic() + 20
        while proc.poll() is None and time.monotonic() < fin:
            QApplication.processEvents(); time.sleep(0.02)
        QApplication.processEvents()
        assert proc.wait(5) == 0                                           # la segunda no sigue
        assert recibido == [r"C:\docs\uno.pdf", r"C:\docs\dos.pdf"]
    finally:
        first.release()
    third = SingleInstance(base, timeout=2)                 # tras soltarla (reinicio), la nueva es la principal
    try:
        assert third.start([]) and third.primary
    finally:
        third.release()


def test_ventana_abre_en_pestanas(qapp, tmp_path):
    import pymupdf
    from ui.main_window import MainWindow
    rutas = []
    for n in ("x", "y"):
        d = pymupdf.open(); d.new_page(); p = str(tmp_path / f"{n}.pdf"); d.save(p); d.close(); rutas.append(p)
    w = MainWindow()
    w.open_from_instance(rutas)
    assert w.doc_tabs.count() == 2
