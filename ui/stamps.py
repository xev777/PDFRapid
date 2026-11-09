# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Sellos tipo Acrobat («Aprobado», «Confidencial»…): imagen generada con nombre y fecha."""
import base64
from datetime import datetime
from PyQt6.QtCore import Qt, QBuffer, QIODevice, QRectF
from PyQt6.QtGui import QImage, QPainter, QColor, QFont, QPen

STAMPS = [  # (texto, color)
    ("APROBADO", "#1e8e3e"), ("REVISADO", "#1565d8"), ("RECIBIDO", "#1565d8"), ("PAGADO", "#1e8e3e"),
    ("CONFIDENCIAL", "#c62828"), ("RECHAZADO", "#c62828"), ("BORRADOR", "#6b7280"), ("COPIA", "#6b7280"),
]


def stamp_b64(text: str, color: str, signer: str = None) -> str:
    """PNG (base64) del sello con el usuario y la fecha de hoy, como los sellos dinámicos de Acrobat."""
    if signer is None:
        from core.settings import AppSettings
        signer = AppSettings().get_author()
    sub = " · ".join(x for x in (signer, datetime.now().strftime("%d/%m/%Y %H:%M")) if x)
    W, H = 600, 190
    img = QImage(W, H, QImage.Format.Format_ARGB32); img.fill(Qt.GlobalColor.transparent)
    c = QColor(color)
    p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setPen(QPen(c, 9)); fill = QColor(c); fill.setAlpha(22); p.setBrush(fill)
    p.drawRoundedRect(QRectF(8, 8, W - 16, H - 16), 26, 26)
    f = QFont("Segoe UI", 64, QFont.Weight.Black); p.setFont(f)
    while p.fontMetrics().horizontalAdvance(text) > W - 70 and f.pointSize() > 20:
        f.setPointSize(f.pointSize() - 2); p.setFont(f)
    p.setPen(c)
    p.drawText(QRectF(0, 18, W, 110), Qt.AlignmentFlag.AlignCenter, text)
    p.setFont(QFont("Segoe UI", 22, QFont.Weight.DemiBold))
    p.drawText(QRectF(0, 122, W, 50), Qt.AlignmentFlag.AlignCenter, sub)
    p.end()
    buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly); img.save(buf, "PNG")
    return base64.b64encode(bytes(buf.data())).decode()
