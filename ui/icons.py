# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Sistema de iconos vectoriales — reemplaza los emojis por SVG dibujados en tiempo de
ejecución. Sin dependencias externas ni descargas: cada glifo se define una sola vez
(viewBox 0 0 24 24) y se recolorea al vuelo según el tema (C['icon'], C['icon_active'], etc.)."""
from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer
from ui.styles import C

_SVG_PATHS = {
    # Herramientas (core/constants.py T_*)
    "select":      '<path d="M4 3l14 8-6 2-2 6-6-16z" fill="currentColor"/>',
    "lasso":       '<path d="M12 3C7 3 3 6 3 10c0 3 2 5 5 5.5L7 20l3-2 2 2v-4c4-.5 7-3 7-6.5C19 6 15 3 12 3z" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "txtsel":      '<path d="M4 5h16M6 5v3a2 2 0 002 2h1M18 5v3a2 2 0 01-2 2h-1M9 10v9M15 10v9M7 19h5m3 0h2" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/>',
    "text":        '<path d="M4 5h16M12 5v14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>',
    "textbox":     '<rect x="3" y="5" width="18" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 9h8M8 12h8M8 15h5" stroke="currentColor" stroke-width="1.3"/>',
    "comment":     '<path d="M4 4h16v11H9l-4 4V4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
    "highlight":   '<rect x="4" y="8" width="16" height="8" fill="currentColor" opacity="0.35"/><rect x="4" y="8" width="16" height="8" fill="none" stroke="currentColor" stroke-width="1.4"/>',
    "line":        '<path d="M4 20L20 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    "arrow":       '<path d="M4 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "darrow":      '<path d="M4 12h16M8 6l-4 6 4 6M16 6l4 6-4 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "rect":        '<rect x="4" y="6" width="16" height="12" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    "rrect":       '<rect x="4" y="6" width="16" height="12" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    "circle":      '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    "triangle":    '<path d="M12 5l8 14H4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
    "arrow_shape": '<path d="M4 10h8V6l8 6-8 6v-4H4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
    "image":       '<rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="8.5" cy="9.5" r="1.6" fill="currentColor"/><path d="M4 17l5-5 3 3 4-5 5 6" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "crop":        '<path d="M6 2v14a2 2 0 002 2h14M2 6h14a2 2 0 012 2v14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "ruler":       '<path d="M3 15.5L15.5 3 21 8.5 8.5 21z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M7 11.5l1.8 1.8M9.5 9l2.6 2.6M12 6.5l1.8 1.8M14.5 4l2.6 2.6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "digisign":    '<path d="M5 3h9l4 4v6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M5 3v18h7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M8 9h6M8 12h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="17.5" cy="16" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M15.8 18.5L15 22l2.5-1.3L20 22l-.8-3.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
    "qrlens":      '<circle cx="10" cy="10" r="6.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M15 15l5.5 5.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M7 7h2.2v2.2H7zM10.8 7H13v2.2h-2.2zM7 10.8h2.2V13H7z" fill="currentColor"/><path d="M11 11h2v2h-2z" fill="currentColor"/>',
    "ocr_region":  '<rect x="3" y="3" width="7" height="7" fill="none" stroke="currentColor" stroke-width="1.6"/><rect x="14" y="14" width="7" height="7" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.6"/>',

    "redact":      '<rect x="3" y="9" width="18" height="6" rx="1" fill="currentColor"/><path d="M3 5h10M3 19h14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    "hand":        '<path d="M8 13V5.5a1.5 1.5 0 013 0V11m0-6.5a1.5 1.5 0 013 0V11m0-5a1.5 1.5 0 013 0v7c0 4-2.5 7-6 7-2.5 0-4-1.2-5.5-3.5L4 13.5a1.5 1.5 0 012.5-1.6L8 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
    "stamp":       '<path d="M9 4h6l-1 7h3a2 2 0 012 2v2H5v-2a2 2 0 012-2h3L9 4zM4 19h16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>',
    "moon":        '<path d="M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
    "pencil":      '<path d="M4 20l1-4L16 5l3 3L8 19l-4 1zM14 7l3 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
    "signature":   '<path d="M3 17c3-1 4-9 6-9s0 9 2 9 2-5 4-5 1 4 3 4 2-2 3-2M3 21h18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    # Comunes / toolbar / menú
    "prev":        '<path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "next":        '<path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "fit_width":   '<rect x="5" y="3" width="14" height="18" rx="1" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M2 12h20M5 9l-3 3 3 3M19 9l3 3-3 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "fit_page":    '<rect x="6" y="3" width="12" height="18" rx="1" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M9 8h6M9 12h6M9 16h4" stroke="currentColor" stroke-width="1.3"/>',
    "lock":        '<rect x="5" y="11" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 11V8a4 4 0 018 0v3" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "eyedropper":  '<path d="M17 3l4 4-3 3-1.5-1.5L7 18l-4 1 1-4 9.5-9.5L12 4l3-3z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
    "open":        '<path d="M3 7h6l2 2h10v10H3V7z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
    "save":        '<path d="M5 4h11l3 3v13H5V4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><rect x="8" y="4" width="7" height="5" fill="none" stroke="currentColor" stroke-width="1.4"/>',
    "print":       '<path d="M6 9V4h12v5M6 18h12v-5H6v5zM4 9h16v6H4V9z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
    "search":      '<circle cx="10" cy="10" r="6" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M15 15l5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "zoom_in":     '<circle cx="10" cy="10" r="6" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M15 15l5 5M10 7v6M7 10h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "zoom_out":    '<circle cx="10" cy="10" r="6" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M15 15l5 5M7 10h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "undo":        '<path d="M7 7L3 11l4 4M3 11h11a6 6 0 010 12h-2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "redo":        '<path d="M17 7l4 4-4 4M21 11H10a6 6 0 000 12h2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "delete":      '<path d="M6 7h12M9 7V5h6v2M7 7l1 13h8l1-13" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
    "fill":        '<path d="M4 4h11l5 5v11H4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M7 13l2.5 2.5L15 10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "align":        '<path d="M4 3v18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><rect x="7" y="6" width="12" height="4" rx="1" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><rect x="7" y="14" width="7" height="4" rx="1" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "flip":         '<path d="M12 3v18" stroke="currentColor" stroke-width="1.4" stroke-dasharray="2 2"/><path d="M9 6L3 18h6V6zM15 6l6 12h-6V6z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "group":        '<rect x="3" y="3" width="18" height="18" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.3" stroke-dasharray="3 2"/><rect x="6" y="6" width="7" height="7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><rect x="11" y="11" width="7" height="7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "ungroup":      '<rect x="4" y="4" width="7" height="7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><rect x="13" y="13" width="7" height="7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "unlock":       '<rect x="5" y="11" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 11V8a4 4 0 017.5-2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "hide":         '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 4l16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "show":         '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "pause": '<path d="M9 5v14M15 5v14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "voice": '<path d="M12 3a3 3 0 013 3v5a3 3 0 01-6 0V6a3 3 0 013-3zM6 11a6 6 0 0012 0M12 17v4M9 21h6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "perimeter": '<path d="M4 18l3-12 9 2 4 9z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="3 2"/><circle cx="4" cy="18" r="1.4" fill="currentColor"/><circle cx="7" cy="6" r="1.4" fill="currentColor"/><circle cx="16" cy="8" r="1.4" fill="currentColor"/><circle cx="20" cy="17" r="1.4" fill="currentColor"/>',
    "area": '<path d="M4 18l3-12 9 2 4 9z" fill="currentColor" fill-opacity="0.25" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
    "scale": '<path d="M3 16h18M3 13v6M9 15v2M15 15v2M21 13v6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M7 6h10M14 3l3 3-3 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "page1": '<rect x="7" y="3" width="10" height="18" rx="1" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "page2": '<rect x="2.5" y="5" width="9" height="14" rx="1" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><rect x="12.5" y="5" width="9" height="14" rx="1" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "cover": '<rect x="12.5" y="5" width="9" height="14" rx="1" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><rect x="2.5" y="5" width="9" height="14" rx="1" stroke="currentColor" stroke-width="1.2" fill="none" stroke-dasharray="2 2"/>',
    "exit": '<path d="M14 4H6a1 1 0 00-1 1v14a1 1 0 001 1h8M10 12h10M17 9l3 3-3 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "heart": '<path d="M12 20s-7-4.4-9-9a4.6 4.6 0 018.2-4.2L12 8l.8-1.2A4.6 4.6 0 0121 11c-2 4.6-9 9-9 9z" fill="#e53935" fill-opacity="0.85" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
    "speaker":      '<path d="M4 9h4l5-4v14l-5-4H4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M16 9a4 4 0 010 6M18.5 6.5a7.5 7.5 0 010 11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    "brush":        '<path d="M14 4l6 6-7 7-6-6zM7 11l-3 9 9-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "table":       '<rect x="4" y="5" width="16" height="14" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4 10h16M4 14.5h16M10 5v14" stroke="currentColor" stroke-width="1.4"/>',
    "link":        '<path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1.2 1.2M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1.2-1.2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    "duplicate":   '<rect x="8" y="8" width="12" height="12" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4 16V5a1 1 0 011-1h11" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "close":       '<path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    "goto":        '<path d="M12 2v14M6 10l6 6 6-6" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    "help":        '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M9.5 9a2.5 2.5 0 114 2.2c-.7.5-1.5 1-1.5 2.3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="12" cy="17" r="0.9" fill="currentColor"/>',
    "cut":         '<circle cx="6" cy="6" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="6" cy="18" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8.5 7.5L20 19M20 5L8.5 16.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    "paste":       '<rect x="6" y="5" width="12" height="16" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.6"/><rect x="9" y="3" width="6" height="3" rx="1" fill="none" stroke="currentColor" stroke-width="1.4"/>',
    "format":      '<circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12 3v3M12 18v3M4.2 7l2.6 1.5M17.2 15.5l2.6 1.5M4.2 17l2.6-1.5M17.2 8.5l2.6-1.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
    "order":       '<rect x="7" y="3" width="12" height="12" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"/><rect x="3" y="9" width="12" height="12" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"/>',
    "select_group":'<path d="M4 4h16v16H4z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-dasharray="3,2"/><circle cx="4" cy="4" r="1.4" fill="currentColor"/><circle cx="20" cy="4" r="1.4" fill="currentColor"/><circle cx="4" cy="20" r="1.4" fill="currentColor"/><circle cx="20" cy="20" r="1.4" fill="currentColor"/>',

    # Miniaturas
    "rotate_cw":   '<path d="M20 8a8 8 0 10.6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M20 3v6h-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
    "rotate_ccw":  '<path d="M4 8a8 8 0 11-.6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M4 3v6h6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
    "range_select":'<rect x="3" y="6" width="7" height="12" rx="1" fill="none" stroke="currentColor" stroke-width="1.5"/><rect x="14" y="6" width="7" height="12" rx="1" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M10 12h4" stroke="currentColor" stroke-width="1.5"/>',
    "select_all":  '<path d="M4 4h6M4 4v6M20 4h-6M20 4v6M4 20h6M4 20v-6M20 20h-6M20 20v-6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',

    # Operaciones entre PDFs
    "merge":       '<path d="M6 4v9a3 3 0 003 3h6M6 4L3 7m3-3l3 3M18 20v-9a3 3 0 00-3-3H9M18 20l3-3m-3 3l-3-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "swap":        '<path d="M4 8h13l-3-3m3 3l-3 3M20 16H7l3 3m-3-3l3-3" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
    "copy":        '<rect x="9" y="9" width="11" height="11" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M5 15V6a1 1 0 011-1h9" fill="none" stroke="currentColor" stroke-width="1.5"/>',
    "ops":         '<path d="M7 12h10M12 7v10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.4"/>',
    "pdf_doc":     '<path d="M6 3h9l5 5v13H6V3z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M15 3v5h5" fill="none" stroke="currentColor" stroke-width="1.6"/>',

    # OCR
    "ocr_panel":   '<circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M16 16l5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M8 11h6M8 8.5h6M8 13.5h4" stroke="currentColor" stroke-width="1.1"/>',
    "warning":     '<path d="M12 3l10 18H2L12 3z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 10v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="12" cy="17" r="0.9" fill="currentColor"/>',

    # App / empty state
    "app_logo":    '<rect x="4" y="3" width="16" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',

    # Genérico: círculo sólido (swatch de color)
    "dot":         '<circle cx="12" cy="12" r="9" fill="currentColor"/>',
}

_cache: dict = {}


def _tint_pixmap(svg_inner: str, color: str, size: int) -> QPixmap:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{svg_inner}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pm.rect(), QColor(color))
    painter.end()
    return pm


def get_icon(name: str, color: str = None, size: int = 20) -> QIcon:
    """Icono estático (QIcon) cacheado, recoloreado según el tema."""
    color = color or C["icon"]
    key = (name, color, size)
    if key in _cache:
        return _cache[key]
    svg_inner = _SVG_PATHS.get(name, _SVG_PATHS["help"])
    icon = QIcon(_tint_pixmap(svg_inner, color, size))
    _cache[key] = icon
    return icon


def get_toggle_icon(name: str, size: int = 20) -> QIcon:
    """Icono con estado Off/On: oscuro normal, claro cuando el botón está checked."""
    key = ("__toggle__", name, size)
    if key in _cache:
        return _cache[key]
    svg_inner = _SVG_PATHS.get(name, _SVG_PATHS["help"])
    icon = QIcon()
    icon.addPixmap(_tint_pixmap(svg_inner, C["icon"], size), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_tint_pixmap(svg_inner, C["icon_active"], size), QIcon.Mode.Normal, QIcon.State.On)
    _cache[key] = icon
    return icon
