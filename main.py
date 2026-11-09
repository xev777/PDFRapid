# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""
PDFRapid — Editor de PDF libre y sin conexión
Punto de entrada principal
"""
from core.i18n import T, Tf
import sys
import os
import time

# ══════════════════════════════════════════════════════════
# FORZAR LA RUTA CORRECTA (Solución a prueba de fallos)
# ══════════════════════════════════════════════════════════
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ══════════════════════════════════════════════════════════
# IMPORTS
# ══════════════════════════════════════════════════════════
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTranslator, QLibraryInfo, QTimer
from core.logger import log
from core.translator import translator
from core.constants import APP_NAME, APP_VERSION
from ui.styles import SS

# ══════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════
def _excepthook(exc_type, exc, tb):
    """Un error no capturado dentro de un evento de Qt cerraría la app sin aviso (PyQt llama a abort).
    Se registra con su traza y se avisa, y la app sigue funcionando."""
    import traceback
    log.critical("Error no capturado:\n" + "".join(traceback.format_exception(exc_type, exc, tb)))
    try:
        from PyQt6.QtWidgets import QMessageBox
        if QApplication.instance():
            QMessageBox.warning(None, APP_NAME, Tf("Ocurrió un error inesperado y se registró en ~/pdfrapid.log:\n\n{0}\n\nPuedes seguir trabajando; si algo no responde, guarda y reinicia.", exc))
    except Exception:
        pass


def main():
    sys.excepthook = _excepthook
    try:
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setOrganizationName("Pdfgm")          # clave interna de la configuración guardada
        app.setApplicationVersion(APP_VERSION)

        # Fusion garantiza que QSS se aplique de forma consistente a los widgets.
        app.setStyle("Fusion")

        # Cargar la traducción al español de los textos internos de Qt (botones
        # estándar de QMessageBox como "Sí"/"No"/"Guardar", diálogos nativos, etc.)
        # — sin esto, esos textos aparecen en inglés sin importar el idioma de la app.
        qt_translator = QTranslator(app)
        qt_tr_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if translator.current_lang != "es":
            pass                                  # inglés: los textos propios de Qt ya vienen en inglés
        elif qt_translator.load("qtbase_es", qt_tr_path):
            app.installTranslator(qt_translator)
        else:
            log.warning("No se pudo cargar la traducción qtbase_es de Qt")

        # Aplicar stylesheet global — al estar en app (no en window),
        # se hereda en todos los popups, menús y diálogos modales.
        # (El selector de color es propio — dialogs/color_picker.py — no usa QColorDialog,
        # cuyo interior no respetaba el QSS de forma confiable en este entorno.)
        app.setStyleSheet(SS)

        # Pantalla de inicio: se muestra antes de cargar la interfaz (lo más lento del arranque)
        from ui import branding
        app.setWindowIcon(branding.logo_icon())
        splash = branding.splash()
        splash.show()
        branding.message(splash, T("Cargando interfaz…"))
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.35:           # dejar que se vea el fundido de entrada
            app.processEvents(); time.sleep(0.01)

        log.info(f"Idioma activo: {translator.current_lang}")

        from ui.main_window import MainWindow
        window = MainWindow()
        pdf = next((a for a in sys.argv[1:] if a.lower().endswith(".pdf") and os.path.isfile(a)), None)
        if pdf:                                   # "Abrir con…" / doble clic en un .pdf
            branding.message(splash, Tf("Abriendo {0}…", os.path.basename(pdf)))
            app.processEvents()
            window._open_path(pdf)

        def mostrar():
            window.show()
            splash.finish(window)
        # mínimo ~1,6 s en pantalla para que la presentación no sea un parpadeo
        QTimer.singleShot(max(0, int((1.6 - (time.monotonic() - t0)) * 1000)), mostrar)

        log.info(f"{APP_NAME} {APP_VERSION} iniciado correctamente")
        sys.exit(app.exec())

    except Exception as e:
        import traceback
        print(f"\n❌ ERROR FATAL: {e}")
        print("Revisa la estructura de carpetas o el archivo ~/pdfrapid.log")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    if "--selftest" in sys.argv:              # autodiagnóstico del programa empaquetado
        from core.selftest import run
        i = sys.argv.index("--selftest")
        sys.exit(run(sys.argv[i + 1] if len(sys.argv) > i + 1 else None))
    main()
