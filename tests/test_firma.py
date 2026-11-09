# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import datetime as dt
import pymupdf
import pytest

pytest.importorskip("pyhanko")
from core import signing  # noqa: E402


def _cert(tmp_path, pw="clave123"):
    """Certificado de prueba autofirmado en un .p12 (como los que entregan las entidades acreditadas)."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "FERNANDO ERAZO PRUEBA")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=365))
            .add_extension(x509.KeyUsage(True, True, False, False, False, False, False, False, False), critical=True)
            .sign(key, hashes.SHA256()))
    p = tmp_path / "cert.p12"
    p.write_bytes(pkcs12.serialize_key_and_certificates(b"prueba", key, cert, None,
                                                        serialization.BestAvailableEncryption(pw.encode())))
    return str(p)


def _pdf(tmp_path, n=2):
    p = str(tmp_path / "doc.pdf"); d = pymupdf.open()
    for i in range(n): d.new_page().insert_text((72, 72), f"Contrato pagina {i + 1}")
    d.save(p); return p


def test_firmar_y_verificar(tmp_path):
    src, p12 = _pdf(tmp_path), _cert(tmp_path)
    out = str(tmp_path / "firmado.pdf")
    nombre = signing.sign_pdf(src, out, p12, "clave123", reason="Aprobación", location="Quito")
    assert nombre == "FERNANDO ERAZO PRUEBA"
    sigs = signing.list_signatures(out)
    assert len(sigs) == 1 and sigs[0]["integra"] and sigs[0]["firmante"] == nombre
    assert sigs[0]["motivo"] == "Aprobación" and sigs[0]["lugar"] == "Quito"
    d = pymupdf.open(out)
    assert signing.has_signatures(d) and "Firmado digitalmente" in d[-1].get_text()   # firma visible


def test_firma_detecta_modificacion(tmp_path):
    src, p12 = _pdf(tmp_path), _cert(tmp_path)
    out = str(tmp_path / "firmado.pdf"); signing.sign_pdf(src, out, p12, "clave123")
    data = bytearray(open(out, "rb").read())
    i = data.find(b"Contrato pagina 1")
    if i < 0:                                   # texto comprimido: alterar un byte del contenido firmado
        i = len(data) // 3
    data[i] ^= 0x01
    bad = str(tmp_path / "alterado.pdf"); open(bad, "wb").write(bytes(data))
    sigs = signing.list_signatures(bad)
    assert sigs and not sigs[0]["integra"]


def test_clave_incorrecta(tmp_path):
    with pytest.raises(ValueError):
        signing.load_signer(_cert(tmp_path), "mala")


def test_firmar_desde_la_app_y_panel(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox
    from ui.main_window import MainWindow
    from ui import signature_ui
    src, p12 = _pdf(tmp_path), _cert(tmp_path)
    out = str(tmp_path / "doc_firmado.pdf")
    w = MainWindow(); w.show(); w._open_path(src)

    def exec_(self):
        self.ed_cert.setText(p12); self.ed_pw.setText("clave123"); self.ed_loc.setText("Quito")
        self.cb_pos.setCurrentIndex(self.cb_pos.findData("br")); self.cb_style.setCurrentIndex(self.cb_style.findData("text"))
        self.cb_src.setCurrentIndex(self.cb_src.findData("file")); self.cb_tsa.setChecked(False)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(signature_ui.SignDialog, "exec", exec_)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    signature_ui.sign_document(w)
    assert w._viewer.path == out and w._dock_sigs.isVisibleTo(w)
    assert w._sigs.count == 1 and "Íntegra" in w._sigs.lst.item(0).text()
    preguntas = []                                              # guardar un PDF firmado avisa (y aquí se cancela)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: preguntas.append(a) or QMessageBox.StandardButton.No)
    assert not w.save_pdf() and preguntas


def test_firma_con_qr_ubicada_con_el_raton(qapp, tmp_path, monkeypatch):
    """Elegir la posición arrastrando un recuadro en la página; apariencia con código QR."""
    from PyQt6.QtCore import Qt, QPointF, QEvent
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QDialog, QFileDialog, QApplication
    from ui.main_window import MainWindow
    from ui.canvas import PageCanvas
    from ui import signature_ui
    src, p12 = _pdf(tmp_path), _cert(tmp_path)
    out = str(tmp_path / "qr_firmado.pdf")
    w = MainWindow(); w.show(); w._open_path(src); qapp.processEvents()

    def exec_(self):
        self.ed_cert.setText(p12); self.ed_pw.setText("clave123")
        self.cb_pos.setCurrentIndex(self.cb_pos.findData("pick")); self.cb_style.setCurrentIndex(self.cb_style.findData("qr"))
        self.ed_url.setText("https://ejemplo.org/validar")
        self.cb_src.setCurrentIndex(self.cb_src.findData("file")); self.cb_tsa.setChecked(False)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(signature_ui.SignDialog, "exec", exec_)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    signature_ui.sign_document(w)
    assert PageCanvas.pick_box is not None and w._viewer.path == src       # espera a que se elija el recuadro
    cv = w._viewer.canvases[0]; k = cv._gk()
    a, b = QPointF(100 * k, 120 * k), QPointF(340 * k, 200 * k)            # recuadro de 240 × 80 pt en (100, 120)
    for t, p, btn in ((QEvent.Type.MouseButtonPress, a, Qt.MouseButton.LeftButton),
                      (QEvent.Type.MouseMove, b, Qt.MouseButton.LeftButton),
                      (QEvent.Type.MouseButtonRelease, b, Qt.MouseButton.NoButton)):
        QApplication.sendEvent(cv, QMouseEvent(t, p, cv.mapToGlobal(p), Qt.MouseButton.LeftButton, btn, Qt.KeyboardModifier.NoModifier))
    qapp.processEvents()
    assert PageCanvas.pick_box is None and w._viewer.path == out
    d = pymupdf.open(out); r = next(d[0].widgets()).rect
    assert abs(r.x0 - 100) < 1.5 and abs(r.y0 - 120) < 1.5 and abs(r.x1 - 340) < 1.5 and abs(r.y1 - 200) < 1.5
    assert signing.list_signatures(out)[0]["integra"]
    assert "VALIDAR EN: https://ejemplo.org/validar" in signing.qr_text("X", __import__("datetime").datetime.now(), url="https://ejemplo.org/validar")


@pytest.mark.parametrize("rot", [0, 90])
def test_recuadro_de_firma_en_pagina_girada(tmp_path, rot):
    d = pymupdf.open(); pg = d.new_page(width=600, height=800); pg.set_rotation(rot)
    box = signing.visible_to_pdf_box(pg, (100, 100, 300, 180))
    back = (pymupdf.Rect(box) * pg.transformation_matrix * pg.rotation_matrix).normalize()
    assert back == pymupdf.Rect(100, 100, 300, 180)


def _tsa():
    """Servidor de sellado de prueba (sin red): certificado propio con uso «timeStamping»."""
    from asn1crypto import x509 as ax, keys as ak
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from pyhanko.sign.timestamps import DummyTimeStamper
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TSA PRUEBA")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30))
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
            .sign(key, hashes.SHA256()))
    return DummyTimeStamper(tsa_cert=ax.Certificate.load(cert.public_bytes(serialization.Encoding.DER)),
                            tsa_key=ak.PrivateKeyInfo.load(key.private_bytes(serialization.Encoding.DER,
                                                           serialization.PrivateFormat.PKCS8, serialization.NoEncryption())))


def test_sello_de_tiempo(tmp_path, monkeypatch):
    usadas = []
    monkeypatch.setattr(signing, "make_timestamper", lambda url: usadas.append(url) or _tsa())
    src, p12 = _pdf(tmp_path), _cert(tmp_path)
    out = str(tmp_path / "sellado.pdf")
    signing.sign_pdf(src, out, p12, "clave123", tsa_url="http://tsa.ejemplo.org")
    assert usadas == ["http://tsa.ejemplo.org"]
    from pyhanko.pdf_utils.reader import PdfFileReader
    with open(out, "rb") as f:
        sig = PdfFileReader(f).embedded_signatures[0]
        attrs = sig.signer_info["unsigned_attrs"].native or []
        assert any(x["type"] == "signature_time_stamp_token" for x in attrs)   # el sello quedó dentro de la firma
    assert signing.list_signatures(out)[0]["integra"]


def test_firmar_con_token_simulado(qapp, tmp_path, monkeypatch):
    """Flujo de la app con un token: detectar certificados, PIN, firmar y cerrar la sesión (token simulado)."""
    from PyQt6.QtWidgets import QDialog, QFileDialog
    from ui.main_window import MainWindow
    from ui import signature_ui
    src, p12 = _pdf(tmp_path), _cert(tmp_path)
    lib = tmp_path / "token.dll"; lib.write_bytes(b"")
    cerrada = []

    class Sesion:
        def close(self): cerrada.append(True)
    monkeypatch.setattr(signing, "list_token_certs", lambda path: [
        {"slot": 1, "token": "MI TOKEN", "label": "firma", "id": "01ab", "name": "FERNANDO ERAZO PRUEBA"}])

    def abrir(path, slot, pin, cid):
        assert (path, slot, cid) == (str(lib), 1, "01ab")
        if pin != "1234": raise ValueError("El PIN del token no es correcto.")
        return signing.load_signer(p12, "clave123"), Sesion()
    monkeypatch.setattr(signing, "open_token_signer", abrir)
    out = str(tmp_path / "token_firmado.pdf")
    w = MainWindow(); w.show(); w._open_path(src)

    def exec_(self):
        self.cb_src.setCurrentIndex(self.cb_src.findData("token"))
        self.cb_lib.setEditText(str(lib)); self._detect()
        assert self.cb_tcert.count() == 1 and self.lbl_pw.text() == "PIN:"
        self.ed_pw.setText("1234"); self.cb_pos.setCurrentIndex(self.cb_pos.findData("br"))
        self.cb_tsa.setChecked(False)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(signature_ui.SignDialog, "exec", exec_)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    signature_ui.sign_document(w)
    assert w._viewer.path == out and cerrada and signing.list_signatures(out)[0]["integra"]


@pytest.mark.skipif(not __import__("os").environ.get("PDFRAPID_TEST_PKCS11"),
                    reason=r"Sin token real: define PDFRAPID_TEST_PKCS11=ruta\de\la\biblioteca.dll y PDFRAPID_TEST_PIN")
def test_token_real(tmp_path):
    import os
    lib, pin = os.environ["PDFRAPID_TEST_PKCS11"], os.environ.get("PDFRAPID_TEST_PIN", "")
    certs = signing.list_token_certs(lib)
    assert certs, "el token no tiene certificados"
    signer, sess = signing.open_token_signer(lib, certs[0]["slot"], pin, certs[0]["id"])
    try:
        out = str(tmp_path / "real.pdf")
        signing.sign_pdf(_pdf(tmp_path), out, None, None, signer=signer, style="qr")
    finally:
        sess.close()
    assert signing.list_signatures(out)[0]["integra"]


def test_firma_recuadro_sigue_al_raton_y_clic_la_coloca(qapp, tmp_path):
    """Al elegir dónde firmar se ve un recuadro del tamaño de la firma bajo el ratón; un clic la deja ahí."""
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    from ui.canvas import PageCanvas
    from ui.main_window import MainWindow
    win = MainWindow(); win.show(); win._open_path(_pdf(tmp_path)); qapp.processEvents()
    got = []
    PageCanvas.pick_box = (lambda page, box: got.append((page, box)), (240, 80))
    try:
        cv = win._viewer.canvases[0]; k = cv._gk()
        def ev(t, p, btn, btns):
            QApplication.sendEvent(cv, QMouseEvent(t, p, cv.mapToGlobal(p), btn, btns, Qt.KeyboardModifier.NoModifier))
        p = QPointF(300 * k, 400 * k)
        ev(QEvent.Type.MouseMove, p, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton)
        assert cv._pick_ghost is not None and not cv.grab().isNull()          # se dibuja la vista previa
        ev(QEvent.Type.MouseButtonPress, p, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        ev(QEvent.Type.MouseButtonRelease, p, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
        assert got and got[0][0] == 0 and cv._pick_ghost is None
        x0, y0, x1, y1 = got[0][1]
        assert abs(x0 - 180) < 1 and abs(y0 - 360) < 1 and abs(x1 - 420) < 1 and abs(y1 - 440) < 1   # centrado en el clic
        PageCanvas.pick_box = (lambda page, box: got.append((page, box)), (240, 80))
        p = QPointF(2, 2)                                                      # en la esquina: no se sale de la página
        ev(QEvent.Type.MouseButtonPress, p, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        ev(QEvent.Type.MouseButtonRelease, p, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
        assert got[1][1][0] == 0 and got[1][1][1] == 0
    finally:
        PageCanvas.pick_box = None; win._viewer.dirty = False


@pytest.mark.parametrize("escala", [0.75, 1.6])
def test_firma_tamano_y_lupa_qr(qapp, tmp_path, escala):
    """El tamaño elegido cambia el sello; la lupa QR lee su contenido (con tildes) y lo copia con un clic."""
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent, QGuiApplication
    from PyQt6.QtWidgets import QApplication
    from core import qr_read
    from core.constants import T_QRLENS
    from ui import qr_lens
    from ui.main_window import MainWindow
    src, p12, out = _pdf(tmp_path), _cert(tmp_path), str(tmp_path / "f.pdf")
    signing.sign_pdf(src, out, p12, "clave123", page_no=0, pos="br", style="qr", reason="Aprobación", scale=escala)
    d = pymupdf.open(out); r = next(d[0].widgets()).rect
    w0, h0 = signing.box_size("qr", escala)
    assert abs(r.width - w0) < 1 and abs(r.height - h0) < 1
    (qr, txt), = qr_read.find_qr(d[0]); d.close()
    assert "RAZÓN: Aprobación" in txt and qr.intersects(r)
    win = MainWindow(); win.show(); win._open_path(out); qapp.processEvents()
    v = win._viewer; v.set_tool(T_QRLENS); cv = v.canvases[0]; k = cv._gk()
    p = QPointF(qr.x0 * k + qr.width * k / 2, qr.y0 * k + qr.height * k / 2)
    for t, btn in ((QEvent.Type.MouseMove, Qt.MouseButton.NoButton), (QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton)):
        QApplication.sendEvent(cv, QMouseEvent(t, p, cv.mapToGlobal(p), btn, btn, Qt.KeyboardModifier.NoModifier))
    assert qr_lens.lens().isVisible() and qr_lens.lens().text == txt
    assert QGuiApplication.clipboard().text() == txt
    v.set_tool("select"); assert not qr_lens.lens().isVisible()


@pytest.mark.parametrize("rot", [90, 180, 270])
def test_firma_derecha_en_pagina_girada(tmp_path, rot):
    """En páginas giradas (p. ej. horizontales escaneadas) el sello se ve derecho, no girado con la página."""
    src, p12, out = str(tmp_path / "g.pdf"), _cert(tmp_path), str(tmp_path / "f.pdf")
    d = pymupdf.open(); d.new_page().set_rotation(rot); d.save(src); d.close()
    signing.sign_pdf(src, out, p12, "clave123", page_no=0, pos="br", style="qr")
    pg = pymupdf.open(out)[0]
    m = pg.rotation_matrix; m = pymupdf.Matrix(m.a, m.b, m.c, m.d, 0, 0)         # solo el giro
    dirs = [pymupdf.Point(l["dir"]) * m for b in pg.get_text("dict")["blocks"] for l in b.get("lines", [])
            if "Firmado" in "".join(s["text"] for s in l["spans"])]
    assert dirs and abs(dirs[0].x - 1) < 1e-3 and abs(dirs[0].y) < 1e-3          # texto horizontal tal como se ve
    vis = next(pg.widgets()).rect * pg.rotation_matrix
    w, h = signing.box_size("qr")
    assert abs(vis.width - w) < 1 and abs(vis.height - h) < 1                       # y apaisado, como en una página normal
    assert signing.list_signatures(out)[0]["integra"]


def test_botones_firma_y_lupa_en_barra(qapp, tmp_path, monkeypatch):
    from core.constants import T_QRLENS, T_SELECT
    from ui import signature_ui
    from ui.main_window import MainWindow
    w = MainWindow(); w._open_path(_pdf(tmp_path)); qapp.processEvents()
    w._btn_qrlens.click()
    assert w.toolbox.current == T_QRLENS and w._btn_qrlens.isChecked()
    w._btn_qrlens.click()
    assert w.toolbox.current == T_SELECT and not w._btn_qrlens.isChecked()
    llamado = []
    monkeypatch.setattr(signature_ui, "sign_document", lambda win: llamado.append(win))
    b = next(b for b in w.findChildren(__import__("PyQt6.QtWidgets", fromlist=["x"]).QToolButton)
             if b.toolTip() == __import__("core.i18n", fromlist=["x"]).T("Firmar con certificado digital…"))
    b.click(); assert llamado == [w]
    w._viewer.dirty = False


def _pki(tmp_path, pw="clave123"):
    """Entidad de prueba (raíz) que emite el certificado del firmante con su CRL. Devuelve (p12, ca, crl)."""
    from asn1crypto import x509 as ax, crl as acrl
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    now = dt.datetime.now(dt.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ENTIDAD DE PRUEBA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=10))
          .not_valid_after(now + dt.timedelta(days=365))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    url = "http://crl.ejemplo.org/entidad.crl"
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ana Pérez")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=100))
            .add_extension(x509.KeyUsage(True, True, False, False, False, False, False, False, False), critical=True)
            .add_extension(x509.CRLDistributionPoints([x509.DistributionPoint([x509.UniformResourceIdentifier(url)],
                                                                               None, None, None)]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    crl = (x509.CertificateRevocationListBuilder().issuer_name(ca_name).last_update(now - dt.timedelta(hours=1))
           .next_update(now + dt.timedelta(days=7)).sign(ca_key, hashes.SHA256()))
    p12 = str(tmp_path / "ana.p12")
    with open(p12, "wb") as f:
        f.write(pkcs12.serialize_key_and_certificates(b"ana", key, leaf, [ca],
                                                      serialization.BestAvailableEncryption(pw.encode())))
    return (p12, ax.Certificate.load(ca.public_bytes(serialization.Encoding.DER)),
            acrl.CertificateList.load(crl.public_bytes(serialization.Encoding.DER)))


def test_firma_larga_duracion_ltv(tmp_path, monkeypatch):
    """LTV (PAdES B-LTA): CRL y certificados en el DSS del PDF + sello de tiempo del documento. Sin red: la CRL se
    entrega de antemano (en uso real se descarga de la entidad)."""
    from pyhanko_certvalidator import ValidationContext
    from pyhanko.pdf_utils.reader import PdfFileReader
    p12, ca, crl = _pki(tmp_path)
    tsa = _tsa()
    monkeypatch.setattr(signing, "make_timestamper", lambda url: tsa)
    real = signing.make_validation_context
    def vc(signer):
        base = real(signer)                                   # comprobar que trae la raíz del propio certificado
        assert any(c.sha256 == ca.sha256 for c in signer.cert_registry)
        return ValidationContext(trust_roots=[ca, tsa.tsa_cert], crls=[crl], allow_fetching=False,
                                 revocation_mode="hard-fail") if base else None
    monkeypatch.setattr(signing, "make_validation_context", vc)
    out = str(tmp_path / "ltv.pdf")
    with pytest.raises(ValueError):                            # sin servidor de sellado no hay LTV
        signing.sign_pdf(_pdf(tmp_path), out, p12, "clave123", ltv=True)
    signing.sign_pdf(_pdf(tmp_path), out, p12, "clave123", style="qr", tsa_url="http://tsa.ejemplo.org", ltv=True)
    with open(out, "rb") as f:
        r = PdfFileReader(f)
        dss = r.root["/DSS"]
        assert len(dss["/CRLs"]) >= 1 and len(dss["/Certs"]) >= 2           # datos de revocación y cadena
        assert [str(s.sig_object["/Type"]) for s in r.embedded_signatures] == ["/Sig", "/DocTimeStamp"]
    firma, sello = signing.list_signatures(out)
    assert firma["integra"] and firma["cubre_todo"] and firma["ltv"] and firma["sello"]   # el DSS no cuenta como cambio
    assert sello.get("documento") and sello["integra"]


def test_dialogo_ltv_requiere_sello(qapp):
    from ui import signature_ui
    dlg = signature_ui.SignDialog(None, 1)
    dlg.cb_tsa.setChecked(False); dlg.cb_ltv.setChecked(True)
    assert dlg.cb_tsa.isChecked()                       # LTV activa el sello de tiempo
    dlg.cb_tsa.setChecked(False)
    assert not dlg.cb_ltv.isChecked()                   # y sin sello no hay LTV
