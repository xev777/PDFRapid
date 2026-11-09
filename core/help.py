# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Ayuda por función: fuente única en docs/guia/ayuda.json.
La usan la ayuda de la app (botón ?, F1, Centro de ayuda) y la guía en PDF (capítulo «Referencia de funciones»),
para que nunca digan cosas distintas."""
import html
import json
import os
import unicodedata
from core import guide

_data = None
LABELS = {"es": ("Qué hace", "Para qué sirve", "Cómo se usa", "Ejemplo", "Para usuarios avanzados"),
          "en": ("What it does", "What it is for", "How to use it", "Example", "For advanced users")}


def _load():
    global _data
    if _data is None:
        path = os.path.join(os.path.dirname(guide.source("es")), "ayuda.json")
        with open(path, encoding="utf-8") as f:
            _data = json.load(f)
    return _data


def _lang(lang):
    return lang if lang in LABELS else "es"


def groups(lang: str) -> list:
    """[(id, nombre)] en orden."""
    i = 1 if _lang(lang) == "es" else 2
    return [(g[0], g[i]) for g in _load()["groups"]]


def topics(group: str = None) -> list:
    return [t for t in _load()["topics"] if group is None or t["group"] == group]


def topic(tid: str) -> dict:
    return next((t for t in _load()["topics"] if t["id"] == tid), None)


def title(tid: str, lang: str) -> str:
    t = topic(tid)
    return t[_lang(lang)]["title"] if t else ""


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def search(query: str, lang: str) -> list:
    """Ids de las fichas que contienen todas las palabras (sin distinguir tildes ni mayúsculas); el título pesa más."""
    words = _norm(query).split()
    out = []
    for t in _load()["topics"]:
        c = t[_lang(lang)]
        body = _norm(" ".join([c["what"], c["why"], " ".join(c["how"]), c["example"], c["expert"]]))
        head = _norm(c["title"])
        if all(w in head or w in body for w in words):
            out.append((-sum(w in head for w in words), t["id"]))
    return [tid for _, tid in sorted(out)] if words else [t["id"] for t in _load()["topics"]]


def to_html(tid: str, lang: str, level: int = 2) -> str:
    """Ficha en HTML sencillo (lo entienden QTextBrowser y pymupdf.Story)."""
    t = topic(tid)
    if not t: return ""
    c, lab, e = t[_lang(lang)], LABELS[_lang(lang)], html.escape
    steps = "".join(f"<li>{e(s)}</li>" for s in c["how"])
    return (f"<h{level}>{e(c['title'])}</h{level}>"
            f"<p><b>{lab[0]}:</b> {e(c['what'])}</p>"
            f"<p><b>{lab[1]}:</b> {e(c['why'])}</p>"
            f"<p><b>{lab[2]}:</b></p><ol>{steps}</ol>"
            f"<p><b>{lab[3]}:</b> {e(c['example'])}</p>"
            f"<p class=\"exp\"><b>{lab[4]}:</b> {e(c['expert'])}</p>")


def guide_chapter(lang: str) -> str:
    """Capítulo «Referencia de funciones» de la guía en PDF: todas las fichas, por grupos."""
    lang = _lang(lang)
    head = "Referencia de funciones" if lang == "es" else "Feature reference"
    intro = ("Cada función explicada: qué hace, para qué sirve, cómo se usa, un ejemplo y detalles para usuarios "
             "avanzados. En la aplicación, pulsa F1 o el botón ? para ver la ficha de lo que estás usando."
             if lang == "es" else
             "Each feature explained: what it does, what it is for, how to use it, an example and details for advanced "
             "users. In the application, press F1 or the ? button to see the page for what you are using.")
    parts = [f"<h1>{head}</h1><p>{html.escape(intro)}</p>"]
    for gid, gname in groups(lang):
        parts.append(f"<h2>{html.escape(gname)}</h2>")
        parts += [to_html(t["id"], lang, 3) for t in topics(gid)]
    return "\n".join(parts)
