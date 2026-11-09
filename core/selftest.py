# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Autodiagnóstico del programa empaquetado: `PDFRapid.exe --selftest [informe.txt]`.
Comprueba que los componentes que se cargan bajo demanda (OCR, Word, firma digital, compresión, imágenes)
están incluidos y funcionan. Escribe un informe y termina con código 0 (todo bien) o 1."""
import datetime as dt
import os
import sys
import tempfile
import traceback


def _pdf(d, text="PDFRapid selftest 12345"):
    import pymupdf
    p = os.path.join(d, "t.pdf"); doc = pymupdf.open()
    pg = doc.new_page(); pg.insert_text((72, 100), text, fontsize=28); doc.save(p); doc.close()
    return p


def _ocr(d):
    import pymupdf
    from core import ocr
    doc = pymupdf.open(_pdf(d)); lines = ocr.ocr_page(doc[0])
    txt = " ".join(t for _, t in lines)
    assert "12345" in txt.replace(" ", ""), f"texto leído: {txt!r}"
    return txt


def _word(d):
    from pdf2docx import Converter
    out = os.path.join(d, "t.docx"); cv = Converter(_pdf(d)); cv.convert(out); cv.close()
    assert os.path.getsize(out) > 1000
    return f"{os.path.getsize(out)} bytes"


def _firma(d):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from core import signing
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SELFTEST")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=2)).sign(key, hashes.SHA256()))
    p12 = os.path.join(d, "c.p12")
    with open(p12, "wb") as f:
        f.write(pkcs12.serialize_key_and_certificates(b"t", key, cert, None, serialization.BestAvailableEncryption(b"pw")))
    out = os.path.join(d, "firmado.pdf")
    signing.sign_pdf(_pdf(d), out, p12, "pw", style="qr", qr_url="https://ejemplo.org")
    sigs = signing.list_signatures(out)
    assert sigs and sigs[0]["integra"]
    return sigs[0]["firmante"]


def _herramientas(d):
    import pymupdf
    from core import pdf_tools
    doc = pymupdf.open(_pdf(d))
    pdf_tools.watermark(doc, [0], "SELFTEST")
    pdf_tools.compress(doc, "max")
    files = pdf_tools.export_images(doc, [0], d, "pag", "png", 72)
    return f"{len(files)} imagen(es)"


def _interfaz(d):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["selftest"])
    from ui.main_window import MainWindow
    w = MainWindow(); w._open_path(_pdf(d)); n = len(w._viewer.doc); w._viewer.dirty = False; w.close()
    return f"{n} página(s)"


def _docx_basico(d):
    import docx
    from core import convert
    src, out = os.path.join(d, "b.docx"), os.path.join(d, "b.pdf")
    x = docx.Document(); x.add_paragraph("Selftest docx 777"); x.save(src)
    convert.basic_docx_to_pdf(src, out)
    import pymupdf
    assert "777" in pymupdf.open(out)[0].get_text()
    return "ok"


def _qr(d):
    import pymupdf
    import qrcode
    from core import qr_read
    img = os.path.join(d, "q.png"); qrcode.make("FIRMADO POR: PÉREZ Ñ").save(img)
    doc = pymupdf.open(); doc.new_page().insert_image(pymupdf.Rect(100, 100, 200, 200), filename=img)
    (_, txt), = qr_read.find_qr(doc[0])
    assert txt == "FIRMADO POR: PÉREZ Ñ", txt
    return "ok"


def _token(d):
    import pkcs11                                       # informativo: el módulo está; las bibliotecas dependen del token
    from core import signing
    libs = signing.token_libraries()
    return f"módulo {pkcs11.__name__} disponible; bibliotecas detectadas: {len(libs)}"


def _wincert(d):
    from core import wincert                            # informativo: depende de lo instalado en el equipo
    certs = wincert.list_certs()
    return f"{sum(c['signing'] for c in certs)} certificado(s) de firma en Windows"


def _office(d):
    from core import convert                            # informativo: depende de lo instalado en el equipo
    return ", ".join(f"{k}: {v or 'no disponible'}" for k, v in convert.available().items())


CHECKS = [("Interfaz y visor", _interfaz), ("OCR (RapidOCR)", _ocr), ("Exportar a Word (pdf2docx)", _word),
          ("Firma digital (pyHanko)", _firma), ("Marca de agua, compresión, imágenes", _herramientas),
          ("Word básico (mammoth)", _docx_basico), ("Crear PDF desde Office (conversor)", _office),
          ("Firma con token (PKCS#11)", _token), ("Lupa QR (zxing-cpp)", _qr),
          ("Certificados de Windows", _wincert)]


def run(report: str = None) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    lines, ok = [f"PDFRapid selftest {dt.datetime.now():%Y-%m-%d %H:%M:%S} · Python {sys.version.split()[0]}"], True
    with tempfile.TemporaryDirectory() as d:
        for name, fn in CHECKS:
            try:
                lines.append(f"[OK]    {name}: {fn(d)}")
            except Exception as e:
                ok = False
                lines.append(f"[FALLO] {name}: {e!r}\n" + "".join(traceback.format_exc()))
    lines.append("RESULTADO: " + ("todo correcto" if ok else "hay fallos"))
    text = "\n".join(lines)
    report = report or os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "selftest.txt")
    with open(report, "w", encoding="utf-8") as f: f.write(text)
    print(text)
    return 0 if ok else 1
