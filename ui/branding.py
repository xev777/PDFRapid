# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Identidad visual de PDFRapid: logotipo (SVG propio, sin recursos externos) y pantalla de inicio."""
from core.i18n import T, Tf
import time
from PyQt6.QtCore import QByteArray, QRectF, Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QLinearGradient, QPen, QPainterPath, QBrush
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QSplashScreen
from core.constants import APP_NAME, APP_VERSION, APP_TAGLINE, APP_AUTHOR
from ui.styles import C

LOGO_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#2563eb"/><stop offset="1" stop-color="#14b8a6"/></linearGradient></defs>
<rect x="2" y="2" width="60" height="60" rx="14" fill="url(#g)"/>
<path d="M20 11h17l10 10v31a3 3 0 0 1-3 3H20a3 3 0 0 1-3-3V14a3 3 0 0 1 3-3z" fill="#ffffff"/>
<path d="M37 11v10h10z" fill="#bfdbfe"/>
<path d="M23 24h11M23 30h17" stroke="#93c5fd" stroke-width="3" stroke-linecap="round"/>
<path d="M34 34l-8 11h6l-2 9 9-12h-6l3-8z" fill="#f59e0b" stroke="#ffffff" stroke-width="1" stroke-linejoin="round"/>
</svg>'''


def logo_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    QSvgRenderer(QByteArray(LOGO_SVG.encode())).render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def logo_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(s))
    return icon


LOGO_RECT = QRectF(44, 70, 112, 112)
BAR_RECT = QRectF(186, 196, 330, 4)


class AnimatedSplash(QSplashScreen):
    """Pantalla de inicio animada: aparece con un fundido, un brillo recorre el logotipo y una barra de progreso
    se desliza mientras carga; al terminar se desvanece. Se anima mientras Qt procesa eventos (antes y después de
    construir la ventana principal, que es lo que más tarda)."""
    FADE_IN, FADE_OUT = 0.35, 0.25

    def __init__(self, pm):
        super().__init__(pm, Qt.WindowType.WindowStaysOnTopHint)
        self._t0 = time.monotonic(); self._closing = None
        self.setWindowOpacity(0.0)
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(16)

    def _tick(self):
        t = time.monotonic() - self._t0
        if self._closing is None:
            self.setWindowOpacity(min(1.0, t / self.FADE_IN))
        else:
            k = (time.monotonic() - self._closing[0]) / self.FADE_OUT
            if k >= 1:
                self._timer.stop(); self.close(); return
            self.setWindowOpacity(1.0 - k)
        self.repaint()

    def drawContents(self, p):
        t = time.monotonic() - self._t0
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # brillo que cruza el logotipo cada 1,8 s
        ph = (t % 1.8) / 1.1
        if ph <= 1:
            clip = QPainterPath(); clip.addRoundedRect(LOGO_RECT.adjusted(3, 3, -3, -3), 24, 24)
            p.save(); p.setClipPath(clip)
            x = LOGO_RECT.left() - 40 + ph * (LOGO_RECT.width() + 80)       # franja diagonal estrecha que cruza
            p.translate(x, LOGO_RECT.center().y()); p.rotate(22)
            band = QRectF(-16, -LOGO_RECT.height(), 32, LOGO_RECT.height() * 2)
            g = QLinearGradient(band.left(), 0, band.right(), 0)
            g.setColorAt(0, QColor(255, 255, 255, 0)); g.setColorAt(0.5, QColor(255, 255, 255, 190))
            g.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillRect(band, QBrush(g)); p.restore()
        # barra de progreso indeterminada
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(C['border']))
        p.drawRoundedRect(BAR_RECT, 2, 2)
        seg = BAR_RECT.width() * 0.32
        x = BAR_RECT.left() - seg + ((t * 0.75) % 1.0) * (BAR_RECT.width() + seg)
        r = QRectF(max(x, BAR_RECT.left()), BAR_RECT.top(), min(x + seg, BAR_RECT.right()) - max(x, BAR_RECT.left()),
                   BAR_RECT.height())
        if r.width() > 0:
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            g.setColorAt(0, QColor("#2563eb")); g.setColorAt(1, QColor("#14b8a6"))
            p.setBrush(g); p.drawRoundedRect(r, 2, 2)
        if self.message():                             # mensaje de progreso bajo la barra
            p.setPen(QColor(C['muted'])); p.setFont(self.font())
            p.drawText(QRectF(BAR_RECT.left(), BAR_RECT.bottom() + 6, BAR_RECT.width(), 18),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.message().strip())

    def finish(self, window):
        """Muestra la ventana y se desvanece."""
        window.show(); window.raise_()
        self._closing = (time.monotonic(),)


def splash() -> QSplashScreen:
    """Pantalla de inicio con los colores del tema activo; `showMessage` escribe el progreso abajo."""
    W, H = 560, 300
    pm = QPixmap(W, H)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    g = QLinearGradient(0, 0, W, H)
    g.setColorAt(0, QColor(C['panel']))
    g.setColorAt(1, QColor(C['accent_soft']))
    p.fillRect(0, 0, W, H, g)
    p.fillRect(0, 0, W, 5, QColor(C['accent']))                      # franja superior
    p.drawPixmap(44, 70, logo_pixmap(112))
    pdf, name = APP_NAME[:3], APP_NAME[3:]                         # "PDF" + "Rapid"
    f = QFont("Segoe UI", 34, QFont.Weight.Bold)
    p.setFont(f)
    p.setPen(QColor(C['accent']))
    p.drawText(184, 120, pdf)
    p.setPen(QColor(C['text']))
    p.drawText(184 + p.fontMetrics().horizontalAdvance(pdf), 120, name)
    p.setFont(QFont("Segoe UI", 12))
    p.setPen(QColor(C['muted']))
    p.drawText(186, 150, T(APP_TAGLINE))
    p.setFont(QFont("Segoe UI", 9))
    p.drawText(186, 174, Tf("Versión {0}", APP_VERSION))
    p.drawText(44, H - 20, Tf("© 2026 {0} · Software libre (AGPL-3.0)", APP_AUTHOR))
    p.setPen(QPen(QColor(C['border']), 1))
    p.drawRect(0, 0, W - 1, H - 1)
    p.end()
    s = AnimatedSplash(pm)
    s.setFont(QFont("Segoe UI", 9))
    return s


def message(s: QSplashScreen, text: str):
    s.showMessage(text + "      \n", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight, QColor(C["muted"]))   # margen
