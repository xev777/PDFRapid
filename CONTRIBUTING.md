# Colaborar con PDFRapid / Contributing

_English below._

¡Gracias por tu interés! Reportes de errores, traducciones y mejoras son bienvenidos.

## Reportar un error
Abre un *issue* con: versión (Ayuda → Acerca de), Windows, pasos para reproducirlo y, si puedes, el log
`~/pdfrapid.log` (o `data\pdfrapid.log` en la versión portable). No adjuntes PDFs con datos personales.

## Enviar cambios
1. Haz un *fork* y una rama a partir de `main`.
2. Instala el entorno (ver README) y ejecuta `venv\Scripts\python -m pytest -q`: todo debe pasar.
3. Reglas del proyecto:
   - **Sin conexión**: no agregues llamadas de red, telemetría ni servicios en la nube (las pruebas bloquean la red).
   - **Licencias**: solo dependencias compatibles con AGPL-3.0 (`tests/test_licencias.py` lo comprueba) y
     añádelas a `packaging/THIRD_PARTY_NOTICES.txt`.
   - Cada archivo `.py` nuevo lleva la cabecera `SPDX-License-Identifier: AGPL-3.0-or-later`.
   - Textos de interfaz con `T("texto en español")` / `Tf("plantilla {0}", x)` (`core/i18n.py`) y su
     traducción en `locales/en_ui.json`.
   - Configuración con `core.portable.qsettings(app)`, nunca `QSettings` directo.
   - Las pruebas no deben abrir diálogos modales.
4. Añade una prueba para lo que cambias y describe el cambio en el pull request.
5. Abre el *pull request* describiendo el cambio.

Al enviar un aporte aceptas que se publique bajo la licencia AGPL-3.0-or-later del proyecto.

---

## Contributing (English)

Thanks for your interest! Bug reports, translations and improvements are welcome.

**Bug reports:** open an issue with the version (Help → About), Windows version, steps to reproduce and, if
possible, the log `~/pdfrapid.log` (`data\pdfrapid.log` in the portable version). Don't attach PDFs with
personal data.

**Pull requests:** branch from `main`, make sure `venv\Scripts\python -m pytest -q` passes, and follow the
rules above: no network access or telemetry; AGPL-compatible dependencies only (listed in
`packaging/THIRD_PARTY_NOTICES.txt`); SPDX header on new `.py` files; UI strings through `T()`/`Tf()` with
the English text in `locales/en_ui.json`; settings through `core.portable.qsettings(app)`; tests must not
open modal dialogs. Add a test and describe the change in the pull request.

By contributing you agree that your contribution is licensed under the project's AGPL-3.0-or-later license.
