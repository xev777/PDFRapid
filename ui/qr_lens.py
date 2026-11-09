# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Lupa QR: ventana flotante que sigue al ratón con la zona ampliada y, si hay un código QR debajo
(p. ej. el sello de una firma electrónica), su contenido. Un clic copia el texto."""
import pymupdf
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout
from core.i18n import T
from core.qr_read import find_qr
from ui.styles import C

SIDE = 220                    # lado de la vista ampliada (px)
MAG = 2.5                     # aumento respecto a la vista actual

_cache = {}                   # (id(doc), página, rotación) → [(Rect visible, texto)]
_lens = None


def qr_codes(doc, page_num) -> list:
    pg = doc[page_num]
    key = (id(doc), page_num, pg.rotation)
    if key not in _cache:
        if len(_cache) > 64: _cache.clear()
        _cache[key] = find_qr(pg)
    return _cache[key]


def qr_at(canvas, pos):
    """(Rect, texto) del QR bajo `pos` (px del lienzo) o None."""
    k = canvas._gk(); x, y = pos.x() / k, pos.y() / k
    for r, t in qr_codes(canvas.doc, canvas.page_num):
        if r.x0 - 4 <= x <= r.x1 + 4 and r.y0 - 4 <= y <= r.y1 + 4:
            return r, t
    return None


class QrLens(QFrame):
    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(f"QrLens{{background:{C['bg']};border:1px solid {C['accent']};border-radius:6px;}}")
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 6, 6, 6); lay.setSpacing(4)
        self.view = QLabel(); self.view.setFixedSize(SIDE, SIDE); lay.addWidget(self.view)
        self.info = QLabel(); self.info.setWordWrap(True); self.info.setFixedWidth(SIDE)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction); lay.addWidget(self.info)
        self.text = ""

    def update_for(self, canvas, pos, gpos):
        k = canvas._gk(); half = SIDE / MAG / 2 / k                     # medio lado en puntos de la página
        x, y = pos.x() / k, pos.y() / k
        clip = pymupdf.Rect(x - half, y - half, x + half, y + half)
        z = k * MAG
        pg = canvas.doc[canvas.page_num]
        pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=clip, alpha=False)   # clip en coordenadas visibles
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        full = QPixmap(SIDE, SIDE); full.fill(Qt.GlobalColor.white)
        p = QPainter(full)                                    # cerca del borde la zona queda en su sitio, con blanco
        p.drawImage(QPointF((max(clip.x0, 0) - clip.x0) * z, (max(clip.y0, 0) - clip.y0) * z), img)
        p.end()
        self.view.setPixmap(full)
        hit = qr_at(canvas, pos)
        self.text = hit[1] if hit else ""
        self.info.setText(f"<b>{T('Código QR')}</b><br>{_html(self.text)}<br><span style='color:{C['muted']}'>"
                          f"{T('Clic: copiar el texto')}</span>" if hit else
                          f"<span style='color:{C['muted']}'>{T('Pasa la lupa sobre un código QR para leerlo.')}</span>")
        self.adjustSize()
        self._place(gpos)
        if not self.isVisible(): self.show()

    def _place(self, gpos):
        scr = QGuiApplication.screenAt(gpos) or QGuiApplication.primaryScreen()
        a = scr.availableGeometry(); w, h = self.width(), self.height()
        x = gpos.x() + 24 if gpos.x() + 24 + w <= a.right() else gpos.x() - 24 - w
        y = gpos.y() + 24 if gpos.y() + 24 + h <= a.bottom() else max(a.top(), gpos.y() - 24 - h)
        self.move(QPoint(x, y))


def _html(t):
    import html
    return html.escape(t).replace("\n", "<br>")


def lens() -> QrLens:
    global _lens
    if _lens is None: _lens = QrLens()
    return _lens


def move(canvas, pos, gpos):
    lens().update_for(canvas, pos, gpos)


def hide():
    if _lens is not None and _lens.isVisible(): _lens.hide()


def copy(canvas, pos) -> str:
    """Copia el texto del QR bajo el ratón; devuelve el texto copiado ('' si no había QR)."""
    hit = qr_at(canvas, pos)
    if hit: QGuiApplication.clipboard().setText(hit[1])
    return hit[1] if hit else ""
