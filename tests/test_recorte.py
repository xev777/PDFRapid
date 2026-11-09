# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Recorte de imágenes insertadas."""
import base64
from PyQt6.QtCore import QRect, QRectF, QBuffer, QIODevice
from PyQt6.QtGui import QImage, QColor
from models.annotation import Ann
from ui.canvas_edit import apply_crop


def _img(w=200, h=100):
    img = QImage(w, h, QImage.Format.Format_RGB32); img.fill(QColor("red"))
    for x in range(w // 2, w):
        for y in range(h): img.setPixelColor(x, y, QColor("blue"))
    buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly); img.save(buf, "PNG")
    return img, base64.b64encode(bytes(buf.data())).decode()


def test_recorte_mitad_derecha(qapp):
    img, b64 = _img()
    a = Ann("image", x1=100, y1=50, x2=300, y2=150, image_data=b64)
    apply_crop(a, img, QRect(100, 0, 100, 100))
    assert a.brect() == QRectF(200, 50, 100, 100)          # queda donde estaba, misma escala
    out = QImage.fromData(base64.b64decode(a.image_data))
    assert out.size().width() == 100 and out.pixelColor(50, 50).blue() > 200


def test_recorte_imagen_girada(qapp):
    img, b64 = _img()
    a = Ann("image", x1=100, y1=50, x2=300, y2=150, image_data=b64); a.rotation = 90
    apply_crop(a, img, QRect(100, 0, 100, 100))
    c = a.brect().center()                                  # girada 90°: la mitad derecha queda abajo
    assert abs(c.x() - 200) < 0.01 and abs(c.y() - 150) < 0.01


def test_dialogo_recorte(qapp):
    from dialogs.crop_dialog import CropDialog
    img, _ = _img()
    d = CropDialog(img); d.resize(500, 400)
    assert d.crop_rect() == img.rect()
    d.area.crop = QRectF(10.4, 5, 50, 40.6); d._update_info(); d.grab()
    r = d.crop_rect(); assert img.rect().contains(r) and r.width() >= 50
