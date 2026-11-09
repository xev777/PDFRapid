# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Herramientas de documento sin interfaz: proteger, comprimir, imágenes ↔ PDF y formularios."""
import os
import pymupdf

# ── protección ────────────────────────────────────────────────────────────────
PERMS = [  # (clave, bits PDF, texto)
    ("print", pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ, "Imprimir"),
    ("copy", pymupdf.PDF_PERM_COPY, "Copiar texto e imágenes"),
    ("annotate", pymupdf.PDF_PERM_ANNOTATE | pymupdf.PDF_PERM_FORM, "Comentar y rellenar formularios"),
    ("modify", pymupdf.PDF_PERM_MODIFY | pymupdf.PDF_PERM_ASSEMBLE, "Modificar y reorganizar páginas"),
]


def make_crypt(user_pw: str, owner_pw: str, allowed: set) -> dict:
    """Configuración de cifrado (formato de core.pdf_io) para aplicar al guardar."""
    perm = pymupdf.PDF_PERM_ACCESSIBILITY
    for key, bits, _ in PERMS:
        if key in allowed:
            perm |= bits
    return {"user_pw": user_pw or "", "owner_pw": owner_pw or None,
            "only_owner_pw": False, "permissions": perm}


def is_owner_password(path: str, pw: str) -> bool:
    """True si `pw` es la contraseña de propietario del archivo en disco."""
    d = pymupdf.open(path)
    try:
        return bool(d.authenticate(pw) & 4)
    finally:
        d.close()


# ── comprimir ─────────────────────────────────────────────────────────────────
LEVELS = {  # clave: (texto, (ppp, calidad JPEG) o None = sin pérdida)
    "lossless": ("Sin pérdida (solo reorganiza y comprime la estructura)", None),
    "balanced": ("Equilibrado: imágenes a 150 ppp, calidad 75", (150, 75)),
    "max": ("Máximo: imágenes a 96 ppp, calidad 50 (para enviar por correo)", (96, 50)),
}
# garbage=2 (compactar) y no 3/4 (buscar duplicados): en PDFs con ~100 000 objetos la búsqueda de
# duplicados tarda 12-20 min y apenas reduce (medido con un manual de 2859 págs.: 0,9 s frente a 15 min).
SAVE_OPTS = dict(garbage=2, deflate=True, deflate_images=True, deflate_fonts=True, use_objstms=1)


def compress(doc, level: str):
    """Reduce las imágenes del documento (en el propio `doc`) según el nivel.
    Guardarlo después con SAVE_OPTS."""
    target = LEVELS[level][1]
    if target:
        dpi, q = target
        doc.rewrite_images(dpi_threshold=dpi + 15, dpi_target=dpi, quality=q)
    try:
        doc.subset_fonts()                 # deja solo los caracteres usados de cada fuente
    except Exception:
        pass


# ── imágenes ↔ PDF ────────────────────────────────────────────────────────────
A4 = (595, 842)


def images_to_pdf(paths: list):
    """Un PDF con una página A4 por imagen (vertical u horizontal según la imagen), ajustada sin deformar."""
    out = pymupdf.open()
    for p in paths:
        pix = pymupdf.Pixmap(p)
        w, h = A4 if pix.height >= pix.width else A4[::-1]
        page = out.new_page(width=w, height=h)
        page.insert_image(page.rect + (18, 18, -18, -18), filename=p, keep_proportion=True)
    return out


def export_images(doc, pages: list, folder: str, base: str, fmt: str = "png", dpi: int = 150) -> list:
    """Guarda cada página de `pages` como imagen; devuelve las rutas creadas."""
    out = []
    for i in pages:
        path = os.path.join(folder, f"{base}_p{i + 1}.{fmt}")
        pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
        if fmt == "jpg":
            pix.save(path, jpg_quality=90)
        else:
            pix.save(path)
        out.append(path)
    return out


# ── formularios ───────────────────────────────────────────────────────────────
FIELD_TYPES = {pymupdf.PDF_WIDGET_TYPE_TEXT: "text", pymupdf.PDF_WIDGET_TYPE_CHECKBOX: "check",
               pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: "radio", pymupdf.PDF_WIDGET_TYPE_COMBOBOX: "combo",
               pymupdf.PDF_WIDGET_TYPE_LISTBOX: "combo"}


def form_fields(doc) -> list:
    """Campos rellenables: [{page, xref, name, label, kind, value, choices}] en orden de página."""
    out = []
    for page in doc:
        for w in page.widgets():
            kind = FIELD_TYPES.get(w.field_type)
            if not kind:
                continue
            value = w.field_value
            if kind in ("check", "radio"):
                value = value not in (False, None, "", "Off")
            out.append({"page": page.number, "xref": w.xref, "name": w.field_name or "",
                        "label": w.field_label or w.field_name or "", "kind": kind, "value": value,
                        "choices": list(w.choice_values or []), "readonly": bool(w.field_flags & 1)})
    return out


def set_field(doc, page_no: int, xref: int, value):
    """Escribe el valor de un campo y regenera su apariencia."""
    page = doc[page_no]
    w = page.load_widget(xref)
    if w.field_type in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
        w.field_value = w.on_state() if value else "Off"
    elif not value:                                    # PyMuPDF no escribe un valor vacío: borrar el campo
        doc.xref_set_key(xref, "V", "()"); w = page.load_widget(xref)
    else:
        w.field_value = value
    w.update()


# Crear y editar campos. Tipos: text, multiline, check, radio, combo, list.
NEW_KINDS = {"text": pymupdf.PDF_WIDGET_TYPE_TEXT, "multiline": pymupdf.PDF_WIDGET_TYPE_TEXT,
             "check": pymupdf.PDF_WIDGET_TYPE_CHECKBOX, "radio": pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON,
             "combo": pymupdf.PDF_WIDGET_TYPE_COMBOBOX, "list": pymupdf.PDF_WIDGET_TYPE_LISTBOX}
FIELD_SIZE = {"text": (160, 20), "multiline": (220, 60), "check": (14, 14), "radio": (14, 14),
              "combo": (160, 20), "list": (160, 60)}                     # tamaño estándar (pt) con un clic
FF_READONLY, FF_REQUIRED, FF_MULTILINE = 1, 2, 4096
FF_RADIO_GROUP = 32768 | 16384                                           # botón de opción, sin apagar el elegido


def _ref(doc, xref, key):
    t, v = doc.xref_get_key(xref, key)
    return int(v.split()[0]) if t == "xref" else 0


def field_xref(doc, xref) -> int:
    """El campo de un widget: su padre si es un botón de un grupo de opciones, o el propio widget."""
    return _ref(doc, xref, "Parent") or xref


def _flags(doc, fx) -> int:
    t, v = doc.xref_get_key(fx, "Ff")
    return int(v) if t == "int" else 0


def _fields_array(doc):
    """(xref del diccionario AcroForm o 0 si va dentro del catálogo, clave, lista de xrefs de Fields)."""
    cat = doc.pdf_catalog()
    af = _ref(doc, cat, "AcroForm")
    owner, key = (af, "Fields") if af else (cat, "AcroForm/Fields")
    t, v = doc.xref_get_key(owner, key)
    xs = [int(x) for x in v[1:-1].replace("0 R", "").split()] if t == "array" else []
    return owner, key, xs


def _set_fields_array(doc, xs):
    owner, key, _ = _fields_array(doc)
    doc.xref_set_key(owner, key, "[" + " ".join(f"{x} 0 R" for x in xs) + "]")


def field_names(doc) -> set:
    return {w.field_name for pg in doc for w in pg.widgets() if w.field_name}


def unique_name(doc, base: str) -> str:
    names, i = field_names(doc), 1
    while f"{base}{i}" in names: i += 1
    return f"{base}{i}"


def clean_name(name: str) -> str:
    """Nombre válido de campo: sin puntos (separan la jerarquía en PDF) ni paréntesis."""
    return "".join(c for c in (name or "").strip() if c not in ".()\\") or "Campo"


def radio_groups(doc) -> list:
    return sorted({w.field_name for pg in doc for w in pg.widgets()
                   if w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON and w.field_name})


def add_field(doc, page_no: int, box, kind: str, props: dict) -> int:
    """Crea un campo en el recuadro `box` (puntos de la página tal como se ve, aunque esté girada).
    props: name, tooltip, required, readonly, value (texto inicial / casilla marcada), choices, fontsize.
    Los botones de opción con el mismo nombre forman un grupo (solo uno elegido). Devuelve el xref del widget."""
    page = doc[page_no]
    w = pymupdf.Widget()
    w.field_type = NEW_KINDS[kind]
    w.rect = pymupdf.Rect(box) * page.derotation_matrix
    w.field_name = clean_name(props.get("name"))
    w.border_color, w.border_width = (0.55, 0.55, 0.55), 1
    w.fill_color = (1, 1, 1) if kind in ("text", "multiline", "combo", "list") else None
    w.text_fontsize = props.get("fontsize", 0)
    if kind in ("combo", "list"):
        w.choice_values = props.get("choices") or [""]
        w.field_value = props.get("value") or w.choice_values[0]
    elif kind in ("check", "radio"):
        w.field_value = False
    else:
        w.field_value = props.get("value") or ""
    if kind == "multiline": w.field_flags |= FF_MULTILINE
    xref = page.add_widget(w).xref
    if kind == "radio":
        _join_radio_group(doc, xref, w.field_name)
    update_field(doc, page_no, xref, props)
    return xref


def _join_radio_group(doc, xref, name):
    """Agrupa el botón con los otros botones de opción del mismo nombre (un campo padre con /Kids),
    con un estado «encendido» distinto para cada uno."""
    group = next((fx for fx in _fields_array(doc)[2] if fx != xref and doc.xref_get_key(fx, "Kids")[0] == "array"
                  and doc.xref_get_key(fx, "T")[1] == name and _flags(doc, fx) & 32768), 0)
    loose = [x for pg in doc for x in (w.xref for w in pg.widgets()
             if w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON and w.field_name == name)
             if not _ref(doc, x, "Parent")]
    if not group:
        if len(loose) < 2: return
        group = doc.get_new_xref()
        doc.update_object(group, f"<</FT/Btn/Ff {FF_RADIO_GROUP}/T{pymupdf.get_pdf_str(name)}/V/Off/Kids[]>>")
        _set_fields_array(doc, _fields_array(doc)[2] + [group])
    t, v = doc.xref_get_key(group, "Kids")
    kids = [int(x) for x in v[1:-1].replace("0 R", "").split()] if t == "array" else []
    for x in loose:
        n = len(kids) + 1
        _, ap = doc.xref_get_key(x, "AP/N")
        doc.xref_set_key(x, "AP/N", ap.replace("/Yes", f"/Opcion{n}"))
        for k in ("T", "FT", "Ff", "V"): doc.xref_set_key(x, k, "null")
        doc.xref_set_key(x, "AS", "/Off"); doc.xref_set_key(x, "Parent", f"{group} 0 R")
        kids.append(x)
    doc.xref_set_key(group, "Kids", "[" + " ".join(f"{k} 0 R" for k in kids) + "]")
    _set_fields_array(doc, [f for f in _fields_array(doc)[2] if f not in loose])


def field_props(doc, page_no: int, xref: int) -> dict:
    w = doc[page_no].load_widget(xref)
    fx = field_xref(doc, xref); ff = _flags(doc, fx)
    kind = {pymupdf.PDF_WIDGET_TYPE_TEXT: "multiline" if ff & FF_MULTILINE else "text"}.get(
        w.field_type, FIELD_TYPES.get(w.field_type, "text"))
    if w.field_type == pymupdf.PDF_WIDGET_TYPE_LISTBOX: kind = "list"
    t, dv = doc.xref_get_key(fx, "DV")
    return {"kind": kind, "name": w.field_name or "", "tooltip": w.field_label or "",
            "required": bool(ff & FF_REQUIRED), "readonly": bool(ff & FF_READONLY),
            "choices": list(w.choice_values or []), "fontsize": w.text_fontsize or 0,
            "value": dv if t == "string" else "", "rect": tuple(w.rect * doc[page_no].rotation_matrix)}


def update_field(doc, page_no: int, xref: int, props: dict, box=None):
    """Cambia nombre, ayuda, obligatorio, solo lectura, opciones, tamaño de letra, valor inicial y, con `box`
    (puntos de la página visible), la posición y el tamaño."""
    page = doc[page_no]
    fx = field_xref(doc, xref)
    if box is not None:
        w = page.load_widget(xref); w.rect = pymupdf.Rect(box) * page.derotation_matrix; w.update()
    w = page.load_widget(xref)
    if fx == xref:                                       # campo simple: con la API de PyMuPDF
        if "name" in props: w.field_name = clean_name(props["name"])
        if "tooltip" in props: w.field_label = props["tooltip"] or None
        if "fontsize" in props and w.field_type in (pymupdf.PDF_WIDGET_TYPE_TEXT, pymupdf.PDF_WIDGET_TYPE_COMBOBOX,
                                                     pymupdf.PDF_WIDGET_TYPE_LISTBOX):
            w.text_fontsize = props["fontsize"]
        if props.get("choices") and w.field_type in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
            w.choice_values = props["choices"]
            if w.field_value not in props["choices"]: w.field_value = props["choices"][0]
        w.update()
    else:                                                # botón de un grupo: los datos van en el padre
        if "name" in props: doc.xref_set_key(fx, "T", pymupdf.get_pdf_str(clean_name(props["name"])))
        if "tooltip" in props:
            doc.xref_set_key(fx, "TU", pymupdf.get_pdf_str(props["tooltip"]) if props["tooltip"] else "null")
    ff = _flags(doc, fx)
    for key, bit in (("required", FF_REQUIRED), ("readonly", FF_READONLY)):
        if key in props: ff = ff | bit if props[key] else ff & ~bit
    doc.xref_set_key(fx, "Ff", str(ff))
    if "value" in props and w.field_type == pymupdf.PDF_WIDGET_TYPE_TEXT:
        doc.xref_set_key(fx, "DV", pymupdf.get_pdf_str(props["value"]) if props["value"] else "null")


def delete_field(doc, page_no: int, xref: int):
    """Quita el widget y, si era el último botón de su grupo, también el grupo."""
    parent = _ref(doc, xref, "Parent")
    page = doc[page_no]
    page.delete_widget(page.load_widget(xref))
    fields = [f for f in _fields_array(doc)[2] if f != xref]
    if parent:
        t, v = doc.xref_get_key(parent, "Kids")
        kids = [int(x) for x in v[1:-1].replace("0 R", "").split() if int(x) != xref] if t == "array" else []
        doc.xref_set_key(parent, "Kids", "[" + " ".join(f"{k} 0 R" for k in kids) + "]")
        if not kids: fields = [f for f in fields if f != parent]
    _set_fields_array(doc, fields)


def reset_form(doc) -> int:
    """Vacía el formulario: cada campo vuelve a su valor inicial (o queda vacío / sin marcar).
    Devuelve cuántos campos cambiaron."""
    n = 0
    for pg in doc:
        for w in pg.widgets():
            if w.field_type not in FIELD_TYPES: continue
            t, dv = doc.xref_get_key(field_xref(doc, w.xref), "DV")
            dv = dv if t == "string" else ""
            if w.field_type in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
                if w.field_value in (False, None, "", "Off"): continue
                fx = field_xref(doc, w.xref)
                if fx != w.xref:                         # botón de un grupo: el valor está en el padre
                    doc.xref_set_key(w.xref, "AS", "/Off"); doc.xref_set_key(fx, "V", "/Off"); n += 1; continue
                w.field_value = "Off"
            else:
                if (w.field_value or "") == dv: continue
                doc.xref_set_key(w.xref, "V", pymupdf.get_pdf_str(dv))   # PyMuPDF no escribe un valor vacío
                w = pg.load_widget(w.xref)
            w.update(); n += 1
    return n


# ── tachado definitivo (redacción) ────────────────────────────────────────────
def redact(doc, regions: dict, images: bool = True) -> int:
    """Elimina de verdad el contenido bajo cada rect ({página: [Rect sin rotar]}) y lo cubre de negro.
    `images`: también borra los píxeles de las imágenes afectadas. Devuelve cuántas zonas se tacharon."""
    n = 0
    for pno, rects in regions.items():
        page = doc[pno]
        for r in rects:
            page.add_redact_annot(pymupdf.Rect(r), fill=(0, 0, 0)); n += 1
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS if images else pymupdf.PDF_REDACT_IMAGE_NONE)
    return n


def scrub(doc):
    """Quita la información oculta: metadatos, adjuntos, scripts, enlaces a archivos y miniaturas incrustadas."""
    doc.scrub(metadata=True, xml_metadata=True, attached_files=True, embedded_files=True, javascript=True,
              thumbnails=True, reset_fields=False, reset_responses=False, hidden_text=False, redactions=False,
              redact_images=0, remove_links=False)


# ── marca de agua y numeración ────────────────────────────────────────────────
def _rgb(hexcolor):
    h = hexcolor.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def watermark(doc, pages, text, size=60, color="#c62828", opacity=0.25, diagonal=True, behind=False):
    """Texto de marca de agua centrado en cada página (diagonal o horizontal)."""
    for pno in pages:
        page = doc[pno]
        r = page.rect
        w = pymupdf.get_text_length(text, fontname="hebo", fontsize=size)
        c = pymupdf.Point(r.width / 2, r.height / 2) * page.derotation_matrix
        org = pymupdf.Point(c.x - w / 2, c.y + size * 0.35)
        angle = (45 if diagonal else 0) - page.rotation          # se ve igual aunque la página esté rotada
        page.insert_text(org, text, fontname="hebo", fontsize=size, color=_rgb(color),
                         fill_opacity=opacity, overlay=not behind,
                         morph=(c, pymupdf.Matrix(angle)) if angle else None)   # sube de izquierda a derecha


POSITIONS = {"bl": "Pie, izquierda", "bc": "Pie, centro", "br": "Pie, derecha",
             "tl": "Encabezado, izquierda", "tc": "Encabezado, centro", "tr": "Encabezado, derecha"}


def number_pages(doc, pages, fmt="Página {n} de {total}", pos="bc", size=9, start=1, color="#000000", margin=28,
                 date="", name=""):
    """Numeración, Bates o encabezado/pie con texto libre. `fmt` admite {n} (con formato, p. ej. {n:06d}), {total},
    {date} (fecha de hoy) y {name} (nombre del archivo)."""
    import datetime, os
    total = len(pages) + start - 1
    date = date or datetime.date.today().strftime("%d/%m/%Y")
    name = name or os.path.splitext(os.path.basename(doc.name or ""))[0]
    for k, pno in enumerate(pages):
        page = doc[pno]
        text = fmt.format(n=start + k, total=total, date=date, name=name)
        r = page.rect
        w = pymupdf.get_text_length(text, fontname="helv", fontsize=size)
        x = {"l": margin, "c": (r.width - w) / 2, "r": r.width - margin - w}[pos[1]]
        y = margin if pos[0] == "t" else r.height - margin + size
        org = pymupdf.Point(x, y) * page.derotation_matrix
        page.insert_text(org, text, fontname="helv", fontsize=size, color=_rgb(color), rotate=page.rotation)


def background(doc, pages, color=None, image=None, opacity=1.0):
    """Fondo de página detrás del contenido: un color o una imagen estirada a toda la página.
    Solo se ve donde la página es transparente (un PDF escaneado, que es una imagen, lo tapa)."""
    for pno in pages:
        page = doc[pno]
        r = (page.rect * page.derotation_matrix).normalize()          # página visible → coordenadas sin girar
        if image:
            page.insert_image(r, filename=image, keep_proportion=False, overlay=False, rotate=page.rotation)
        elif color:
            page.draw_rect(r, color=None, fill=_rgb(color), fill_opacity=opacity, overlay=False, width=0)


# ── recortar páginas ─────────────────────────────────────────────────────────
def crop_rect(page, left, top, right, bottom):
    """Caja de recorte (coordenadas de la MediaBox, sin rotar) que quita esos márgenes en puntos,
    medidos sobre la página tal como se ve (con su rotación) y sobre el recorte actual."""
    w, h = page.rect.width, page.rect.height
    if left + right >= w - 10 or top + bottom >= h - 10:
        raise ValueError("Los márgenes dejan la página sin contenido")
    vis = pymupdf.Rect(left, top, w - right, h - bottom)
    r = (vis * page.derotation_matrix).normalize()
    cb = page.cropbox
    r = pymupdf.Rect(r.x0 + cb.x0, r.y0 + cb.y0, r.x1 + cb.x0, r.y1 + cb.y0)
    return r & page.mediabox


def content_margins(page, pad=6.0, dpi=40):
    """Márgenes en blanco (izq, sup, der, inf) en puntos de la página tal como se ve, dejando `pad` de aire."""
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, annots=False)
    w, h, s = pix.width, pix.height, pix.samples
    rows = [y for y in range(h) if min(s[y * pix.stride: y * pix.stride + w]) < 240]
    if not rows: return 0.0, 0.0, 0.0, 0.0
    cols = [x for x in range(w) if any(s[y * pix.stride + x] < 240 for y in range(rows[0], rows[-1] + 1, 2))]
    k = page.rect.width / w
    left, top = max(cols[0] * k - pad, 0), max(rows[0] * k - pad, 0)
    right, bottom = max(page.rect.width - (cols[-1] + 1) * k - pad, 0), max(page.rect.height - (rows[-1] + 1) * k - pad, 0)
    return left, top, right, bottom


# ── enlaces ──────────────────────────────────────────────────────────────────
def list_links(doc) -> list:
    """Enlaces a páginas y a la web: [{page, index, rect (página visible), kind 'page'|'uri', target}]."""
    out = []
    for page in doc:
        for i, l in enumerate(page.get_links()):
            if l.get("kind") == pymupdf.LINK_GOTO and l.get("page", -1) >= 0:
                kind, target = "page", l["page"]
            elif l.get("kind") == pymupdf.LINK_URI:
                kind, target = "uri", l.get("uri", "")
            else:
                continue
            out.append({"page": page.number, "index": i, "rect": tuple(l["from"]),
                        "kind": kind, "target": target})
    return out


def _link_dict(page, box, kind, target):
    d = {"from": pymupdf.Rect(box) * page.derotation_matrix}  # PyMuPDF: insert_link pide coordenadas sin girar,
                                                              # get_links devuelve las de la página visible
    if kind == "page":
        d.update(kind=pymupdf.LINK_GOTO, page=int(target), to=pymupdf.Point(0, 0))
    else:
        d.update(kind=pymupdf.LINK_URI, uri=str(target).strip())
    return d


def add_link(doc, page_no: int, box, kind: str, target):
    """Enlace en el recuadro `box` (página visible) a una página (índice desde 0) o a una dirección web."""
    page = doc[page_no]
    page.insert_link(_link_dict(page, box, kind, target))


def update_link(doc, page_no: int, index: int, kind: str, target):
    page = doc[page_no]
    old = page.get_links()[index]
    page.delete_link(old)
    page.insert_link(_link_dict(page, old["from"], kind, target))


def delete_link(doc, page_no: int, index: int):
    page = doc[page_no]
    page.delete_link(page.get_links()[index])
