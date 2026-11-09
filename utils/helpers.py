# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Funciones de ayuda y decoradores"""
from core.i18n import T, Tf
import functools
import inspect
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from core.logger import log


def wire_toggle_style(btn, off_style: str = None, on_style: str = None):
    """Fuerza el relleno del estado 'checked' de un QPushButton/QToolButton
    aplicando un stylesheet inline por widget en vez de depender del selector
    QSS ':checked'. En esta combinación PyQt6 + Fusion + Windows, ':checked'
    a veces no pinta el fondo (el botón queda 'hueco', solo se ve el borde) —
    el stylesheet inline por widget sí se pinta siempre de forma confiable."""
    from ui.styles import C
    off = off_style or (
        f"QPushButton{{background-color:transparent;border:1px solid {C['border']};"
        f"border-radius:4px;color:{C['muted']};}}"
        f"QPushButton:hover{{background-color:{C['hover']};color:{C['text']};}}"
    )
    on = on_style or (
        f"QPushButton{{background-color:{C['accent']};border:1px solid {C['accent']};"
        f"border-radius:4px;color:white;}}"
    )
    btn.setStyleSheet(on if btn.isChecked() else off)
    btn.toggled.connect(lambda checked, b=btn: b.setStyleSheet(on if checked else off))

def guard(fn):
    """Decorador para manejar excepciones en métodos de la UI"""
    try:
        n = sum(1 for p in inspect.signature(fn).parameters.values()
                if p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY))
    except Exception:
        n = None

    @functools.wraps(fn)
    def _w(*a, **kw):
        try:
            if n is not None and len(a) > n:
                a = a[:n]
            return fn(*a, **kw)
        except PermissionError as e:
            log.error(f"{fn.__name__}: {e}")
            QMessageBox.critical(None, T("Error"), T("El archivo está en uso por otro programa."))
        except Exception as e:
            log.error(f"{fn.__name__}: {e}\n{traceback.format_exc()}")
            app = QApplication.instance()
            if app:
                QMessageBox.critical(None, Tf("Error — {0}", fn.__name__),
                                     Tf("{0}\n\nRevisa ~/pdfrapid.log para detalles.", e))
    return _w