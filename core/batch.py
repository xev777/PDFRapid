# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Procesar por lotes: aplicar una acción a todos los PDF de una carpeta. Los originales nunca se tocan:
cada resultado se guarda en la carpeta de salida (con la misma estructura de subcarpetas)."""
import os
import pymupdf
from core import export, pdf_tools
from core.pdf_io import save_pdf

# acción → (texto, extensión del resultado)
ACTIONS = {
    "ocr": ("Reconocer texto (OCR) en páginas escaneadas", ".pdf"),
    "compress": ("Comprimir", ".pdf"),
    "watermark": ("Marca de agua", ".pdf"),
    "number": ("Numerar páginas / Bates", ".pdf"),
    "protect": ("Proteger con contraseña", ".pdf"),
    "pdfa": ("Convertir a PDF/A-2b", ".pdf"),
    "flatten": ("Aplanar anotaciones y formularios", ".pdf"),
    "scrub": ("Eliminar información oculta", ".pdf"),
    "txt": ("Exportar a texto (.txt)", ".txt"),
    "xlsx": ("Exportar tablas a Excel (.xlsx)", ".xlsx"),
    "md": ("Exportar a Markdown (.md)", ".md"),
}


class Locked(Exception):
    """El PDF pide contraseña para abrirlo."""


def find_pdfs(folder: str, recursive: bool) -> list:
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        out += [os.path.join(root, f) for f in sorted(files) if f.lower().endswith(".pdf")]
        if not recursive: break
    return out


def out_path(src: str, folder: str, out_dir: str, action: str) -> str:
    rel = os.path.relpath(src, folder)
    path = os.path.splitext(os.path.join(out_dir, rel))[0] + ACTIONS[action][1]
    if os.path.abspath(path) == os.path.abspath(src):          # nunca sobrescribir el original
        path = os.path.splitext(path)[0] + "_procesado" + ACTIONS[action][1]
    return path


def _ocr(doc) -> int:
    from core import ocr
    n = 0
    for page in doc:
        if page.get_text().strip(): continue                    # ya tiene texto
        lines = ocr.ocr_page(page)
        if lines: ocr.add_text_layer(page, lines); n += 1
    return n


def process(src: str, dst: str, action: str, opts: dict) -> str:
    """Aplica `action` a `src` y guarda en `dst`. Devuelve un resumen corto del resultado."""
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    if action == "pdfa":
        from core import pdfa
        rep = pdfa.convert(src, dst, opts.get("producer", "PDFRapid"))
        return f"{len(rep['rasterizadas'])} raster" if rep["rasterizadas"] else ""
    doc = pymupdf.open(src)
    try:
        if doc.needs_pass: raise Locked(src)
        pages = list(range(len(doc)))
        info, crypt, save_opts = "", None, {}
        if action == "ocr":
            info = str(_ocr(doc))
        elif action == "compress":
            pdf_tools.compress(doc, opts.get("level", "balanced")); save_opts = pdf_tools.SAVE_OPTS
        elif action == "watermark":
            pdf_tools.watermark(doc, pages, opts.get("text") or "CONFIDENCIAL")
        elif action == "number":
            pdf_tools.number_pages(doc, pages, opts.get("fmt") or "{n}", opts.get("pos", "bc"))
        elif action == "protect":
            crypt = pdf_tools.make_crypt(opts["password"], opts.get("owner") or None, {k for k, _, _ in pdf_tools.PERMS})
        elif action == "flatten":
            doc.bake(annots=True, widgets=True)
        elif action == "scrub":
            pdf_tools.scrub(doc)
        elif action == "txt":
            return str(export.to_text(doc, dst))
        elif action == "md":
            return str(export.to_markdown(doc, dst))
        elif action == "xlsx":
            n, how = export.to_xlsx(doc, dst)
            return f"{n} {how}" if how else "0"
        save_pdf(doc, dst, crypt, **save_opts)
        return info
    finally:
        doc.close()


def run(files: list, folder: str, out_dir: str, action: str, opts: dict, progress=None, cancelled=lambda: False) -> list:
    """Procesa cada archivo; un error en uno no detiene los demás. Devuelve [(src, dst, error o None, resumen)]."""
    results = []
    for i, src in enumerate(files):
        if cancelled(): break
        if progress: progress(i, src)
        dst = out_path(src, folder, out_dir, action)
        try:
            results.append((src, dst, None, process(src, dst, action, opts)))
        except Locked:
            results.append((src, None, "protegido con contraseña", ""))
        except Exception as e:
            results.append((src, None, str(e) or type(e).__name__, ""))
    return results
