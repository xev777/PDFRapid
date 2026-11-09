# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Leer códigos QR de una página (p. ej. el sello de una firma electrónica) con zxing-cpp, sin conexión.
zxing-cpp respeta tildes y ñ (UTF-8); OpenCV, que solo se usa si zxing-cpp faltara, no lee esos QR."""
import pymupdf

DPI = 250                                  # suficiente para QR pequeños con mucho texto


def _gray(page, dpi):
    import numpy as np
    k = dpi / 72
    pix = page.get_pixmap(matrix=pymupdf.Matrix(k, k), colorspace=pymupdf.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width], k


def find_qr(page, dpi: int = DPI) -> list:
    """Códigos QR de la página: [(Rect en puntos de la página visible, texto)]. Lista vacía si no hay."""
    img, k = _gray(page, dpi)
    try:
        import zxingcpp
    except ImportError:
        return _find_qr_cv(img, k)
    out = []
    for r in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode):
        if not r.valid or not r.text: continue
        p = r.position
        xs = [q.x for q in (p.top_left, p.top_right, p.bottom_right, p.bottom_left)]
        ys = [q.y for q in (p.top_left, p.top_right, p.bottom_right, p.bottom_left)]
        out.append((pymupdf.Rect(min(xs) / k, min(ys) / k, max(xs) / k, max(ys) / k), r.text))
    return out


def _find_qr_cv(img, k) -> list:
    try:
        import cv2
        ok, texts, pts, _ = cv2.QRCodeDetector().detectAndDecodeMulti(img)
    except Exception:
        return []
    if not ok or pts is None: return []
    return [(pymupdf.Rect(q[:, 0].min() / k, q[:, 1].min() / k, q[:, 0].max() / k, q[:, 1].max() / k), t)
            for t, q in zip(texts, pts) if t]
