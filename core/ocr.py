# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""OCR con RapidOCR (ONNX, modelos incluidos, sin conexión) y capa de texto buscable."""
import numpy as np
import pymupdf

ZOOM = 2.0            # resolución de render para el OCR (144 ppp)
_engine = None


def _get_engine():
    """El modelo tarda en cargar: se crea una sola vez."""
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR
        _engine = RapidOCR()
    return _engine


def ocr_page(page, clip=None) -> list:
    """Reconoce el texto de una página (o de una región `clip`).
    Devuelve [(Rect en puntos de la página visible, texto)] por línea, en orden de lectura."""
    pix = page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), clip=clip, alpha=False)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    res = _get_engine()(img)
    if res.boxes is None:
        return []
    ox, oy = (clip.x0, clip.y0) if clip else (0, 0)
    out = []
    for box, txt in zip(res.boxes, res.txts):
        xs, ys = box[:, 0] / ZOOM + ox, box[:, 1] / ZOOM + oy
        out.append((pymupdf.Rect(xs.min(), ys.min(), xs.max(), ys.max()), txt))
    return out


def add_text_layer(page, lines):
    """Escribe el texto reconocido como texto invisible sobre su posición,
    para que el PDF se pueda buscar, seleccionar y copiar."""
    m = page.derotation_matrix
    vertical = page.rotation in (90, 270)
    for rect, txt in lines:
        if not txt.strip() or rect.height <= 0:
            continue
        fs = rect.height * 0.8
        tl = pymupdf.get_text_length(txt, fontname="helv", fontsize=fs)
        k = rect.width / tl if tl else 1
        org = pymupdf.Point(rect.x0, rect.y1 - rect.height * 0.2) * m
        page.insert_text(org, txt, fontname="helv", fontsize=fs, render_mode=3,
                         rotate=page.rotation,
                         morph=(org, pymupdf.Matrix(1, k) if vertical else pymupdf.Matrix(k, 1)))


def searchable_pdf(doc, results: dict) -> bytes:
    """Copia de las páginas de `results` ({página: líneas}) con su capa de texto."""
    out = pymupdf.open()
    for pi in sorted(results):
        out.insert_pdf(doc, from_page=pi, to_page=pi)
        add_text_layer(out[-1], results[pi])
    data = out.tobytes(garbage=3, deflate=True)
    out.close()
    return data
