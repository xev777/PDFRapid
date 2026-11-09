# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Guardar como PDF/A-2b (ISO 19005-2, nivel B): el formato de archivo a largo plazo que piden muchos trámites y
archivos. Lo que se hace, en una copia del documento:
- incrustar las tipografías que faltan: las 14 estándar (Helvetica, Times…) con sus equivalentes libres de MuPDF
  y las TrueType (Arial, Calibri…) con la del propio Windows;
- perfil de color sRGB como «intención de salida»; las imágenes CMYK se pasan a RGB;
- metadatos XMP que declaran PDF/A-2b y coinciden con las propiedades del documento;
- quitar lo prohibido: cifrado, JavaScript y acciones, adjuntos, XFA, interpolación de imágenes;
- anotaciones imprimibles y con apariencia propia.
Las páginas que no se pueden arreglar (tipografías que no existen en el equipo, colores CMYK en el contenido) se
convierten en imagen con el texto invisible encima, para que sigan siendo buscables. El resultado se puede
comprobar con veraPDF (ver tests/test_pdfa.py)."""
import codecs
import datetime as dt
import glob
import os
import re
import pymupdf

BASE14 = {"helvetica": "helv", "helvetica-oblique": "heit", "helvetica-bold": "hebo", "helvetica-boldoblique": "hebi",
          "times-roman": "tiro", "times-italic": "tiit", "times-bold": "tibo", "times-bolditalic": "tibi",
          "courier": "cour", "courier-oblique": "coit", "courier-bold": "cobo", "courier-boldoblique": "cobi",
          # nombres de Windows para las mismas (Arial ≈ Helvetica, Times New Roman ≈ Times, Courier New ≈ Courier)
          "helv": "helv", "times": "tiro", "timesnewroman": "tiro", "couriernew": "cour"}
SYMBOLIC = {"symbol", "zapfdingbats"}
_CMYK_OP = re.compile(rb"(?:^|\s)-?[\d.]+\s+-?[\d.]+\s+-?[\d.]+\s+-?[\d.]+\s+[kK](?=\s|$)")


# ── tipografías ────────────────────────────────────────────────────────────────────────────────────────────────
_sysfonts = None


def system_fonts() -> dict:
    """{nombre PostScript o «familia,estilo» normalizado: ruta .ttf} de las tipografías de Windows (se lee una vez)."""
    global _sysfonts
    if _sysfonts is not None: return _sysfonts
    _sysfonts = {}
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return _sysfonts
    dirs = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")]
    for path in [p for d in dirs for p in glob.glob(os.path.join(d, "*.ttf"))]:
        try:
            f = TTFont(path, lazy=True, fontNumber=0)
            names = {n.nameID: n.toUnicode() for n in f["name"].names if n.nameID in (1, 2, 4, 6) and n.platformID == 3}
            f.close()
        except Exception:
            continue
        fam, sub = names.get(1, ""), names.get(2, "Regular")
        for key in (names.get(6), names.get(4), f"{fam},{sub}", fam if sub.lower() == "regular" else None):
            if key: _sysfonts.setdefault(_norm(key), path)
    return _sysfonts


def _norm(name: str) -> str:
    """«ABCDEF+Arial,Bold» / «Arial-BoldMT» / «Arial Bold» → «arial,bold» (comparables entre sí)."""
    n = name.split("+", 1)[-1].lower().replace(" ", "")
    n = re.sub(r"(mt|ps|psmt)$", "", n.replace("-", ","))
    n = n.replace("regular", "").rstrip(",")
    return n.replace(",italic", ",italic").replace("oblique", "italic")


def _key(name):
    return name.split("+", 1)[-1]


def _font_program(base: str):
    """(bytes, tipo) del programa de tipografía para `base`: ("cff", …) de MuPDF o ("ttf", …) de Windows."""
    n = _key(base).lower()
    if n in SYMBOLIC:
        return pymupdf.Font("symb" if n == "symbol" else "zadb").buffer, "cff"
    if n in BASE14 or n.replace(",", "-") in BASE14:
        code = BASE14.get(n) or BASE14[n.replace(",", "-")]
        return pymupdf.Font(code).buffer, "cff"
    path = system_fonts().get(_norm(base))
    if path:
        with open(path, "rb") as f: return f.read(), "ttf"
    fam = _norm(base).split(",")[0]                            # p. ej. «Arial,Bold» sin la negrita instalada
    for alias, code in (("arial", "helv"), ("helvetica", "helv"), ("times", "tiro"), ("courier", "cour")):
        if fam.startswith(alias):
            style = _norm(base).split(",")[1:] or [""]
            suffix = {"bold": "bo", "italic": "it", "bolditalic": "bi"}.get(style[0], "")
            code = code if not suffix else code[:2] + {"bo": "bo", "it": "it", "bi": "bi"}[suffix]
            return pymupdf.Font(code).buffer, "cff"
    return None, None


def _encoding_unicodes(doc, x) -> list:
    """Unicode de los códigos 0..255 según la /Encoding de la tipografía simple (WinAnsi si no indica otra)."""
    enc = doc.xref_get_key(x, "Encoding")
    base, diffs = "/WinAnsiEncoding", ""
    if enc[0] == "name": base = enc[1]
    elif enc[0] in ("dict", "xref"):
        src = doc.xref_object(int(enc[1].split()[0])) if enc[0] == "xref" else enc[1]
        m = re.search(r"/BaseEncoding\s*/(\w+)", src); base = "/" + m.group(1) if m else base
        m = re.search(r"/Differences\s*\[(.*?)\]", src, re.S); diffs = m.group(1) if m else ""
    codec = "mac_roman" if base == "/MacRomanEncoding" else "cp1252"
    uni = []
    for c in range(256):
        try: uni.append(ord(codecs.decode(bytes([c]), codec)))
        except Exception: uni.append(None)
    code = 0
    for tok in re.findall(r"/[^\s/\[\]]+|\d+", diffs):
        if tok.isdigit(): code = int(tok); continue
        u = pymupdf.glyph_name_to_unicode(tok[1:])
        if code < 256: uni[code] = u if u and u != 0xFFFD else None
        code += 1
    return uni


def _builtin_widths(data, first, last) -> list:
    """Anchos por código según la codificación propia de una CFF simbólica (Symbol, ZapfDingbats)."""
    import io
    from fontTools.cffLib import CFFFontSet
    from fontTools.pens.basePen import NullPen
    cff = CFFFontSet(); cff.decompile(io.BytesIO(data), None)
    f = cff[cff.fontNames[0]]
    out = []
    for c in range(first, last + 1):
        name = f.Encoding[c] if not isinstance(f.Encoding, str) else ".notdef"
        if name == ".notdef" or name not in f.CharStrings: out.append(0); continue
        cs = f.CharStrings[name]; cs.draw(NullPen())
        out.append(round(cs.width))
    return out


def _embed_simple(doc, x, base, data, kind) -> bool:
    """Incrusta `data` en la tipografía simple `x` y rehace anchos y descriptor para que coincidan."""
    font = pymupdf.Font(fontbuffer=data)
    first, last = 32, 255
    symbolic = _key(base).lower() in SYMBOLIC
    if symbolic:                                       # usan su propia codificación interna
        doc.xref_set_key(x, "Encoding", "null")
        widths = _builtin_widths(data, first, last)
    else:
        uni = _encoding_unicodes(doc, x)
        if doc.xref_get_key(x, "Encoding")[0] == "null":
            doc.xref_set_key(x, "Encoding", "/WinAnsiEncoding")
        widths = [round(font.glyph_advance(u) * 1000) if u and font.has_glyph(u) else 0 for u in uni[first:last + 1]]
    sx = doc.get_new_xref(); doc.update_object(sx, "<<>>")
    doc.update_stream(sx, data)
    if kind == "cff":
        doc.xref_set_key(sx, "Subtype", "/Type1C"); prog_key = "FontFile3"; subtype = "/Type1"
    else:
        doc.xref_set_key(sx, "Length1", str(len(data))); prog_key = "FontFile2"; subtype = "/TrueType"
    bb = font.bbox
    asc, desc = round(font.ascender * 1000), round(font.descender * 1000)
    name = _key(base).replace(" ", "")
    flags = (4 if symbolic else 32) | (64 if re.search(r"italic|oblique", base, re.I) else 0) | (1 if font.is_monospaced else 0)
    fd = doc.get_new_xref()
    doc.update_object(fd, f"<</Type/FontDescriptor/FontName/{name}/Flags {flags}"
                          f"/FontBBox[{round(bb.x0 * 1000)} {round(bb.y0 * 1000)} {round(bb.x1 * 1000)} {round(bb.y1 * 1000)}]"
                          f"/ItalicAngle {-12 if flags & 64 else 0}/Ascent {asc}/Descent {desc}/CapHeight {asc}/StemV 80"
                          f"/{prog_key} {sx} 0 R>>")
    doc.xref_set_key(x, "Subtype", subtype)
    doc.xref_set_key(x, "BaseFont", "/" + name)
    doc.xref_set_key(x, "FirstChar", str(first)); doc.xref_set_key(x, "LastChar", str(last))
    doc.xref_set_key(x, "Widths", "[" + " ".join(map(str, widths)) + "]")
    doc.xref_set_key(x, "FontDescriptor", f"{fd} 0 R")
    return True


def _has_program(doc, fd_ref) -> bool:
    if not fd_ref or fd_ref[0] != "xref": return False
    fd = int(fd_ref[1].split()[0])
    return any(doc.xref_get_key(fd, k)[0] == "xref" for k in ("FontFile", "FontFile2", "FontFile3"))


def embed_fonts(doc) -> tuple:
    """Incrusta las tipografías simples que faltan. Devuelve (incrustadas, imposibles): nombres."""
    done, missing = [], set()
    for x in range(1, doc.xref_length()):
        try:
            if doc.xref_get_key(x, "Type") != ("name", "/Font"): continue
        except Exception:
            continue
        sub = doc.xref_get_key(x, "Subtype")[1]
        base = doc.xref_get_key(x, "BaseFont")[1].lstrip("/")
        if sub == "/Type3": continue
        if sub == "/Type0":
            d = doc.xref_get_key(x, "DescendantFonts")
            m = re.search(r"(\d+) 0 R", d[1])
            dx = int(m.group(1)) if m else None
            if d[0] == "xref":                                     # arreglo indirecto
                m = re.search(r"(\d+) 0 R", doc.xref_object(int(d[1].split()[0]))); dx = int(m.group(1)) if m else None
            if dx and not _has_program(doc, doc.xref_get_key(dx, "FontDescriptor")): missing.add(base)
            elif dx and doc.xref_get_key(dx, "Subtype")[1] == "/CIDFontType2" and doc.xref_get_key(dx, "CIDToGIDMap")[0] == "null":
                doc.xref_set_key(dx, "CIDToGIDMap", "/Identity")      # obligatorio en PDF/A (Identity es el valor implícito)
            continue
        if _has_program(doc, doc.xref_get_key(x, "FontDescriptor")): continue
        data, kind = _font_program(base)
        if data and _embed_simple(doc, x, base, data, kind): done.append(base)
        else: missing.add(base)
    return done, sorted(missing)


# ── color ──────────────────────────────────────────────────────────────────────────────────────────────────────
def srgb_profile() -> bytes:
    from PIL import ImageCms
    icc = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    icc[8:12] = bytes([2, 0x10, 0, 0])            # versión 2.1 en la cabecera: la aceptan PDF/A-1, 2 y 3
    return bytes(icc)


def add_output_intent(doc):
    sx = doc.get_new_xref(); doc.update_object(sx, "<</N 3>>"); doc.update_stream(sx, srgb_profile())
    oi = doc.get_new_xref()
    doc.update_object(oi, f"<</Type/OutputIntent/S/GTS_PDFA1/OutputConditionIdentifier(sRGB IEC61966-2.1)"
                          f"/RegistryName(http://www.color.org)/Info(sRGB IEC61966-2.1)/DestOutputProfile {sx} 0 R>>")
    doc.xref_set_key(doc.pdf_catalog(), "OutputIntents", f"[{oi} 0 R]")


def cmyk_images_to_rgb(doc) -> int:
    n = 0
    for page in doc:
        for img in page.get_images(full=True):
            x = img[0]
            try:
                pix = pymupdf.Pixmap(doc, x)
            except Exception:
                continue
            if pix.n - pix.alpha >= 4:                     # CMYK
                page.replace_image(x, pixmap=pymupdf.Pixmap(pymupdf.csRGB, pix)); n += 1
    return n


def _reachable(doc, x, seen, depth=0):
    if x in seen or depth > 12: return
    seen.add(x)
    try: src = doc.xref_object(x, compressed=False)
    except Exception: return
    for m in re.finditer(r"(\d+) 0 R", src):
        _reachable(doc, int(m.group(1)), seen, depth + 1)


def page_uses_cmyk(doc, page) -> bool:
    if _CMYK_OP.search(page.read_contents() or b""): return True
    seen = set()
    res = doc.xref_get_key(page.xref, "Resources")
    if res[0] == "xref": _reachable(doc, int(res[1].split()[0]), seen)
    else:
        for m in re.finditer(r"(\d+) 0 R", res[1]): _reachable(doc, int(m.group(1)), seen)
    for x in seen:
        src = doc.xref_object(x, compressed=False)
        if "/DeviceCMYK" in src and "/Image" not in src: return True
        if "/Form" in src and doc.xref_is_stream(x) and _CMYK_OP.search(doc.xref_stream(x) or b""): return True
    return False


def fix_form_resources(doc) -> None:
    """Los Form XObject sin /Resources propios heredan los de la página: PDF/A exige que los tengan explícitos."""
    seen = set()

    def walk(res_src, val, depth=0):
        if depth > 8: return
        m = re.search(r"/XObject\s*(<<.*?>>|\d+ 0 R)", res_src, re.S)
        if not m: return
        xo = m.group(1)
        if xo.endswith("R"): xo = doc.xref_object(int(xo.split()[0]), compressed=False)
        for ref in re.findall(r"(\d+) 0 R", xo):
            x = int(ref)
            if x in seen or doc.xref_get_key(x, "Subtype") != ("name", "/Form"): continue
            seen.add(x)
            r = doc.xref_get_key(x, "Resources")
            if r[0] == "null":
                doc.xref_set_key(x, "Resources", val); r = doc.xref_get_key(x, "Resources")
            walk(doc.xref_object(int(r[1].split()[0])) if r[0] == "xref" else r[1], r[1], depth + 1)
    for page in doc:
        r = doc.xref_get_key(page.xref, "Resources")
        if r[0] == "xref": walk(doc.xref_object(int(r[1].split()[0])), r[1])
        elif r[0] == "dict": walk(r[1], r[1])


# ── limpieza ───────────────────────────────────────────────────────────────────────────────────────────────────
def remove_forbidden(doc) -> list:
    """Quita lo que PDF/A prohíbe. Devuelve la lista de cosas quitadas (para informar)."""
    out = []
    cat = doc.pdf_catalog()
    names = doc.xref_get_key(cat, "Names")
    if names[0] != "null":
        nx = int(names[1].split()[0]) if names[0] == "xref" else None
        for k, what in (("JavaScript", "JavaScript"), ("EmbeddedFiles", "adjuntos")):
            if nx and doc.xref_get_key(nx, k)[0] != "null":
                doc.xref_set_key(nx, k, "null"); out.append(what)
            elif not nx and f"/{k}" in names[1]:
                out.append(what)
        if not nx: doc.xref_set_key(cat, "Names", "null")
    for k in ("OpenAction", "AA", "Collection", "Perms", "Threads"):
        if doc.xref_get_key(cat, k)[0] != "null":
            if k != "OpenAction" or "/JavaScript" in doc.xref_get_key(cat, k)[1] or "/Launch" in doc.xref_get_key(cat, k)[1]:
                doc.xref_set_key(cat, k, "null"); out.append({"AA": "acciones automáticas", "OpenAction": "acción al abrir"}.get(k, k))
    af = doc.xref_get_key(cat, "AcroForm")
    if af[0] == "xref":
        fx = int(af[1].split()[0])
        for k in ("XFA", "NeedAppearances"):
            if doc.xref_get_key(fx, k)[0] != "null":
                doc.xref_set_key(fx, k, "null"); out.append("formulario XFA" if k == "XFA" else "")
    for page in doc:
        if doc.xref_get_key(page.xref, "AA")[0] != "null": doc.xref_set_key(page.xref, "AA", "null")
        for a in page.annots() or []:
            ax = a.xref
            flags = a.flags & ~(pymupdf.PDF_ANNOT_IS_HIDDEN | pymupdf.PDF_ANNOT_IS_INVISIBLE | pymupdf.PDF_ANNOT_IS_NO_VIEW)
            a.set_flags(flags | pymupdf.PDF_ANNOT_IS_PRINT)
            for k in ("AA", "A") if a.type[0] != pymupdf.PDF_ANNOT_LINK else ("AA",):
                if doc.xref_get_key(ax, k)[0] != "null" and ("/JavaScript" in doc.xref_get_key(ax, k)[1] or k == "AA"):
                    doc.xref_set_key(ax, k, "null")
            ap = doc.xref_get_key(ax, "AP")
            if ap[0] == "dict":                            # solo la apariencia normal (/N)
                n = re.search(r"/N\s+(\d+ 0 R|<<.*>>)", ap[1], re.S)
                if n: doc.xref_set_key(ax, "AP", f"<</N {n.group(1)}>>")
        for l in page.get_links():
            if l.get("kind") == pymupdf.LINK_LAUNCH or (l.get("kind") == pymupdf.LINK_URI and
                                                         l.get("uri", "").lower().startswith("javascript:")):
                page.delete_link(l); out.append("enlaces que ejecutan programas")
    for x in range(1, doc.xref_length()):
        try:
            if doc.xref_get_key(x, "Interpolate")[1] == "true": doc.xref_set_key(x, "Interpolate", "false")
            s = doc.xref_get_key(x, "S")
            if s == ("name", "/JavaScript") or s == ("name", "/Launch"):
                doc.xref_set_key(x, "S", "/Named"); doc.xref_set_key(x, "N", "/NextPage"); doc.xref_set_key(x, "JS", "null")
            for k in ("Alternates", "OPI"):
                if doc.xref_get_key(x, k)[0] != "null": doc.xref_set_key(x, k, "null")
        except Exception:
            pass
    return sorted({o for o in out if o})


def rasterize_page(doc, pno, dpi=200):
    """Página → imagen RGB con el texto original invisible encima (sigue siendo buscable y copiable)."""
    page = doc[pno]
    rot = page.rotation
    page.set_rotation(0)                                 # imagen y palabras sin girar; el giro se repone al final
    words = page.get_text("words")
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False, annots=True)
    new = doc.new_page(pno, width=page.rect.width, height=page.rect.height)   # página nueva antes de la vieja
    new.insert_image(new.rect, pixmap=pix)
    font = pymupdf.Font(fontbuffer=_text_font())
    new.insert_font(fontname="F0", fontbuffer=font.buffer)
    for x0, y0, x1, y1, txt, *_ in words:
        size = max(min((y1 - y0) * 0.85, 72), 1)
        tl = font.text_length(txt, fontsize=size) or 1
        new.insert_text((x0, y1 - (y1 - y0) * 0.2), txt, fontname="F0", fontsize=size, render_mode=3,
                        morph=(pymupdf.Point(x0, y1), pymupdf.Matrix((x1 - x0) / tl, 1)))
    doc.delete_page(pno + 1)
    doc[pno].set_rotation(rot)


def _text_font() -> bytes:
    """Tipografía para el texto invisible: Arial de Windows o, si no está, la Helvetica libre de MuPDF (incrustada)."""
    p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf")
    if os.path.isfile(p):
        with open(p, "rb") as f: return f.read()
    return pymupdf.Font("helv").buffer


# ── metadatos ──────────────────────────────────────────────────────────────────────────────────────────────────
def _pdf_date(d):
    return d.strftime("D:%Y%m%d%H%M%S") + (d.strftime("%z")[:3] + "'" + d.strftime("%z")[3:] + "'" if d.tzinfo else "Z")


def _xml(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def set_metadata(doc, producer: str):
    now = dt.datetime.now().astimezone().replace(microsecond=0)
    meta = doc.metadata or {}
    title, author, subject, keywords = (meta.get(k) or "" for k in ("title", "author", "subject", "keywords"))
    created = meta.get("creationDate") or _pdf_date(now)
    m = re.match(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?", created)
    try:
        cd = dt.datetime(*[int(g or d) for g, d in zip(m.groups(), (2000, 1, 1, 0, 0, 0))]).replace(tzinfo=now.tzinfo) if m else now
    except ValueError:
        cd = now
    info = {"title": title, "author": author, "subject": subject, "keywords": keywords, "creator": "PDFRapid",
            "producer": producer, "creationDate": _pdf_date(cd), "modDate": _pdf_date(now), "trapped": "", "format": ""}
    doc.set_metadata({k: v for k, v in info.items() if k not in ("format",)})
    iso = lambda d: d.isoformat()
    li = lambda tag, v: f"<{tag}><rdf:Alt><rdf:li xml:lang=\"x-default\">{_xml(v)}</rdf:li></rdf:Alt></{tag}>" if v else ""
    xmp = f"""<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">
<pdfaid:part>2</pdfaid:part><pdfaid:conformance>B</pdfaid:conformance>
{li("dc:title", title)}{li("dc:description", subject)}
{f"<dc:creator><rdf:Seq><rdf:li>{_xml(author)}</rdf:li></rdf:Seq></dc:creator>" if author else ""}
{f"<pdf:Keywords>{_xml(keywords)}</pdf:Keywords>" if keywords else ""}
<pdf:Producer>{_xml(producer)}</pdf:Producer><xmp:CreatorTool>PDFRapid</xmp:CreatorTool>
<xmp:CreateDate>{iso(cd)}</xmp:CreateDate><xmp:ModifyDate>{iso(now)}</xmp:ModifyDate><xmp:MetadataDate>{iso(now)}</xmp:MetadataDate>
</rdf:Description></rdf:RDF></x:xmpmeta>
<?xpacket end="w"?>"""
    doc.set_xml_metadata(xmp)


def is_pdfa(doc) -> str:
    """«PDF/A-2b», etc. si el documento lo declara en sus metadatos XMP; '' si no."""
    try:
        x = doc.get_xml_metadata() or ""
    except Exception:
        return ""
    p = re.search(r"pdfaid:part(?:>|=\")(\d)", x); c = re.search(r"pdfaid:conformance(?:>|=\")(\w)", x)
    return f"PDF/A-{p.group(1)}{c.group(1).lower() if c else ''}" if p else ""


# ── conversión ─────────────────────────────────────────────────────────────────────────────────────────────────
def convert(src, out: str, producer: str = "PDFRapid") -> dict:
    """Guarda `src` (Document de PyMuPDF ya abierto, o ruta) como PDF/A-2b en `out`. No modifica `src`.
    Devuelve un informe: {fuentes, rasterizadas, quitado, cmyk_imagenes}."""
    if isinstance(src, str):
        src = pymupdf.open(src)
    doc = pymupdf.open("pdf", src.tobytes(encryption=pymupdf.PDF_ENCRYPT_NONE, garbage=1))
    rep = {"fuentes": [], "rasterizadas": [], "quitado": remove_forbidden(doc), "cmyk_imagenes": 0}
    if doc.embfile_count():
        for n in doc.embfile_names(): doc.embfile_del(n)
        if "adjuntos" not in rep["quitado"]: rep["quitado"].append("adjuntos")
    for page in doc:                                       # anotaciones sin apariencia propia: se la genera MuPDF
        for a in page.annots() or []:
            try:
                if a.type[0] not in (pymupdf.PDF_ANNOT_LINK, pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_WIDGET) \
                        and doc.xref_get_key(a.xref, "AP/N")[0] == "null":
                    a.update()
            except Exception:
                pass
    fix_form_resources(doc)
    rep["cmyk_imagenes"] = cmyk_images_to_rgb(doc)
    rep["fuentes"], missing = embed_fonts(doc)
    bad = set()
    if missing:
        for pno, page in enumerate(doc):
            if any(f[3] in missing or _key(f[3]) in {_key(m) for m in missing} for f in page.get_fonts(full=True)):
                bad.add(pno)
    for pno, page in enumerate(doc):
        if pno not in bad and page_uses_cmyk(doc, page): bad.add(pno)
    for pno in sorted(bad):
        rasterize_page(doc, pno)
    rep["rasterizadas"] = [p + 1 for p in sorted(bad)]
    if bad:                                                # las tipografías de las páginas nuevas
        embed_fonts(doc)
    add_output_intent(doc)
    set_metadata(doc, producer)
    doc.save(out, garbage=4, deflate=True, clean=False, no_new_id=False)
    doc.close()
    return rep
