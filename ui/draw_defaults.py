# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Valores por defecto para anotaciones nuevas.

Reemplaza al antiguo panel lateral de propiedades: ya no hay un panel visible
para fijar el estilo de dibujo, así que los objetos nuevos se crean con estos
valores fijos y razonables. Para cambiar el estilo de un objeto ya creado se
usa el menú contextual (clic derecho → "Formato del objeto…"), que edita la
anotación directamente sin depender de este objeto.
"""
from PyQt6.QtGui import QColor
from ui.styles import C


class DrawDefaults:
    stroke_color = QColor(C['accent'])
    fill_color = None
    line_width = 1.5
    opacity = 1.0
    stroke_style = "solid"
    font_name = "Segoe UI"
    font_size = 12
    text_color = QColor("#111111")

    on_select = None            # la barra de formato muestra el estilo del objeto seleccionado

    def load(self, ann):
        if self.on_select: self.on_select(ann)
