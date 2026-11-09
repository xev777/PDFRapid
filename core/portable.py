# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Modo portable: si junto al .exe existe el archivo `portable.txt`, la configuración, el log y los
archivos auxiliares se guardan en la carpeta `data` del programa (nada en el registro ni en el perfil)."""
import os
import sys
from PyQt6.QtCore import QSettings

_APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else sys.argv[0] or __file__))
PORTABLE = getattr(sys, "frozen", False) and os.path.isfile(os.path.join(_APP_DIR, "portable.txt"))


def data_dir() -> str:
    """Carpeta para log e iconos generados: `<programa>/data` en modo portable, `~/.pdfrapid` si no."""
    d = os.path.join(_APP_DIR, "data") if PORTABLE else os.path.join(os.path.expanduser("~"), ".pdfrapid")
    os.makedirs(d, exist_ok=True)
    return d


def qsettings(app: str) -> QSettings:
    """QSettings("Pdfgm", app), o un .ini en `data` en modo portable."""
    if PORTABLE:
        return QSettings(os.path.join(data_dir(), f"{app}.ini"), QSettings.Format.IniFormat)
    return QSettings("Pdfgm", app)
