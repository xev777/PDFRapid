# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Persistencia de anotaciones de Pdfgm como anotaciones PDF nativas.

Mientras se edita, las anotaciones de Pdfgm viven solo en memoria (capa de
dibujo del visor) y nunca se escriben en el documento abierto. Al guardar se
genera una copia del documento con una anotación nativa por objeto (visible y
editable en cualquier lector) y, dentro de cada anotación, una clave privada
/PdfgmData que apunta a un stream con los datos completos del objeto (JSON).
Así no hay límite de tamaño y, si otro programa borra la anotación, sus datos
desaparecen con ella.

Al abrir, `extract` lee esos datos, quita las anotaciones de Pdfgm del
documento en memoria (para que no se dibujen dos veces) y deja intactas las
anotaciones ajenas. Las coordenadas se guardan en puntos PDF sin rotación.
"""
import base64
import json
import math
import pymupdf

KEY = "PdfgmData"
KEY_GUIDES = "PdfgmGuides"  # en cada página: guías de la regla {"v": [x], "h": [y]} en puntos visibles
KEY_PART = "PdfgmPart"     # anotación auxiliar de un objeto (p. ej. el borde de una caja de texto)
_DASHES = {"dashed": [4, 3], "dotted": [1, 2]}
_LE_ARROW = pymupdf.PDF_ANNOT_LE_CLOSED_ARROW
_LE_NONE = pymupdf.PDF_ANNOT_LE_NONE


# ── lectura ──────────────────────────────────────────────────────────────
def _data_of(doc, annot):
    kind, val = doc.xref_get_key(annot.xref, KEY)
    if kind != "xref":
        return None
    try:
        return json.loads(doc.xref_stream(int(val.split()[0])).decode("utf-8"))
    except Exception:
        return None


def _is_legacy_keywords(kw: str) -> bool:
    """Formato de Pdfgm ≤ v10: JSON {"0": "[...]"} en metadata.keywords."""
    try:
        d = json.loads(kw)
    except Exception:
        return False
    return isinstance(d, dict) and all(k.isdigit() for k in d)


def extract(doc) -> dict:
    """Devuelve {página: [dict de Ann]} y quita del `doc` en memoria las
    anotaciones de Pdfgm. Las anotaciones ajenas no se tocan."""
    pages = {}
    for pno in range(len(doc)):
        page = doc[pno]
        own, parts = [], []
        for annot in page.annots():
            d = _data_of(doc, annot)
            if d is not None:
                own.append((annot.xref, d))
            elif doc.xref_get_key(annot.xref, KEY_PART)[0] != "null":
                parts.append(annot.xref)                  # se regenera al guardar: solo quitarla
        for xref in parts:
            page.delete_annot(page.load_annot(xref))
        for xref, d in own:
            pages.setdefault(pno, []).append(d)
            page.delete_annot(page.load_annot(xref))
    meta = doc.metadata or {}
    if _is_legacy_keywords(meta.get("keywords", "")):
        meta["keywords"] = ""
        doc.set_metadata(meta)
    return pages


def _guide_dict(g) -> dict:
    return {"v": [float(x) for x in g.get("v", [])], "h": [float(y) for y in g.get("h", [])]}


def read_guides(doc) -> dict:
    """Guías guardadas por PDFRapid ({página: {"v": [...], "h": [...]}}) y las quita del `doc` en memoria.
    Cada página guarda las suyas (así viajan con la página al reordenar o borrar páginas); también se leen
    las del formato anterior, todas juntas en el catálogo."""
    out = {}
    try:
        cat = doc.pdf_catalog()
        t, v = doc.xref_get_key(cat, KEY_GUIDES)
        if t == "xref":                                   # formato anterior (2026-10-26)
            data = json.loads(doc.xref_stream(int(v.split()[0])).decode("utf-8"))
            out = {int(p): _guide_dict(g) for p, g in data.items() if 0 <= int(p) < len(doc)}
            doc.xref_set_key(cat, KEY_GUIDES, "null")
        for pno in range(len(doc)):
            px = doc[pno].xref
            t, v = doc.xref_get_key(px, KEY_GUIDES)
            if t == "xref":
                out[pno] = _guide_dict(json.loads(doc.xref_stream(int(v.split()[0])).decode("utf-8")))
                doc.xref_set_key(px, KEY_GUIDES, "null")
    except Exception:
        pass
    return out


def _write_guides(out, guides: dict):
    for p, d in (guides or {}).items():
        if not (0 <= p < len(out) and (d["v"] or d["h"])): continue
        xref = out.get_new_xref()
        out.update_object(xref, "<<>>")
        out.update_stream(xref, json.dumps(d).encode("utf-8"))
        out.xref_set_key(out[p].xref, KEY_GUIDES, f"{xref} 0 R")


# ── escritura ────────────────────────────────────────────────────────────
def _rgb(hx):
    if not hx:
        return None
    hx = hx.lstrip("#")
    if len(hx) == 8:          # #aarrggbb (QColor.name con alfa)
        hx = hx[2:]
    try:
        return tuple(int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None


def _png(img) -> bytes:
    from PyQt6.QtCore import QBuffer, QIODevice
    buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly); img.save(buf, "PNG")
    return bytes(buf.data())


def _rotated_stamp(page, r, img, rot):
    """Sello con la imagen girada `rot` grados (como en pantalla) dentro de la caja girada de `r`."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTransform, QImage
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    out = img.transformed(QTransform().rotate(rot), Qt.TransformationMode.SmoothTransformation)
    pts = _rotated([r.tl, r.tr, r.br, r.bl], rot, (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
    box = pymupdf.Rect(min(p.x for p in pts), min(p.y for p in pts), max(p.x for p in pts), max(p.y for p in pts))
    return page.add_stamp_annot(box, stamp=_png(out))


def _text_image(a, r, box):
    """El texto (o la caja de texto) dibujado como imagen nítida, para exportarlo girado en cualquier ángulo."""
    from PyQt6.QtCore import Qt, QRectF
    from PyQt6.QtGui import QImage, QPainter, QColor, QFont, QPen
    k = 4                                            # 4 px por punto PDF: nítido al imprimir
    img = QImage(max(1, int(r.width * k)), max(1, int(r.height * k)), QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setOpacity(a.get("opacity", 1.0))
    if box:
        if a.get("box_bg"): p.fillRect(img.rect(), QColor(a["box_bg"]))
        if a.get("box_bw"):
            bw = a["box_bw"] * k
            p.setPen(QPen(QColor(a.get("box_border") or "#000000"), bw)); p.drawRect(QRectF(bw / 2, bw / 2, img.width() - bw, img.height() - bw))
    f = QFont(a.get("font_name") or "Arial"); f.setPixelSize(int(max(4, a.get("font_size", 12)) * k))
    f.setBold(bool(a.get("font_bold"))); f.setItalic(bool(a.get("font_italic"))); f.setUnderline(bool(a.get("font_underline")))
    p.setFont(f); p.setPen(QColor(a.get("text_color") or "#000000"))
    align = {"center": Qt.AlignmentFlag.AlignHCenter, "right": Qt.AlignmentFlag.AlignRight}.get(a.get("text_align"), Qt.AlignmentFlag.AlignLeft)
    flags = Qt.TextFlag.TextWordWrap.value | align.value | Qt.AlignmentFlag.AlignTop.value
    pad = 2 * k
    p.drawText(QRectF(pad, pad, img.width() - 2 * pad, img.height() - 2 * pad), flags, a.get("text", ""))
    p.end()
    return img


def _rotated(points, rot, cx, cy):
    if not rot:
        return points
    t = math.radians(rot)
    c, s = math.cos(t), math.sin(t)
    return [pymupdf.Point(cx + (p.x - cx) * c - (p.y - cy) * s,
                       cy + (p.x - cx) * s + (p.y - cy) * c) for p in points]


def _rounded_rect(r, rad, steps=6):
    rad = max(0.0, min(rad, r.width / 2, r.height / 2))
    pts = []
    corners = [(r.x1 - rad, r.y0 + rad, -90), (r.x1 - rad, r.y1 - rad, 0),
               (r.x0 + rad, r.y1 - rad, 90), (r.x0 + rad, r.y0 + rad, 180)]
    for cx, cy, start in corners:
        for i in range(steps + 1):
            t = math.radians(start + 90 * i / steps)
            pts.append(pymupdf.Point(cx + rad * math.cos(t), cy + rad * math.sin(t)))
    return pts


def _ellipse(r, n=48):
    cx, cy, rx, ry = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2, r.width / 2, r.height / 2
    return [pymupdf.Point(cx + rx * math.cos(2 * math.pi * i / n),
                       cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _arrow_shape(a):
    x1, y1, x2, y2 = a["x1"], a["y1"], a["x2"], a["y2"]
    length = max(math.hypot(x2 - x1, y2 - y1), 1)
    ang = math.atan2(y2 - y1, x2 - x1)
    sw = max(abs(y2 - y1) * 0.3, 4)
    hw, hl = sw * 2.5, min(length * 0.35, sw * 3)
    local = [(0, -sw / 2), (length - hl, -sw / 2), (length - hl, -hw / 2), (length, 0),
             (length - hl, hw / 2), (length - hl, sw / 2), (0, sw / 2)]
    c, s = math.cos(ang), math.sin(ang)
    return [pymupdf.Point(x1 + px * c - py * s, y1 + px * s + py * c) for px, py in local]


def _add_native(page, a):
    k = a.get("kind")
    x1, y1, x2, y2 = a["x1"], a["y1"], a["x2"], a["y2"]
    r = pymupdf.Rect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    rot = a.get("rotation", 0) or 0
    stroke, fill = _rgb(a.get("stroke")), _rgb(a.get("fill"))
    op = a.get("opacity", 1.0)
    width = a.get("stroke_width", 1.5)
    dashes = _DASHES.get(a.get("stroke_style"))
    style = True   # aplicar colores/borde genéricos

    if k == "highlight":
        annot = page.add_highlight_annot(r)
    elif k in ("underline", "strikeout"):
        annot = (page.add_underline_annot if k == "underline" else page.add_strikeout_annot)(r)
    elif k == "redact":                               # pendiente: Acrobat/Foxit lo muestran para aplicarlo
        annot = page.add_redact_annot(r, fill=(0, 0, 0))
        style = False
    elif k == "ink":
        pts = a.get("points") or []
        if len(pts) < 2:
            return None
        annot = page.add_ink_annot([[(float(x), float(y)) for x, y in pts]])
        fill = None
    elif k in ("line", "arrow", "darrow"):
        p1, p2 = _rotated([pymupdf.Point(x1, y1), pymupdf.Point(x2, y2)], rot,
                          (x1 + x2) / 2, (y1 + y2) / 2)
        annot = page.add_line_annot(p1, p2)
        if k != "line":
            start = k == "darrow" or a.get("arrow_start")
            end = a.get("arrow_end", True)
            annot.set_line_ends(_LE_ARROW if start else _LE_NONE, _LE_ARROW if end else _LE_NONE)
            fill = stroke
    elif k == "rect" and not rot:
        annot = page.add_rect_annot(r)
    elif k == "circle" and not rot:
        annot = page.add_circle_annot(r)
    elif k in ("rect", "rrect", "circle", "triangle", "arrow_shape"):
        if k == "rect":
            pts = [r.tl, r.tr, r.br, r.bl]
        elif k == "rrect":
            pts = _rounded_rect(r, a.get("corner_r") or 7)
        elif k == "circle":
            pts = _ellipse(r)
        elif k == "triangle":
            pts = [pymupdf.Point(cx, y1), pymupdf.Point(x2, y2), pymupdf.Point(x1, y2)]   # volteado: y1 > y2
        else:
            pts = _arrow_shape(a)
            fill = fill or stroke
        annot = page.add_polygon_annot(_rotated(pts, rot, cx, cy))
    elif k in ("text", "textbox"):
        fs = max(4, a.get("font_size", 12))
        txt = a.get("text", "")
        if k == "text":
            lines = txt.split("\n") or [""]
            w = max(pymupdf.get_text_length(ln, "helv", fs) for ln in lines) + fs
            top = y1 - fs
            r = pymupdf.Rect(x1, top, x1 + w, top + len(lines) * fs * 1.3 + 4)
            if rot % 360:                                # girado: como imagen (en PDFRapid sigue siendo editable)
                annot = _rotated_stamp(page, r, _text_image(a, r, False), rot)
            else:
                annot = page.add_freetext_annot(r, txt, fontsize=fs, fontname="helv",
                                                text_color=_rgb(a.get("text_color")), opacity=op)
        elif rot % 360:
            annot = _rotated_stamp(page, r, _text_image(a, r, True), rot)
        else:
            bw = a.get("box_bw", 0) or 0
            annot = page.add_freetext_annot(
                r, txt, fontsize=fs, fontname="helv", text_color=_rgb(a.get("text_color")),
                fill_color=_rgb(a.get("box_bg")), border_width=0,
                opacity=op, align={"center": 1, "right": 2}.get(a.get("text_align"), 0))
            if bw:          # FreeText pinta el borde con el color del texto: el borde va aparte, con su color
                border = page.add_rect_annot(r)
                border.set_colors(stroke=_rgb(a.get("box_border") or "#000000")); border.set_border(width=bw)
                border.set_opacity(op); border.update()
                page.parent.xref_set_key(border.xref, KEY_PART, "true")
        style = False
    elif k == "comment":
        annot = page.add_text_annot(pymupdf.Point(x1, y1), a.get("text", ""), icon="Comment")
        annot.set_info(title=a.get("author", ""), content=a.get("text", ""))
        annot.update()
        _add_thread(page, annot, a, pymupdf.Point(x1, y1))
        style = False
    elif k == "image":
        data = a.get("image_data")
        if not data:
            return None
        raw = base64.b64decode(data)
        if rot % 360:
            from PyQt6.QtGui import QImage
            annot = _rotated_stamp(page, r, QImage.fromData(raw), rot)
        else:
            annot = page.add_stamp_annot(r, stamp=raw)
        style = False
    else:
        return None

    if style:
        if k in ("highlight", "underline", "strikeout"):
            annot.set_colors(stroke=stroke)
        else:
            annot.set_colors(stroke=stroke, fill=fill)
            annot.set_border(width=width, dashes=dashes)
        annot.set_opacity(op)
    annot.update()
    return annot


def _add_thread(page, parent, a, pt):
    """Respuestas y estado de revisión de un comentario como anotaciones nativas «en respuesta a» (/IRT),
    para que Acrobat y otros lectores muestren el hilo. Al reabrir en PDFRapid se regeneran desde el JSON."""
    from models.annotation import REVIEW_STATES
    doc = page.parent
    items = [(r.get("author", ""), r.get("text", ""), None) for r in a.get("replies") or []]
    if a.get("status") in REVIEW_STATES and a.get("status"):
        items.append((a.get("author", ""), REVIEW_STATES[a["status"]][1], REVIEW_STATES[a["status"]][1]))
    for author, text, state in items:
        r = page.add_text_annot(pt, text, icon="Comment")
        r.set_info(title=author, content=text)
        r.set_flags(pymupdf.PDF_ANNOT_IS_HIDDEN if state else 0)
        r.update()
        doc.xref_set_key(r.xref, "IRT", f"{parent.xref} 0 R")
        if state:
            doc.xref_set_key(r.xref, "State", pymupdf.get_pdf_str(state))
            doc.xref_set_key(r.xref, "StateModel", "(Review)")
        doc.xref_set_key(r.xref, KEY_PART, "true")


def export(doc, pages: dict, guides: dict = None):
    """Crea una copia de `doc` con las anotaciones de Pdfgm como nativas.
    `pages` = {página: [dict de Ann en puntos PDF sin rotación]}.
    El llamador debe guardar y cerrar la copia."""
    out = pymupdf.open("pdf", doc.tobytes())
    for pno, anns in pages.items():
        if not (0 <= pno < len(out)):
            continue
        page = out[pno]
        for a in anns:
            annot = _add_native(page, a)
            if annot is None:
                continue
            if a.get("hidden"):                          # oculto: se conserva en el archivo, pero no se ve ni se imprime
                annot.set_flags(annot.flags | pymupdf.PDF_ANNOT_IS_HIDDEN)
            xref = out.get_new_xref()
            out.update_object(xref, "<<>>")
            out.update_stream(xref, json.dumps(a, ensure_ascii=False).encode("utf-8"))
            out.xref_set_key(annot.xref, KEY, f"{xref} 0 R")
    _write_guides(out, guides)
    return out
