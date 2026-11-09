# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Constantes de la aplicación"""
from PyQt6.QtCore import Qt

APP_NAME = "PDFRapid"
APP_VERSION = "1.0"
APP_TAGLINE = "Editor de PDF libre y sin conexión"
APP_AUTHOR = "Fernando Erazo"
SOURCE_URL = "https://github.com/xev777/PDFRapid"                 # código fuente público (AGPL)
DONATE_URL = "https://ko-fi.com/pdfrapid"      # provisional: página de donación (Ko-fi)
APP_TITLE = f"{APP_NAME} — Editor de PDF"

# ══════════════════════════════════════════════════════════
# HERRAMIENTAS
# ══════════════════════════════════════════════════════════
T_SELECT = "select"
T_LASSO = "lasso"
T_TXTSEL = "txtsel"
T_TEXT = "text"
T_TEXTBOX = "textbox"
T_COMMENT = "comment"
T_HL = "highlight"
T_LINE = "line"
T_ARROW = "arrow"
T_DARROW = "darrow"
T_RECT = "rect"
T_RRECT = "rrect"
T_CIRCLE = "circle"
T_TRI = "triangle"
T_ARROW_SHAPE = "arrow_shape"
T_OCR_REGION = "ocr_region"
T_IMAGE = "image"
T_INK = "ink"
T_SIGN = "signature"
T_STAMP = "stamp"
T_HAND = "hand"
T_REDACT = "redact"
T_MEASURE = "measure"
T_QRLENS = "qrlens"
T_FILL = "fill"           # Rellenar y firmar: ✓ ✗ ● línea, fecha, iniciales

# ══════════════════════════════════════════════════════════
# CONSTANTES FÍSICAS
# ══════════════════════════════════════════════════════════
HS = 8          # Tamaño de handle en píxeles
MAX_RECENT = 12 # Máximo de archivos recientes
AUTOSAVE_MS = 120_000          # autoguardado para recuperación (2 min)

# ══════════════════════════════════════════════════════════
# CURSORES PARA HANDLES
# ══════════════════════════════════════════════════════════
HANDLE_CURSORS = {
    0: Qt.CursorShape.SizeFDiagCursor,
    1: Qt.CursorShape.SizeVerCursor,
    2: Qt.CursorShape.SizeBDiagCursor,
    3: Qt.CursorShape.SizeHorCursor,
    4: Qt.CursorShape.SizeHorCursor,
    5: Qt.CursorShape.SizeBDiagCursor,
    6: Qt.CursorShape.SizeVerCursor,
    7: Qt.CursorShape.SizeFDiagCursor,
    8: Qt.CursorShape.CrossCursor,
}