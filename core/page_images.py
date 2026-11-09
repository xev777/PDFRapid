# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Imágenes que ya trae el PDF (no las añadidas con PDFRapid): encontrarlas, guardarlas, reemplazarlas, eliminarlas
o convertirlas en un objeto que se pueda mover y cambiar de tamaño."""
import pymupdf


def image_at(page, point) -> dict:
    """La imagen más pequeña que contiene `point` (puntos de la página sin girar), o None.
    Devuelve {xref, bbox, rotated}."""
    hits = []
    page._image_info = None                       # PyMuPDF guarda en caché lo de antes de un cambio
    # primero sin xrefs (no decodifica nada): en un escaneado, averiguar el xref decodifica la imagen entera
    if not any(pymupdf.Rect(i["bbox"]).contains(point) for i in page.get_image_info()): return None
    page._image_info = None
    for info in page.get_image_info(xrefs=True):
        r = pymupdf.Rect(info["bbox"])
        if info.get("xref") and not _deleted(info) and r.contains(point):
            a, b, c, d = info["transform"][:4]
            hits.append({"xref": info["xref"], "bbox": r, "rotated": abs(b) > 1e-3 or abs(c) > 1e-3 or a < 0 or d < 0})
    return min(hits, key=lambda h: h["bbox"].get_area()) if hits else None


def _deleted(info) -> bool:
    """PyMuPDF «elimina» una imagen cambiándola por un píxel transparente: esa ya no cuenta."""
    return info.get("width", 2) <= 1 and info.get("height", 2) <= 1


def uses(doc, xref) -> int:
    """En cuántos lugares del documento se dibuja la imagen (un logotipo puede repetirse en cada página)."""
    return sum(1 for page in doc for i in page.get_image_info(xrefs=True) if i.get("xref") == xref)


def pixmap(doc, xref) -> pymupdf.Pixmap:
    """La imagen en RGB(A), con su transparencia (máscara) si la tiene."""
    pix = pymupdf.Pixmap(doc, xref)
    smask = doc.xref_get_key(xref, "SMask")
    if smask[0] == "xref":
        try:
            pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, int(smask[1].split()[0])))
        except Exception:
            pass
    if pix.colorspace and pix.colorspace.n not in (1, 3):           # CMYK u otros → RGB
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return pix


def png(doc, xref) -> bytes:
    return pixmap(doc, xref).tobytes("png")


def save(doc, xref, path: str):
    """Guarda la imagen: en su formato original si es JPEG y el archivo pide .jpg; si no, como PNG."""
    if path.lower().endswith((".jpg", ".jpeg")):
        info = doc.extract_image(xref)
        if info and info.get("ext") in ("jpg", "jpeg") and doc.xref_get_key(xref, "SMask")[0] != "xref":
            with open(path, "wb") as f: f.write(info["image"])
            return
        pixmap(doc, xref).save(path, jpg_quality=92)
        return
    pixmap(doc, xref).save(path)


def _swap(page, xref, **kw):
    """`page.replace_image` deja la imagen nueva también como recurso aparte, con el mismo contenido que la
    reemplazada; así PyMuPDF ya no sabe cuál es cuál. Se quita ese recurso sobrante."""
    doc = page.parent
    before = {i[0] for i in page.get_images()}
    page.replace_image(xref, **kw)
    for item in page.get_images(full=True):
        if item[0] not in before and item[0] != xref and item[7]:
            doc.xref_set_key(page.xref, "Resources/XObject/" + item[7], "null")
    page._image_info = None


def delete(page, xref):
    """Quita la imagen de todos los lugares donde se dibuja (queda un píxel transparente en su lugar)."""
    pix = pymupdf.Pixmap(pymupdf.csGRAY, (0, 0, 1, 1), 1)
    pix.clear_with()
    _swap(page, xref, pixmap=pix)


def replace(page, xref, path: str):
    """Pone otra imagen en todos los lugares donde se dibuja esta (ocupa el mismo espacio)."""
    _swap(page, xref, filename=path)
