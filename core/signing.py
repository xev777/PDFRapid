# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Firma digital con certificado (.p12/.pfx) y verificación de firmas, con pyHanko (MIT).
La firma se agrega como actualización incremental: no altera lo que ya estaba firmado."""
from core.i18n import T, Tf
import logging
import os
from datetime import datetime
import pymupdf

# sin conexión no se puede validar la cadena de la entidad emisora: pyHanko lo informa con trazas largas
for _name in ("pyhanko", "pyhanko_certvalidator"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)

POSITIONS = {"br": "Abajo a la derecha", "bl": "Abajo a la izquierda", "tr": "Arriba a la derecha",
             "tl": "Arriba a la izquierda"}
BOX_W, BOX_H, MARGIN = 210, 62, 36
QR_BOX_W, QR_BOX_H = 240, 80          # con código QR hace falta algo más de espacio
STYLES = {"text": "Recuadro con los datos", "qr": "Con código QR"}
SIZES = {0.75: "Pequeño", 1.0: "Normal", 1.3: "Grande", 1.6: "Muy grande"}   # escala del sello visible


def box_size(style="text", scale=1.0):
    """Tamaño (ancho, alto) en puntos del sello visible para un estilo y una escala."""
    w, h = (QR_BOX_W, QR_BOX_H) if style == "qr" else (BOX_W, BOX_H)
    return w * scale, h * scale


def visible_to_pdf_box(page, rect):
    """Recuadro tal como se ve en pantalla (puntos de la página visible) → (x0, y0, x1, y1) en el espacio PDF
    (origen abajo a la izquierda), que es lo que usa pyHanko. Funciona con páginas giradas y recortadas."""
    r = (pymupdf.Rect(rect) * page.derotation_matrix * ~page.transformation_matrix).normalize()
    return (r.x0, r.y0, r.x1, r.y1)


def qr_text(name, when, reason="", location="", url=""):
    """Contenido del código QR: datos legibles con cualquier lector de QR (y la dirección de validación si hay)."""
    lines = [f"FIRMADO POR: {name}", f"FECHA: {when:%d/%m/%Y %H:%M:%S}"]
    if reason: lines.append(f"RAZÓN: {reason}")
    if location: lines.append(f"LUGAR: {location}")
    if url: lines.append(f"VALIDAR EN: {url}")
    return "\n".join(lines)


def page_rotation(path, page_no, password=None) -> int:
    """Rotación (/Rotate) de la página: 0, 90, 180 o 270."""
    d = pymupdf.open(path)
    try:
        if d.needs_pass: d.authenticate(password or "")
        return d[page_no].rotation % 360
    finally:
        d.close()


def _embedded_helvetica_factory():
    """Motor de tipografía de pyHanko que incrusta la Helvetica libre de MuPDF (WinAnsi) con sus anchos reales:
    lo exige PDF/A y no necesita dependencias nuevas (el de pyHanko para TrueType pide uharfbuzz)."""
    from pyhanko.pdf_utils import generic
    from pyhanko.pdf_utils.font.api import ShapeResult
    from pyhanko.pdf_utils.font.basic import SimpleFontEngine, SimpleFontEngineFactory
    font = pymupdf.Font("helv")
    widths = []
    for c in range(32, 256):
        try: u = ord(bytes([c]).decode("cp1252"))
        except UnicodeDecodeError: u = 0
        widths.append(round(font.glyph_advance(u) * 1000) if u and font.has_glyph(u) else 0)
    n = generic.NameObject

    class Engine(SimpleFontEngine):
        def shape(self, txt):
            raw = txt.encode("cp1252", "replace")
            esc = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            adv = sum(widths[b - 32] if b >= 32 else 0 for b in raw) / 1000
            return ShapeResult(graphics_ops=b"(" + esc + b") Tj", x_advance=adv, y_advance=0)

        def as_resource(self):
            prog = generic.StreamObject({n("/Subtype"): n("/Type1C")}, stream_data=font.buffer)
            bb = font.bbox
            fd = generic.DictionaryObject({
                n("/Type"): n("/FontDescriptor"), n("/FontName"): n("/Helvetica"), n("/Flags"): generic.NumberObject(32),
                n("/FontBBox"): generic.ArrayObject(generic.NumberObject(round(v * 1000)) for v in (bb.x0, bb.y0, bb.x1, bb.y1)),
                n("/ItalicAngle"): generic.NumberObject(0), n("/Ascent"): generic.NumberObject(round(font.ascender * 1000)),
                n("/Descent"): generic.NumberObject(round(font.descender * 1000)),
                n("/CapHeight"): generic.NumberObject(718), n("/StemV"): generic.NumberObject(88),
                n("/FontFile3"): self.writer.add_object(prog)})
            return generic.DictionaryObject({
                n("/Type"): n("/Font"), n("/Subtype"): n("/Type1"), n("/BaseFont"): n("/Helvetica"),
                n("/Encoding"): n("/WinAnsiEncoding"), n("/FirstChar"): generic.NumberObject(32),
                n("/LastChar"): generic.NumberObject(255), n("/Widths"): generic.ArrayObject(map(generic.NumberObject, widths)),
                n("/FontDescriptor"): self.writer.add_object(fd)})

    class Factory(SimpleFontEngineFactory):
        def create_font_engine(self, writer, obj_stream=None):
            return Engine(writer, "Helvetica", 0.5)
    return Factory("Helvetica", 0.5)


def stamp_font(path, password=None):
    """Tipografía del sello: Helvetica estándar sin incrustar o, si el documento es PDF/A (exige incrustarlas),
    la Helvetica libre de MuPDF incrustada."""
    from pyhanko.pdf_utils.font.basic import SimpleFontEngineFactory
    from core import pdfa
    d = pymupdf.open(path)
    try:
        if d.needs_pass: d.authenticate(password or "")
        archive = bool(pdfa.is_pdfa(d))
    finally:
        d.close()
    return _embedded_helvetica_factory() if archive else SimpleFontEngineFactory("Helvetica", 0.5)


def upright(style, rotation):
    """Estilo de sello de pyHanko que se ve derecho en una página girada (/Rotate): el sello se dibuja con el
    tamaño visible y se gira al revés con la /Matrix de su XObject (el visor lo ajusta al /Rect del campo)."""
    if not rotation: return style
    import dataclasses
    from pyhanko.pdf_utils import generic, layout
    a, b, c, d = {90: (0, 1, -1, 0), 180: (-1, 0, 0, -1), 270: (0, -1, 1, 0)}[rotation]

    class Upright(type(style)):
        def create_stamp(self, writer, box, text_params):
            if rotation in (90, 270):                     # el /Rect está en el espacio PDF: ancho y alto cambiados
                box = layout.BoxConstraints(width=box.height, height=box.width)
            st = super().create_stamp(writer, box, text_params)
            plain = st.as_form_xobject

            def as_form_xobject():
                x = plain()
                x["/Matrix"] = generic.ArrayObject(generic.FloatObject(v) for v in (a, b, c, d, 0, 0))
                return x
            st.as_form_xobject = as_form_xobject
            return st
    return Upright(**{f.name: getattr(style, f.name) for f in dataclasses.fields(style)})


def signature_box(path, page_no, pos="br", password=None, size=(BOX_W, BOX_H)):
    """Rectángulo (x0, y0, x1, y1) en coordenadas PDF (origen abajo a la izquierda) para la firma visible,
    en una esquina de la página tal como se ve."""
    d = pymupdf.open(path)
    try:
        if d.needs_pass: d.authenticate(password or "")
        pg = d[page_no]; w, h = size; W, H = pg.rect.width, pg.rect.height
        x0 = MARGIN if pos[1] == "l" else W - MARGIN - w
        y0 = MARGIN if pos[0] == "t" else H - MARGIN - h
        return visible_to_pdf_box(pg, (x0, y0, x0 + w, y0 + h))
    finally:
        d.close()


def load_signer(p12_path, password):
    """Firmante desde un certificado .p12/.pfx. ValueError con un mensaje claro si la clave no es correcta."""
    from pyhanko.sign import signers
    with open(p12_path, "rb") as f:
        data = f.read()
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
        pkcs12.load_key_and_certificates(data, password.encode() if password else None)
    except Exception:
        raise ValueError(T("La contraseña del certificado no es correcta o el archivo no es un certificado .p12/.pfx válido."))
    s = signers.SimpleSigner.load_pkcs12(p12_path, passphrase=password.encode() if password else None)
    if s is None:
        raise ValueError(T("No se pudo leer el certificado."))
    return s


# ── tokens USB y tarjetas inteligentes (PKCS#11) ──────────────────────────────
# Bibliotecas PKCS#11 habituales en Windows (las instala el controlador del token o de la tarjeta).
TOKEN_LIBS = {
    "eTPKCS11.dll": "SafeNet eToken", "eps2003csp11.dll": "ePass2003 (Feitian)", "ShuttleCsp11_3003.dll": "Feitian",
    "aetpkss1.dll": "Gemalto / IDPrime / SafeSign", "IDPrimePKCS11.dll": "Thales IDPrime", "opensc-pkcs11.dll": "OpenSC",
    "bit4ipki.dll": "bit4id", "WDPKCS.dll": "Watchdata", "acospkcs11.dll": "ACS", "UsrPkcs11.dll": "DNIe (España)",
    "cmP11.dll": "Certisign / Morpho", "asepkcs.dll": "Athena / ASECard", "SignatureP11.dll": "Charismathics",
    "dkck201.dll": "DigiSign", "TokenP11.dll": "Token genérico",
}


def token_libraries() -> list:
    """[(ruta, nombre)] de las bibliotecas PKCS#11 conocidas que existen en este equipo."""
    dirs = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), d) for d in ("System32", "SysWOW64")]
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if base: dirs += [os.path.join(base, "OpenSC Project", "OpenSC", "pkcs11")]
    out = []
    for d in dirs:
        for dll, name in TOKEN_LIBS.items():
            path = os.path.join(d, dll)
            if os.path.isfile(path) and all(os.path.basename(x[0]).lower() != dll.lower() for x in out):
                out.append((path, name))
    return out


def list_token_certs(lib_path) -> list:
    """Certificados de los tokens conectados: [{slot, token, label, id (hex), name}]. Leerlos no pide PIN."""
    import pkcs11
    from asn1crypto import x509
    lib = pkcs11.lib(lib_path)
    out = []
    for slot in lib.get_slots(token_present=True):
        tok = slot.get_token()
        with tok.open() as sess:
            for c in sess.get_objects({pkcs11.Attribute.CLASS: pkcs11.ObjectClass.CERTIFICATE}):
                try:
                    cert = x509.Certificate.load(c[pkcs11.Attribute.VALUE])
                    name = cert.subject.native.get("common_name") or cert.subject.human_friendly
                    if cert.ca: continue                       # solo certificados de persona, no de la entidad
                except Exception:
                    name = ""
                try: cid = c[pkcs11.Attribute.ID]
                except Exception: cid = b""
                out.append({"slot": slot.slot_id, "token": tok.label.strip(), "label": c[pkcs11.Attribute.LABEL],
                            "id": bytes(cid).hex(), "name": name})
    return out


def open_token_signer(lib_path, slot_id, pin, cert_id_hex):
    """(firmante, sesión) con la clave del token. ValueError claro si el PIN no es correcto. Cerrar la sesión al final."""
    import pkcs11
    from pyhanko.sign.pkcs11 import PKCS11Signer
    lib = pkcs11.lib(lib_path)
    slot = next((s for s in lib.get_slots(token_present=True) if s.slot_id == slot_id), None)
    if slot is None: raise ValueError(T("El token no está conectado."))
    try:
        sess = slot.get_token().open(user_pin=pin)
    except (pkcs11.exceptions.PinIncorrect, pkcs11.exceptions.PinInvalid, pkcs11.exceptions.PinLenRange):
        raise ValueError(T("El PIN del token no es correcto."))
    except pkcs11.exceptions.PinLocked:
        raise ValueError(T("El token está bloqueado por demasiados intentos con PIN incorrecto."))
    cid = bytes.fromhex(cert_id_hex) if cert_id_hex else None
    return PKCS11Signer(sess, cert_id=cid, key_id=cid), sess


def signer_name(signer) -> str:
    return signer.signing_cert.subject.native.get("common_name") or signer.signing_cert.subject.human_friendly


def sign_pdf(src, out, p12_path, password, page_no=None, pos="br", visible=True, reason="", location="",
             pdf_password=None, field_name=None, box=None, style="text", qr_url="", signer=None, tsa_url="",
             scale=1.0, ltv=False):
    """Firma `src` y escribe `out` (PAdES, SHA-256). `page_no` None = última página.
    `box`: recuadro en el espacio PDF (ver `visible_to_pdf_box`); si no, se usa la esquina `pos`.
    `style`: "text" (recuadro con los datos) o "qr" (código QR con los datos y texto al lado, como hacen algunos
    programas oficiales, p. ej. FirmaEC en Ecuador). Es solo la apariencia: la validez está en la firma.
    `signer`: firmante ya abierto (p. ej. un token, ver `open_token_signer`); si no, se usa el .p12.
    `scale`: tamaño del sello en las esquinas y de su letra (ver `SIZES`); con `box`, el tamaño es el del recuadro.
    `ltv`: firma de larga duración (PAdES B-LTA): incluye en el PDF los certificados y los datos de revocación
    (OCSP/CRL, descargados de la entidad) y añade un sello de tiempo del documento. Necesita `tsa_url` e internet.
    `tsa_url`: servidor de sellado de tiempo (RFC 3161). Es lo único que usa internet, y solo si se indica."""
    from pyhanko.sign import signers, fields
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko import stamp
    signer = signer or load_signer(p12_path, password)
    field_name = field_name or f"FirmaPDFRapid_{datetime.now():%Y%m%d%H%M%S}"
    with open(src, "rb") as inf:
        w = IncrementalPdfFileWriter(inf, strict=False)
        if w.prev.encrypted:
            w.encrypt(pdf_password or "")
        n_pages = int(w.root["/Pages"]["/Count"])
        page = n_pages - 1 if page_no is None else page_no
        if visible:
            size = box_size(style, scale)
            fields.append_signature_field(w, fields.SigFieldSpec(
                field_name, on_page=page, box=box or signature_box(src, page, pos, pdf_password, size)))
        if ltv and not tsa_url:
            raise ValueError(T("La firma de larga duración (LTV) necesita un servidor de sellado de tiempo."))
        meta = signers.PdfSignatureMetadata(field_name=field_name, reason=reason or None, location=location or None,
                                            md_algorithm="sha256", subfilter=fields.SigSeedSubFilter.PADES,
                                            embed_validation_info=ltv, use_pades_lta=ltv,
                                            validation_context=make_validation_context(signer) if ltv else None)
        name = signer_name(signer)
        params = {"signer": name}
        from pyhanko.pdf_utils.text import TextBoxStyle
        text = TextBoxStyle(font=stamp_font(src, pdf_password), font_size=round(8 * scale), leading=round(10 * scale))
        if style == "qr":
            st = stamp.QRStampStyle(stamp_text="Firmado electrónicamente por:\n%(signer)s\nFecha: %(ts)s",
                                    border_width=0, innsep=2, text_box_style=text, timestamp_format="%d/%m/%Y %H:%M:%S")
            params["url"] = qr_text(name, datetime.now(), reason, location, qr_url)
        else:
            st = stamp.TextStampStyle(stamp_text="Firmado digitalmente por:\n%(signer)s\nFecha: %(ts)s",
                                      border_width=1, text_box_style=text, timestamp_format="%d/%m/%Y %H:%M:%S %z")
        if visible: st = upright(st, page_rotation(src, page, pdf_password))
        pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=st if visible else None,
                                       timestamper=make_timestamper(tsa_url) if tsa_url else None)
        try:
            with open(out, "wb") as outf:
                pdf_signer.sign_pdf(w, output=outf, appearance_text_params=params if visible else None)
        except Exception as e:
            if not ltv: raise
            try: os.remove(out)
            except OSError: pass
            raise ValueError(Tf("No se pudieron obtener los datos de validación de la entidad para la firma de larga "
                                "duración (¿hay internet?). Puedes firmar sin LTV.\n\nDetalle: {0}", e)) from e
    return signer_name(signer)


def make_validation_context(signer):
    """Contexto para reunir los datos de la firma LTV: descarga (con internet) los certificados intermedios que falten
    y las respuestas OCSP o CRL. Raíces de confianza: las de Windows/del sistema más la raíz que trae el propio
    certificado (las de algunas entidades nacionales no están en Windows). No es una verificación de confianza:
    solo junta los datos para que otros puedan verificar la firma en el futuro."""
    from pyhanko_certvalidator import ValidationContext
    certs = list(signer.cert_registry) + [signer.signing_cert]
    roots = [c for c in certs if c.self_signed]
    return ValidationContext(extra_trust_roots=roots, other_certs=certs, allow_fetching=True, revocation_mode="hard-fail")


def make_timestamper(url):
    """Sello de tiempo de un servidor RFC 3161 (lo ofrecen las entidades de certificación y servicios públicos)."""
    from pyhanko.sign.timestamps import HTTPTimeStamper
    return HTTPTimeStamper(url, timeout=20)


def list_signatures(path, pdf_password=None) -> list:
    """Firmas del PDF: [{nombre, firmante, fecha, integra, cubre_todo, motivo, lugar, emisor, vence, error}].
    «integra»: el contenido firmado no cambió. La confianza en la entidad emisora no se valida (sin conexión)."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext
    out = []
    with open(path, "rb") as f:
        r = PdfFileReader(f, strict=False)
        if r.encrypted:
            r.decrypt(pdf_password or "")
        try:
            sigs = list(r.embedded_signatures)
        except Exception as e:                        # firma dañada: se informa como no válida, sin fallar
            return [{"nombre": "?", "firmante": "", "fecha": None, "integra": False, "cubre_todo": False,
                     "motivo": "", "lugar": "", "emisor": "", "vence": None, "error": str(e)}]
        for sig in sigs:
            info = {"nombre": sig.field_name, "firmante": "", "fecha": None, "integra": False, "cubre_todo": False,
                    "motivo": "", "lugar": "", "emisor": "", "vence": None, "error": "", "sello": False}
            try:
                attrs = sig.signer_info["unsigned_attrs"].native or []
                info["sello"] = any(a["type"] == "signature_time_stamp_token" for a in attrs)
            except Exception:
                pass
            if str(sig.sig_object.get("/Type", "")) == "/DocTimeStamp":   # sello de tiempo del documento (LTV)
                info.update(documento=True, firmante=T("Sello de tiempo del documento"), sello=True)
                try:
                    from pyhanko.sign.validation import validate_pdf_timestamp
                    st = validate_pdf_timestamp(sig, ValidationContext(allow_fetching=False))
                    info.update(fecha=st.timestamp, integra=bool(st.intact and st.valid), cubre_todo=True)
                except Exception as e:
                    info["error"] = str(e)
                out.append(info); continue
            try:
                st = validate_pdf_signature(sig, ValidationContext(allow_fetching=False))
                cert = sig.signer_cert
                info.update(firmante=cert.subject.native.get("common_name") or cert.subject.human_friendly,
                            emisor=cert.issuer.native.get("common_name") or cert.issuer.human_friendly,
                            vence=cert["tbs_certificate"]["validity"]["not_after"].native,
                            fecha=st.signer_reported_dt, integra=bool(st.intact and st.valid),
                            # False: hubo cambios después de firmar (añadir datos LTV o sellos no cuenta como cambio)
                            cubre_todo=st.coverage.name == "ENTIRE_FILE" or getattr(st.modification_level, "name", "")
                            in ("NONE", "LTA_UPDATES"))
                info["ltv"] = "/DSS" in r.root
                obj = sig.sig_object
                info["motivo"] = str(obj.get("/Reason", "")); info["lugar"] = str(obj.get("/Location", ""))
            except Exception as e:
                info["error"] = str(e)
            out.append(info)
    return out


def has_signatures(doc) -> bool:
    """True si el documento (PyMuPDF) tiene firmas digitales aplicadas."""
    try:
        return doc.get_sigflags() > 0 and any(w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE
                                               for p in doc for w in p.widgets())
    except Exception:
        return False
