# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Comparar el texto de dos PDF página por página (palabras eliminadas y agregadas)."""
import difflib
import pymupdf


def _words(page):
    return [(pymupdf.Rect(w[:4]), w[4]) for w in page.get_text("words", sort=True)]


def compare_pages(pa, pb) -> dict:
    """Diferencias de palabras entre dos páginas: rects eliminados (en A), agregados (en B) y lista de cambios."""
    wa, wb = (_words(pa) if pa else []), (_words(pb) if pb else [])
    sm = difflib.SequenceMatcher(None, [t for _, t in wa], [t for _, t in wb], autojunk=False)
    removed, added, changes = [], [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        rem, add = wa[i1:i2], wb[j1:j2]
        removed += [r for r, _ in rem]
        added += [r for r, _ in add]
        changes.append((" ".join(t for _, t in rem), " ".join(t for _, t in add)))
    return {"removed": removed, "added": added, "changes": changes}


def compare_docs(a, b, stop=lambda: False) -> list:
    """Una entrada por página (alineadas por número):
    {"page", "status": "igual" | "cambios" | "solo A" | "solo B", "removed", "added", "changes"}"""
    out = []
    for i in range(max(len(a), len(b))):
        if stop():
            break
        pa = a[i] if i < len(a) else None
        pb = b[i] if i < len(b) else None
        d = compare_pages(pa, pb)
        status = "solo A" if pb is None else "solo B" if pa is None else ("cambios" if d["changes"] else "igual")
        out.append({"page": i, "status": status, **d})
    return out
