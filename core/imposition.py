# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Impresión avanzada: varias páginas por hoja, folleto y póster. Cada función crea un PDF nuevo (vectorial,
sin rasterizar) con las hojas ya compuestas, que luego se imprime normalmente. Las anotaciones y los campos
de formulario deben estar aplanados en `src` (show_pdf_page solo copia el contenido de la página)."""
import math
import pymupdf

def prepare(doc, annots: bool = True):
    """Deja `doc` listo para componer: anotaciones y formularios pasados al contenido (o quitados) y páginas
    giradas convertidas a su orientación visible (show_pdf_page no aplica /Rotate)."""
    if annots:
        for page in doc:                                 # los objetos ocultos no se imprimen
            for a in [a for a in page.annots() if a.flags & pymupdf.PDF_ANNOT_IS_HIDDEN]: page.delete_annot(a)
        doc.bake(annots=True, widgets=True)
    else:
        for page in doc:
            while page.first_widget: page.delete_widget(page.first_widget)
            while page.first_annot: page.delete_annot(page.first_annot)
    for page in doc:
        if page.rotation: page.remove_rotation()
    return doc


GRIDS = {2: (2, 1), 4: (2, 2), 6: (3, 2), 8: (4, 2), 9: (3, 3), 16: (4, 4)}   # n → (columnas, filas) en horizontal


def _fit(cell: pymupdf.Rect, w: float, h: float) -> pymupdf.Rect:
    k = min(cell.width / w, cell.height / h)
    x, y = cell.x0 + (cell.width - w * k) / 2, cell.y0 + (cell.height - h * k) / 2
    return pymupdf.Rect(x, y, x + w * k, y + h * k)


def _place(sheet, cell, src, pno, border):
    r = _fit(cell, src[pno].rect.width, src[pno].rect.height)
    sheet.show_pdf_page(r, src, pno)
    if border: sheet.draw_rect(r, color=(0.6, 0.6, 0.6), width=0.5)


def n_up(src, pages: list, n: int, sheet_size, margin=18, gap=8, border=True):
    """`n` páginas por hoja, de izquierda a derecha y de arriba abajo. La hoja se gira si conviene."""
    cols, rows = GRIDS[n]
    page_landscape = src[pages[0]].rect.width > src[pages[0]].rect.height if pages else False
    if page_landscape: cols, rows = rows, cols
    landscape = cols > rows if cols != rows else page_landscape       # 2, 6, 8 páginas verticales: hoja apaisada
    w, h = (max(sheet_size), min(sheet_size)) if landscape else (min(sheet_size), max(sheet_size))
    out = pymupdf.open()
    cw, ch = (w - 2 * margin - gap * (cols - 1)) / cols, (h - 2 * margin - gap * (rows - 1)) / rows
    for i in range(0, len(pages), n):
        sheet = out.new_page(width=w, height=h)
        for k, pno in enumerate(pages[i:i + n]):
            c, r = k % cols, k // cols
            x, y = margin + c * (cw + gap), margin + r * (ch + gap)
            _place(sheet, pymupdf.Rect(x, y, x + cw, y + ch), src, pno, border)
    return out


def booklet_order(count: int) -> list:
    """Orden de las páginas para un folleto (hojas dobladas por la mitad, impresión a doble cara):
    pares (izquierda, derecha) por cara; None = página en blanco."""
    total = math.ceil(count / 4) * 4 if count else 0
    p = lambda i: i if i < count else None
    out = []
    for s in range(total // 4):
        out.append((p(total - 1 - 2 * s), p(2 * s)))            # cara: última, primera
        out.append((p(2 * s + 1), p(total - 2 - 2 * s)))        # dorso: segunda, penúltima
    return out


def booklet(src, pages: list, sheet_size, margin=12):
    """Folleto: dos páginas por cara en hoja apaisada. Imprimir a doble cara volteando por el borde corto."""
    w, h = max(sheet_size), min(sheet_size)
    out = pymupdf.open()
    for left, right in booklet_order(len(pages)):
        sheet = out.new_page(width=w, height=h)
        for k, idx in enumerate((left, right)):
            if idx is None: continue
            x0 = margin + k * (w / 2)
            _place(sheet, pymupdf.Rect(x0, margin, x0 + w / 2 - 2 * margin, h - margin), src, pages[idx], False)
    return out


def poster(src, pages: list, sheet_size, scale: float, overlap=18, marks=True):
    """Póster: cada página ampliada `scale` veces y repartida en hojas (mosaico) que se solapan `overlap` pt
    para pegarlas. Devuelve (documento, hojas por página)."""
    sw, sh = sheet_size
    out, tiles = pymupdf.open(), 0
    for pno in pages:
        pr = src[pno].rect
        pw, ph = pr.width * scale, pr.height * scale
        if (pw > ph) != (sw > sh): sw, sh = sh, sw                   # orientar la hoja como la página
        step_x, step_y = sw - overlap, sh - overlap
        cols, rows = max(1, math.ceil((pw - overlap) / step_x)), max(1, math.ceil((ph - overlap) / step_y))
        tiles = cols * rows
        for r in range(rows):
            for c in range(cols):
                clip = pymupdf.Rect(c * step_x, r * step_y, c * step_x + sw, r * step_y + sh) / scale
                clip &= pr
                sheet = out.new_page(width=sw, height=sh)
                target = pymupdf.Rect(0, 0, clip.width * scale, clip.height * scale)
                sheet.show_pdf_page(target, src, pno, clip=clip)
                if marks:
                    sheet.insert_text((6, sh - 6), f"{pno + 1} · {r + 1}-{c + 1} / {rows}×{cols}", fontsize=6,
                                      color=(0.5, 0.5, 0.5))
    return out, tiles
