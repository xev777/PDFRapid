# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Guía de usuario: docs/guia/guia_<idioma>.html → PDF con pymupdf.Story. La compilación la deja hecha junto al
.exe (carpeta «guia»); en desarrollo se genera la primera vez en la carpeta temporal.
Uso en la compilación: python -m core.guide <carpeta de salida>"""
import io
import os
import sys
import tempfile
import pymupdf
from core.constants import APP_NAME, APP_VERSION

CSS = """
* {font-family: sans-serif; font-size: 10.5pt; line-height: 1.35;}
h1 {font-size: 22pt; color: #1F5FA8; margin-bottom: 2pt;}
h2 {font-size: 14pt; color: #1F5FA8; margin-top: 14pt; margin-bottom: 4pt;}
p, li {margin-top: 3pt; margin-bottom: 3pt;}
.sub {color: #666666; font-size: 9.5pt;}
table {border-collapse: collapse; margin-top: 4pt;}
th {background-color: #E8EEF7; text-align: left;}
th, td {border: 0.5pt solid #B0B8C4; padding: 2pt 5pt; font-size: 9.5pt;}
h3 {font-size: 12pt; color: #1F5FA8; margin-top: 10pt; margin-bottom: 2pt;}
.exp {color: #555555; font-size: 9.5pt;}
"""


def _root():
    return sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def source(lang: str) -> str:
    for d in (os.path.join(_root(), "docs", "guia"), os.path.join(_root(), "guia")):
        p = os.path.join(d, f"guia_{lang}.html")
        if os.path.isfile(p): return p
    return source("es") if lang != "es" else ""


def build(lang: str, out: str) -> str:
    """Genera el PDF de la guía en `out` (A4, márgenes de 2 cm, pie con número de página)."""
    from core import help as helpdoc                    # referencia de funciones: misma fuente que la ayuda de la app
    html = open(source(lang), encoding="utf-8").read().replace("{version}", APP_VERSION)
    ref = helpdoc.guide_chapter(lang)
    html = html.replace("</body>", ref + "</body>") if "</body>" in html else html + ref
    story = pymupdf.Story(html=html, user_css=CSS)
    page_rect = pymupdf.paper_rect("a4"); body = page_rect + (57, 57, -57, -64)
    buf = io.BytesIO()
    w = pymupdf.DocumentWriter(buf)
    more = True
    while more:
        dev = w.begin_page(page_rect)
        more, _ = story.place(body)
        story.draw(dev)
        w.end_page()
    w.close()
    doc = pymupdf.open("pdf", buf.getvalue())
    title = f"{APP_NAME} — " + ("Guía de usuario" if lang == "es" else "User guide")
    for i, page in enumerate(doc):
        page.insert_text((page.rect.width - 80, page.rect.height - 30), f"{i + 1} / {len(doc)}", fontsize=8,
                         color=(0.45, 0.45, 0.45))
    doc.set_metadata({"title": title, "author": "Fernando Erazo", "creator": APP_NAME, "producer": APP_NAME})
    doc.save(out, garbage=3, deflate=True); doc.close()
    return out


def guide_pdf(lang: str) -> str:
    """Ruta del PDF de la guía en `lang`: el que trae la instalación o uno generado en la carpeta temporal."""
    lang = lang if lang in ("es", "en") else "en"
    name = f"{APP_NAME}-{'guia' if lang == 'es' else 'guide'}-{lang}.pdf"
    if getattr(sys, "frozen", False):
        p = os.path.join(os.path.dirname(sys.executable), "guia", name)
        if os.path.isfile(p): return p
    out = os.path.join(tempfile.gettempdir(), name)
    src = source(lang)
    srcs = [s for s in (src, os.path.join(os.path.dirname(src), "ayuda.json")) if s and os.path.isfile(s)]
    if not os.path.isfile(out) or any(os.path.getmtime(s) > os.path.getmtime(out) for s in srcs):
        build(lang, out)
    return out


if __name__ == "__main__":
    os.makedirs(sys.argv[1], exist_ok=True)
    for lg in ("es", "en"):
        print(build(lg, os.path.join(sys.argv[1], f"{APP_NAME}-{'guia' if lg == 'es' else 'guide'}-{lg}.pdf")))
