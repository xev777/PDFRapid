# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Exportar a Excel (.xlsx), texto (.txt), HTML y Markdown (.md), sin dependencias nuevas.
El .xlsx se escribe a mano (zip + XML, formato Office Open XML mínimo): una hoja por tabla detectada."""
import html
import re
import zipfile
from xml.sax.saxutils import escape
import pymupdf

if hasattr(pymupdf, "no_recommend_layout"): pymupdf.no_recommend_layout()   # sin avisos en la consola

_NUM = re.compile(r"^-?\d{1,15}([.,](\d{1,2}|\d{4,}))?$")   # «1.234» queda como texto: ¿mil o decimal?
_BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _pages(doc, pages):
    return list(pages) if pages is not None else list(range(len(doc)))


# ── texto y HTML ───────────────────────────────────────────────────────────────
def to_text(doc, path: str, pages=None) -> int:
    """Texto en orden de lectura, una página tras otra (separadas por un salto de página). Devuelve los caracteres."""
    parts = [doc[i].get_text("text", sort=True).rstrip() for i in _pages(doc, pages)]
    text = "\n\f\n".join(parts) + "\n"
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:       # con BOM: el Bloc de notas lo abre bien
        f.write(text)
    return len(text.strip())


def to_html(doc, path: str, pages=None, title: str = "") -> int:
    """HTML con el texto, títulos, listas e imágenes de cada página (fluye, no copia el diseño exacto)."""
    body = []
    for i in _pages(doc, pages):
        body.append(f'<section id="p{i + 1}">\n{doc[i].get_text("xhtml")}\n</section>')
    out = ("<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">\n"
           f"<title>{html.escape(title)}</title>\n"
           "<style>body{font-family:sans-serif;max-width:52em;margin:2em auto;padding:0 1em;line-height:1.4}"
           "section{border-bottom:1px solid #ccc;padding-bottom:1.5em;margin-bottom:1.5em}img{max-width:100%;height:auto}"
           "</style></head><body>\n" + "\n".join(body) + "\n</body></html>\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return len(body)


# ── Excel ──────────────────────────────────────────────────────────────────────
def tables(doc, pages=None) -> list:
    """[(nombre de hoja, filas)] con las tablas que detecta PyMuPDF."""
    out = []
    for i in _pages(doc, pages):
        try:
            found = doc[i].find_tables().tables
        except Exception:
            found = []
        for k, t in enumerate(found):
            rows = [[(c or "").replace("\n", " ").strip() for c in r] for r in t.extract()]
            if any(any(c for c in r) for r in rows):
                out.append((f"P{i + 1}" + (f" T{k + 1}" if len(found) > 1 else ""), rows))
    return out


def text_rows(doc, pages=None) -> list:
    """Sin tablas: una hoja por página con una fila por línea de texto y una celda por bloque separado."""
    out = []
    for i in _pages(doc, pages):
        rows = []
        for b in doc[i].get_text("dict", sort=True)["blocks"]:
            for line in b.get("lines", []):
                cells = [s["text"].strip() for s in line["spans"] if s["text"].strip()]
                if cells: rows.append(cells)
        if rows: out.append((f"P{i + 1}", rows))
    return out


def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s


def _cell(ref, v):
    v = _BAD_XML.sub("", v)
    if _NUM.match(v) and not (len(v) > 1 and v[0] == "0" and v[1].isdigit()):   # 0123 (códigos) queda como texto
        return f'<c r="{ref}"><v>{v.replace(",", ".")}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(v)}</t></is></c>'


def write_xlsx(path: str, sheets: list):
    """Escribe un .xlsx con hojas [(nombre, filas)] (celdas de texto o número)."""
    names, used = [], set()
    for name, _ in sheets:
        n = re.sub(r"[\[\]:*?/\\]", "", name)[:31] or "Hoja"
        base, k = n, 2
        while n.lower() in used: n = f"{base[:28]} {k}"; k += 1
        used.add(n.lower()); names.append(n)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
    ct += [f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
           for i in range(len(sheets))]
    ct.append("</Types>")
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
          + "".join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names))
          + "</sheets></workbook>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                      f'Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(sheets))) + "</Relationships>")
    root = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct)); z.writestr("_rels/.rels", root)
        z.writestr("xl/workbook.xml", wb); z.writestr("xl/_rels/workbook.xml.rels", rels)
        for i, (_, rows) in enumerate(sheets):
            width = max((len(r) for r in rows), default=1)
            cols = "".join(f'<col min="{c}" max="{c}" width="{min(60, max(8, max((len(r[c - 1]) for r in rows if len(r) >= c), default=8) + 2))}" customWidth="1"/>'
                           for c in range(1, width + 1))
            data = "".join(f'<row r="{y}">' + "".join(_cell(f"{_col(x)}{y}", v) for x, v in enumerate(r, 1) if v) + "</row>"
                           for y, r in enumerate(rows, 1))
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                       f"<cols>{cols}</cols><sheetData>{data}</sheetData></worksheet>")


def to_xlsx(doc, path: str, pages=None, text_if_no_tables: bool = True) -> tuple:
    """Tablas del PDF → .xlsx (una hoja por tabla). Sin tablas, el texto por líneas (si se permite).
    Devuelve (hojas, «tablas» | «texto» | None)."""
    sheets = tables(doc, pages)
    how = "tablas" if sheets else None
    if not sheets and text_if_no_tables:
        sheets, how = text_rows(doc, pages), "texto"
    if not sheets: return 0, None
    write_xlsx(path, sheets)
    return len(sheets), how


# ── Markdown ───────────────────────────────────────────────────────────────────
_BULLET = re.compile(r"^\s*[•◦▪▫‣⁃●○■□–—·\-\*]\s+")
_BULLET_MD = re.compile(r"^\s*\\?[•◦▪▫‣⁃●○■□–—·\-\*]\s+")   # la misma viñeta, ya escapada
_NUMBERED = re.compile(r"^\s*(\d{1,3}|[a-zA-Z])[.)]\s+")
_MD_ESC = re.compile(r"([\\`*_\[\]<>|])")


def _md_escape(t: str) -> str:
    return _MD_ESC.sub(r"\\\1", t)


def _sizes(doc, pages) -> tuple:
    """(tamaño del texto normal, {tamaño de título: nivel 1-3}) según cuántos caracteres hay de cada tamaño."""
    count = {}
    for i in pages:
        for b in doc[i].get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for s in ln["spans"]:
                    k = round(s["size"] * 2) / 2
                    count[k] = count.get(k, 0) + len(s["text"].strip())
    if not count: return 0, {}
    body = max(count, key=count.get)
    big = sorted((s for s in count if s >= body * 1.15), reverse=True)[:3]
    return body, {s: n + 1 for n, s in enumerate(big)}


def _span_md(s, uri=None) -> str:
    t = _md_escape(s["text"])
    core = t.strip()
    if not core: return t
    lead, trail = t[:len(t) - len(t.lstrip())], t[len(t.rstrip()):]
    bold = s["flags"] & 16 or "bold" in s["font"].lower()
    italic = s["flags"] & 2 or "italic" in s["font"].lower() or "oblique" in s["font"].lower()
    if s["flags"] & 8 and not (bold or italic): core = f"`{s['text'].strip()}`"      # monoespaciada
    if italic: core = f"*{core}*"
    if bold: core = f"**{core}**"
    if uri: core = f"[{core}]({uri})"
    return lead + core + trail


def _line_md(line, links) -> str:
    out, i, spans = [], 0, line["spans"]
    while i < len(spans):                     # tramos seguidos con el mismo enlace van en un solo [texto](url)
        uri = _link_of(spans[i], links)
        if uri:
            j = i
            while j + 1 < len(spans) and _link_of(spans[j + 1], links) == uri: j += 1
            text = "".join(s["text"] for s in spans[i:j + 1])
            out.append(_span_md(dict(spans[i], text=text), uri)); i = j + 1
        else:
            out.append(_span_md(spans[i])); i += 1
    return "".join(out).replace("****", "").replace("**  **", " ").strip()


def _link_of(span, links):
    r = pymupdf.Rect(span["bbox"])
    c = (r.tl + r.br) / 2
    for l in links:
        if c in l[0]: return l[1]
    return None


def _table_md(rows) -> str:
    rows = [[_md_escape((c or "").strip()).replace("\n", "<br>") for c in r] for r in rows]
    w = max(len(r) for r in rows)
    rows = [r + [""] * (w - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * w) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def _block_md(b, body, levels, links) -> str:
    lines = [ln for ln in b.get("lines", []) if "".join(s["text"] for s in ln["spans"]).strip()]
    if not lines: return ""
    plain = " ".join("".join(s["text"] for s in ln["spans"]).strip() for ln in lines)
    sizes = [round(s["size"] * 2) / 2 for ln in lines for s in ln["spans"] if s["text"].strip()]
    size = max(set(sizes), key=sizes.count)
    if size in levels and len(plain) < 200:
        return "#" * levels[size] + " " + _md_escape(re.sub(r"\s+", " ", plain).strip())
    items, cur = [], ""
    for ln in lines:
        txt = _line_md(ln, links)
        raw = "".join(s["text"] for s in ln["spans"])
        if _BULLET.match(raw):
            if cur: items.append(cur)
            cur = "- " + _BULLET_MD.sub("", txt, count=1)
        elif _NUMBERED.match(raw):
            if cur: items.append(cur)
            m = _NUMBERED.match(raw)
            cur = f"{m.group(1)}. " + txt[len(_md_escape(m.group(0).strip())):].strip() if m.group(1).isdigit() else txt
        elif cur.endswith("-") and txt[:1].islower():     # palabra cortada al final de la línea
            cur = cur[:-1] + txt
        else:
            cur = f"{cur} {txt}" if cur else txt
    items.append(cur)
    sep = "\n" if all(i.startswith("- ") or _NUMBERED.match(i) for i in items) else "\n\n"
    return sep.join(items)


def _is_item(md: str) -> bool:
    return md.startswith("- ") or bool(re.match(r"\d{1,3}\. ", md))


def _join(blocks) -> str:
    """Une los bloques con una línea en blanco; los elementos de una misma lista van seguidos."""
    out = blocks[0]
    for prev, cur in zip(blocks, blocks[1:]):
        out += ("\n" if _is_item(prev.rsplit("\n", 1)[-1]) and _is_item(cur) else "\n\n") + cur
    return out


def to_markdown(doc, path: str, pages=None) -> int:
    """Markdown: títulos (por tamaño de letra), párrafos, negrita/cursiva, listas, tablas y enlaces.
    Las páginas se separan con «---». Las imágenes no se incluyen. Devuelve los caracteres escritos."""
    pages = _pages(doc, pages)
    body, levels = _sizes(doc, pages)
    parts = []
    for i in pages:
        page = doc[i]
        links = [(pymupdf.Rect(l["from"]), l["uri"]) for l in page.get_links() if l.get("uri")]
        try:
            found = page.find_tables().tables
        except Exception:
            found = []
        items = [(t.bbox[1], t.bbox[0], _table_md(t.extract())) for t in found if t.extract()]
        boxes = [pymupdf.Rect(t.bbox) for t in found]
        for b in page.get_text("dict", sort=True)["blocks"]:
            if b.get("type") != 0: continue
            r = pymupdf.Rect(b["bbox"])
            if any(r.intersects(tb) and (r & tb).get_area() > 0.5 * r.get_area() for tb in boxes): continue   # ya está en la tabla
            md = _block_md(b, body, levels, links)
            if md: items.append((r.y0, r.x0, md))
        items.sort(key=lambda x: (round(x[0]), x[1]))
        if items: parts.append(_join([m for _, _, m in items]))
    text = "\n\n---\n\n".join(parts).strip() + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return len(text.strip())
