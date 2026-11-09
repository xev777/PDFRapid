# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Traducción de la interfaz al estilo gettext: el texto en español es la clave.

    T("Guardar")                       → "Save" con la interfaz en inglés
    Tf("Página {0} de {1}", n, total)  → traduce la plantilla y luego la completa

Las traducciones están en locales/en_ui.json ({"texto en español": "English text"}).
Si falta una, se muestra el texto en español (nunca se rompe la interfaz)."""
import json
import os

_EN = None


def _table():
    global _EN
    if _EN is None:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales", "en_ui.json")
        try:
            with open(p, encoding="utf-8") as f:
                _EN = json.load(f)
        except (OSError, ValueError):
            _EN = {}
    return _EN


def lang() -> str:
    from core.translator import translator
    return translator.current_lang


def T(text: str) -> str:
    if not text or lang() == "es":
        return text
    return _table().get(text) or text


def Tf(template: str, *args) -> str:
    return T(template).format(*args)
