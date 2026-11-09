# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Búsqueda de texto sin interfaz: en un documento o en todos los PDF de una carpeta
(búsqueda avanzada al estilo Acrobat/Foxit, pensada también para auditoría)."""
import fnmatch
import os
import re
import pymupdf

MAX_INSTANCES = 400        # instancias con contexto por archivo (las demás solo se cuentan)

MODES = {"phrase": "Frase exacta", "all": "Todas las palabras", "any": "Cualquiera de las palabras",
         "regex": "Expresión regular"}


def _matches(pg, r, term, case, whole) -> bool:
    """`search_for` no distingue mayúsculas ni palabras: se filtra mirando el texto alrededor."""
    if not (case or whole):
        return True
    pad = r.height * 0.7
    ctx = pg.get_textbox(r + (-pad, 0, pad, 0))
    pat = re.escape(term)
    if whole:
        pat = rf"(?<!\w){pat}(?!\w)"
    return re.search(pat, ctx, 0 if case else re.IGNORECASE) is not None


def context(pg, r) -> str:
    """La línea donde está la coincidencia (para mostrarla en la lista)."""
    line = pg.get_textbox(pymupdf.Rect(0, r.y0, pg.rect.width + pg.rect.height, r.y1))
    return " ".join(line.split())[:110]


def find_in_page(pg, term, case=False, whole=False) -> list:
    """Rects (sin rotar) de las coincidencias en la página."""
    return [r for r in pg.search_for(term) if _matches(pg, r, term, case, whole)]


def parse_terms(query: str, mode: str) -> list:
    """Términos a buscar. Frase/regex: la consulta entera. Todas/cualquiera: separados por «;»
    o por espacios, y las frases entre comillas se mantienen juntas."""
    q = query.strip()
    if not q:
        return []
    if mode in ("phrase", "regex"):
        return [q]
    if ";" in q:
        return [t.strip() for t in q.split(";") if t.strip()]
    return [a or b for a, b in re.findall(r'"([^"]+)"|(\S+)', q)]


def _text_hits(pg, term, mode, case, whole):
    """[(término encontrado, rect)] en el texto de la página."""
    if mode != "regex":
        return [(term, r) for r in find_in_page(pg, term, case, whole)]
    out, seen = [], set()
    rx = re.compile(term, 0 if case else re.IGNORECASE)
    for m in rx.finditer(pg.get_text()):
        found = " ".join(m.group(0).split())
        if not found or found in seen:
            continue
        seen.add(found)
        out += [(found, r) for r in pg.search_for(found)]
    return out


def _in(text, term, mode, case, whole) -> bool:
    if mode == "regex":
        return re.search(term, text, 0 if case else re.IGNORECASE) is not None
    pat = re.escape(term)
    if whole:
        pat = rf"(?<!\w){pat}(?!\w)"
    return re.search(pat, text, 0 if case else re.IGNORECASE) is not None


def pdf_files(folder: str, recursive: bool, name_filter: str = "") -> list:
    """PDF de la carpeta; `name_filter` admite comodines (`*contrato*`, `2026-*`)."""
    pat = (name_filter or "*").strip().lower()
    if not pat.endswith(".pdf") and not pat.endswith("*"):
        pat += "*"
    out = []
    for root, dirs, files in os.walk(folder):
        out += [os.path.join(root, f) for f in sorted(files)
                if f.lower().endswith(".pdf") and fnmatch.fnmatch(f.lower(), pat)]
        if not recursive:
            break
    return out


def search_file(path, query, mode="phrase", case=False, whole=False, comments=False, bookmarks=False,
                stop=lambda: False):
    """Resultado de buscar en un archivo (una entrada por instancia, como Acrobat):
      {"hits": [(página, término, 1, contexto, tipo)], "total": n.º de instancias, "no_text": bool}
    Solo las primeras MAX_INSTANCES llevan contexto (un PDF enorme puede tener miles).
    tipo = "texto" | "comentario" | "marcador". None si el PDF tiene contraseña o está dañado.
    Con mode="all" el archivo solo cuenta si contiene todos los términos."""
    terms = parse_terms(query, mode)
    try:
        doc = pymupdf.open(path)
    except Exception:
        return None
    try:
        if doc.needs_pass:
            return None
        hits, has_text, total, found_terms = [], False, 0, set()
        for pg in doc:
            if stop():
                break
            if not has_text and pg.get_text().strip():
                has_text = True
            for t in terms:
                for found, r in _text_hits(pg, t, mode, case, whole):
                    total += 1; found_terms.add(found.lower())
                    if len(hits) < MAX_INSTANCES:
                        hits.append((pg.number, found, 1, context(pg, r), "texto"))
            if comments:
                for a in pg.annots():
                    content = (a.info.get("content") or "").strip()
                    for t in terms:
                        if content and _in(content, t, mode, case, whole):
                            total += 1; found_terms.add(t.lower())
                            hits.append((pg.number, t, 1, " ".join(content.split())[:110], "comentario"))
        if bookmarks:
            for _lvl, title, page in doc.get_toc():
                for t in terms:
                    if _in(title, t, mode, case, whole):
                        total += 1; found_terms.add(t.lower())
                        hits.append((max(page - 1, 0), t, 1, title[:110], "marcador"))
        if mode == "all" and not all(t.lower() in found_terms for t in terms):
            hits, total = [], 0
        hits.sort(key=lambda h: (h[0], h[4] != "texto"))
        return {"hits": hits, "total": total, "no_text": not has_text}
    finally:
        doc.close()
