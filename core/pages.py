# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Operaciones de páginas sin interfaz: rangos, dividir y combinar."""
from core.i18n import T, Tf
import pymupdf


def parse_ranges(text: str, total: int) -> list:
    """'1-3, 5, 8-' → [0, 1, 2, 4, 7, …] (índices desde 0, sin repetir, en el orden escrito).
    Admite rangos abiertos ('8-' hasta el final, '-3' desde el inicio). ValueError si algo no es válido."""
    out, seen = [], set()
    for part in filter(None, (p.strip() for p in text.replace(";", ",").split(","))):
        if "-" in part:
            a, b = (x.strip() for x in part.split("-", 1))
            lo, hi = int(a) if a else 1, int(b) if b else total
        else:
            lo = hi = int(part)
        if not (1 <= lo <= total and 1 <= hi <= total):
            raise ValueError(Tf("'{0}' está fuera de 1–{1}", part, total))
        step = 1 if hi >= lo else -1
        for n in range(lo, hi + step, step):
            if n - 1 not in seen:
                seen.add(n - 1)
                out.append(n - 1)
    if not out:
        raise ValueError(T("No se indicó ninguna página"))
    return out


def groups_every(n: int, total: int) -> list:
    """Grupos de `n` páginas: [[0..n-1], [n..2n-1], …]."""
    return [list(range(i, min(i + n, total))) for i in range(0, total, n)]


def groups_ranges(text: str, total: int) -> list:
    """Un grupo por cada rango separado por comas: '1-3, 4-10' → dos archivos."""
    return [parse_ranges(part, total) for part in text.replace(";", ",").split(",") if part.strip()]


def groups_bookmarks(toc: list, total: int, level: int = 1) -> list:
    """Un grupo por cada marcador del nivel `level` (o menor): desde su página hasta la anterior al siguiente.
    `toc` = doc.get_toc() ([nivel, título, página 1-based, …]). Las páginas antes del primero van en «Inicio».
    Devuelve [(título, [páginas 0-based])]."""
    marks = []
    for item in toc:
        lv, title, page = item[0], item[1], item[2]
        if lv <= level and 1 <= page <= total and not (marks and marks[-1][1] == page - 1):
            marks.append((title.strip() or "?", page - 1))
    if not marks: return []
    out = []
    if marks[0][1] > 0: out.append((T("Inicio"), list(range(0, marks[0][1]))))
    for i, (title, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else total
        if end > start: out.append((title, list(range(start, end))))
    return out


def safe_filename(name: str, limit: int = 60) -> str:
    """Nombre de archivo válido en Windows a partir de un título."""
    bad = '<>:"/\\|?*'
    s = "".join("_" if c in bad or ord(c) < 32 else c for c in name).strip(" .")
    return s[:limit].rstrip(" .") or "parte"


def extract(doc, pages: list):
    """Documento nuevo con `pages` (índices) en ese orden."""
    out = pymupdf.open()
    for p in pages:
        out.insert_pdf(doc, from_page=p, to_page=p)
    return out


def combine(docs: list):
    """Documento nuevo con todas las páginas de `docs`, en orden."""
    out = pymupdf.open()
    for d in docs:
        out.insert_pdf(d)
    return out
