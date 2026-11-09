# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Defensas frente a PDFs y documentos maliciosos (análisis de vulnerabilidades del 31/10/2026)."""
import os
import pytest


@pytest.mark.parametrize("uri, ok", [
    ("https://ejemplo.org/x", True), ("http://ejemplo.org", True), ("mailto:soporte@ejemplo.org", True),
    ("HTTPS://EJEMPLO.ORG", True),
    ("file:///C:/Windows/System32/calc.exe", False),       # abrir programas o archivos locales
    ("\\\\servidor\\recurso\\x", False), ("//servidor/recurso", False),   # rutas de red: filtran el usuario de Windows
    ("ms-msdt:/id PCWDiagnostic", False),                   # protocolo usado en ataques reales («Follina»)
    ("search-ms:query=factura", False), ("javascript:alert(1)", False), ("https:", False), ("", False),
])
def test_solo_enlaces_web_y_correo(uri, ok):
    from ui.viewer import safe_link
    assert safe_link(uri) is ok


def test_enlace_peligroso_no_se_abre(qapp, monkeypatch, pdf_path):
    import pymupdf
    from PyQt6.QtWidgets import QMessageBox
    from ui import viewer
    from ui.main_window import MainWindow
    abiertos, avisos = [], []
    monkeypatch.setattr(viewer.QDesktopServices, "openUrl", lambda u: abiertos.append(u))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    w = MainWindow(); w._open_path(pdf_path); qapp.processEvents()
    w._viewer._follow_link({"kind": pymupdf.LINK_URI, "uri": "ms-msdt:/id PCWDiagnostic"})
    assert not abiertos and avisos
    w._viewer._follow_link({"kind": pymupdf.LINK_URI, "uri": "https://ejemplo.org"})
    assert len(abiertos) == 1


@pytest.mark.parametrize("nombre, ok", [
    ("informe.pdf", True), ("foto.JPG", True), ("datos.xlsx", True),
    ("factura.exe", False), ("imagen.iso", False), ("acceso.url", False), ("ayuda.chm", False),
    ("macros.docm", False), ("macros.xlsm", False), ("app.msix", False), ("pagina.html", False),
    ("script.ps1", False), ("sin_extension", False), ("doble.pdf.exe", False),
])
def test_adjuntos_solo_tipos_conocidos(nombre, ok):
    from ui.attachments import can_open
    assert can_open(nombre) is ok


def test_adjunto_abierto_marcado_como_de_internet(tmp_path):
    from ui.attachments import mark_downloaded
    p = str(tmp_path / "a.pdf"); open(p, "wb").write(b"%PDF-1.4")
    mark_downloaded(p)
    try:
        assert "ZoneId=3" in open(p + ":Zone.Identifier").read()
    except OSError:
        pytest.skip("el disco temporal no es NTFS")


def test_office_sin_macros_al_convertir():
    from core import convert
    for app, script in convert._PS.items():
        assert "AutomationSecurity = 3" in script, app            # macros desactivadas a la fuerza


def test_nunca_se_activa_javascript_del_pdf():
    """MuPDF trae un intérprete de JavaScript para formularios, pero solo funciona si se llama a pdf_enable_js."""
    import glob
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fuentes = [p for d in ("core", "ui", "dialogs", "models", "utils") for p in glob.glob(os.path.join(root, d, "*.py"))]
    fuentes += [os.path.join(root, "main.py"), os.path.join(root, "pdfgm_merge.py")]
    assert not [p for p in fuentes if "enable_js" in open(p, encoding="utf-8").read()]
