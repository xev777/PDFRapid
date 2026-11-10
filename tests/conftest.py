# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
os.environ["PDFRAPID_RECOVERY_DIR"] = tempfile.mkdtemp(prefix="pdfrapid_rec_")   # nunca tocar la recuperación real


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from ui.styles import SS
    app.setStyleSheet(SS)
    return app


@pytest.fixture
def pdf_path(tmp_path):
    import pymupdf
    p = str(tmp_path / "doc.pdf")
    d = pymupdf.open()
    for i in range(2):
        d.new_page().insert_text((72, 72), f"Pagina {i + 1}")
    d.save(p)
    d.close()
    return p


@pytest.fixture(autouse=True)
def _sin_dialogos_modales(monkeypatch):
    """Un diálogo modal sin respuesta cuelga las pruebas: si aparece uno no previsto, falla."""
    from PyQt6.QtWidgets import QMessageBox, QInputDialog

    def inesperado(*a, **k):
        raise AssertionError(f"Diálogo inesperado: {a[1:3]}")
    for name in ("question", "information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, inesperado)
    monkeypatch.setattr(QInputDialog, "getText", inesperado)


@pytest.fixture(autouse=True)
def _sin_errores_en_eventos(monkeypatch):
    """En la app real, un error no capturado dentro de un evento de Qt la cierra sin aviso:
    aquí cualquiera de esos errores hace fallar la prueba."""
    import sys, traceback
    errores = []
    monkeypatch.setattr(sys, "excepthook", lambda t, e, tb: errores.append("".join(traceback.format_exception(t, e, tb))))
    yield
    assert not errores, "Error no capturado en un evento de Qt:\n" + errores[0]


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch):
    """PDFRapid funciona 100 % sin conexión: cualquier intento de usar la red hace fallar la prueba."""
    import socket

    LOCAL = ("127.0.0.1", "::1", "localhost")      # asyncio usa conexiones locales internas en Windows

    def vigilar(orig, pos):
        def f(*a, **k):
            dest = a[pos] if len(a) > pos else None
            host = dest[0] if isinstance(dest, tuple) else dest
            if host not in LOCAL:
                raise AssertionError(f"Intento de conexión de red: {dest}")
            return orig(*a, **k)
        return f
    monkeypatch.setattr(socket.socket, "connect", vigilar(socket.socket.connect, 1))
    monkeypatch.setattr(socket.socket, "connect_ex", vigilar(socket.socket.connect_ex, 1))
    monkeypatch.setattr(socket, "getaddrinfo", vigilar(socket.getaddrinfo, 0))
    monkeypatch.setattr(socket, "create_connection", vigilar(socket.create_connection, 0))


@pytest.fixture(autouse=True)
def _liberar_ventanas():
    """Destruye las ventanas que crea cada prueba. Sin esto se acumulaban miles (≈4 GB) y, con poca RAM libre,
    Qt fallaba al pintar (access violation) o veraPDF se quedaba sin memoria."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    antes = {id(w) for w in app.topLevelWidgets()} if app else set()
    yield
    app = QApplication.instance()
    if not app:
        return
    from PyQt6.QtCore import QEvent
    from ui.main_window import MainWindow
    for w in app.topLevelWidgets():         # solo ventanas principales: los singletons (lupa QR…) viven toda la sesión
        if id(w) not in antes and isinstance(w, MainWindow):
            w.hide(); w.deleteLater()      # sin close(): no dispara «¿guardar cambios?»
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    app.processEvents()
