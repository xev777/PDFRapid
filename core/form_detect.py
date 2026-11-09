# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Detectar campos de formulario en un PDF plano (como «Preparar formulario» de Acrobat), sin dependencias nuevas:
- líneas horizontales con una etiqueta a la izquierda o debajo («Nombre: ______») → campo de texto;
- guiones bajos en el texto («Fecha: ________») → campo de texto;
- recuadros pequeños y cuadrados vacíos (o los caracteres ☐ □) → casilla;
- recuadros vacíos más grandes → campo de texto (de varias líneas si son altos).
Solo ve lo que es dibujo o texto del PDF: en uno escaneado (una imagen) no encuentra nada."""
import re
import pymupdf

MIN_LINE = 40          # largo mínimo (pt) de una línea para escribir sobre ella
LINE_H = 15            # alto del campo que se pone sobre una línea
BOX_CHARS = "☐□❏❑"
_UNDERS = re.compile(r"_{4,}")


def _overlap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    """Parte de `a` cubierta por `b` (0-1)."""
    i = a & b
    return 0.0 if i.is_empty else i.get_area() / max(a.get_area(), 1e-6)


def _label(words, r: pymupdf.Rect, below=False) -> str:
    """Texto a la izquierda de `r` en la misma línea (o justo debajo si `below`)."""
    if below:
        ws = [w for w in words if 0 <= w[1] - r.y1 <= 14 and w[0] < r.x1 and w[2] > r.x0]
    else:
        mid = (r.y0 + r.y1) / 2
        ws = [w for w in words if w[2] <= r.x0 + 2 and r.x0 - w[2] < 160 and w[1] - 4 <= mid <= w[3] + 4]
        ws = ws[-4:]
    txt = " ".join(w[4] for w in sorted(ws, key=lambda w: (w[1], w[0])))
    return _UNDERS.sub("", txt).strip(" :.-_\t")


def _empty(words, r: pymupdf.Rect) -> bool:
    return not any(pymupdf.Rect(w[:4]).intersects(r) and _overlap(pymupdf.Rect(w[:4]), r) > 0.3 for w in words)


def detect(page) -> list:
    """[{rect (puntos de la página tal como se ve), kind ("text" | "multiline" | "check"), label}] en orden de lectura."""
    words = page.get_text("words")
    taken = [w.rect for w in page.widgets()]          # campos que ya existen
    found = []

    def add(rect, kind, label):
        rect = pymupdf.Rect(rect)
        if rect.width < 6 or rect.height < 6: return
        if any(_overlap(rect, t) > 0.4 or _overlap(t, rect) > 0.4 for t in taken): return
        taken.append(rect); found.append({"rect": rect, "kind": kind, "label": label})

    lines, boxes = [], []
    for path in page.get_drawings():
        for it in path["items"]:
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                if abs(p1.y - p2.y) < 1 and abs(p1.x - p2.x) >= MIN_LINE:
                    lines.append(pymupdf.Rect(min(p1.x, p2.x), p1.y, max(p1.x, p2.x), p1.y))
            elif it[0] == "re":
                r = pymupdf.Rect(it[1])
                if r.height <= 1.6 and r.width >= MIN_LINE:          # línea dibujada como rectángulo fino
                    lines.append(pymupdf.Rect(r.x0, r.y1, r.x1, r.y1))
                elif r.width >= 6 and r.height >= 6:
                    boxes.append(r)
    page_area = page.rect.get_area()
    # 1) casillas: cuadrados pequeños vacíos y caracteres de casilla
    for r in boxes:
        if r.width <= 22 and abs(r.width - r.height) <= 2.5 and _empty(words, r):
            add(r, "check", _right_label(words, r) or _label(words, r))
    for w in words:
        if w[4] and w[4][0] in BOX_CHARS:
            r = pymupdf.Rect(w[0], w[1], w[0] + (w[3] - w[1]), w[3])
            add(r, "check", _right_label(words, r))
    # 2) recuadros vacíos para escribir (no la página entera ni marcos grandes)
    for r in sorted(boxes, key=lambda r: (r.y0, r.x0)):
        if r.width >= MIN_LINE and 12 <= r.height <= 200 and r.get_area() < page_area * 0.25 and _empty(words, r):
            inner = r + (1.5, 1.5, -1.5, -1.5)
            add(inner, "multiline" if r.height > 36 else "text", _label(words, r) or _label(words, r, below=True)
                or _label_above(words, r))
    # 3) guiones bajos en el texto
    for w in words:
        for m in _UNDERS.finditer(w[4]):
            n = len(w[4]) or 1
            x0 = w[0] + (w[2] - w[0]) * m.start() / n
            x1 = w[0] + (w[2] - w[0]) * m.end() / n
            if x1 - x0 < 25: continue
            r = pymupdf.Rect(x0, w[3] - LINE_H, x1, w[3])
            add(r, "text", (w[4][:m.start()].strip(" :.") or _label(words, r)))
    # 4) líneas con etiqueta a la izquierda o debajo, y espacio libre encima
    for ln in sorted(lines, key=lambda r: (r.y0, r.x0)):
        r = pymupdf.Rect(ln.x0, ln.y0 - LINE_H, ln.x1, ln.y0 - 0.5)
        if not _empty(words, r): continue
        label = _label(words, r) or _label(words, pymupdf.Rect(ln.x0, ln.y0, ln.x1, ln.y0), below=True)
        if label: add(r, "text", label)
    m = page.rotation_matrix                         # a coordenadas de la página tal como se ve
    for f in found: f["rect"] = pymupdf.Rect(f["rect"] * m)
    found.sort(key=lambda f: (round(f["rect"].y0 / 4), f["rect"].x0))
    return found


def _right_label(words, r) -> str:
    ws = [w for w in words if w[0] >= r.x1 - 1 and w[0] - r.x1 < 12 + 120 and w[1] - 4 <= (r.y0 + r.y1) / 2 <= w[3] + 4]
    ws = sorted(ws, key=lambda w: w[0])[:4]
    return " ".join(w[4] for w in ws).strip(" :.")


def _label_above(words, r) -> str:
    ws = [w for w in words if 0 <= r.y0 - w[3] <= 14 and w[0] < r.x1 and w[2] > r.x0]
    return " ".join(w[4] for w in sorted(ws, key=lambda w: w[0])[:5]).strip(" :.")


def apply(doc, found_by_page: dict, add_field, unique_name, clean_name) -> int:
    """Crea los campos detectados. `found_by_page` = {página: detect(page)}. Devuelve cuántos se crearon."""
    n = 0
    for pno, found in found_by_page.items():
        for f in found:
            base = clean_name(f["label"])[:40] if f["label"] else ("Casilla" if f["kind"] == "check" else "Campo")
            name = base if base not in _names(doc) else unique_name(doc, base + " ")
            add_field(doc, pno, tuple(f["rect"]), f["kind"], {"name": name, "tooltip": f["label"]})
            n += 1
    return n


def _names(doc) -> set:
    return {w.field_name for p in doc for w in p.widgets()}
