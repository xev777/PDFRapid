# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Firma con un certificado instalado en Windows (core/wincert.py). Windows se simula con claves de `cryptography`;
la prueba real solo corre con PDFRAPID_TEST_WINCERT=<huella SHA-1 de un certificado del almacén Personal>."""
import datetime as dt
import os
import pytest
from core import signing, wincert
from tests.test_firma import _pdf


def _fake(kind="rsa", cn="Ana Pérez Ñandú"):
    """(der, sign_fn) que imitan a Windows: sign_fn firma el resumen y, con EC, devuelve DER como wincert."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048) if kind == "rsa" else ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]); now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=5)).sign(key, hashes.SHA256()))

    def sign_fn(digest, h, is_ec):
        alg = utils.Prehashed(getattr(hashes, h.upper())())
        if is_ec:                                            # CNG devuelve r‖s; wincert lo pasa a DER
            r, s = utils.decode_dss_signature(key.sign(digest, ec.ECDSA(alg)))
            return wincert._ecdsa_der(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        return key.sign(digest, padding.PKCS1v15(), alg)
    return cert.public_bytes(serialization.Encoding.DER), sign_fn


@pytest.mark.parametrize("kind", ["rsa", "ec"])
def test_firma_con_certificado_de_windows_simulado(tmp_path, kind):
    der, fn = _fake(kind)
    out = str(tmp_path / "f.pdf")
    name = signing.sign_pdf(_pdf(tmp_path), out, None, None, style="qr", signer=wincert.make_signer("X", fn, der))
    s = signing.list_signatures(out)[0]
    assert name == "Ana Pérez Ñandú" and s["integra"] and s["cubre_todo"]


def test_dialogo_origen_windows(qapp, monkeypatch):
    from ui import signature_ui
    if not wincert.available(): pytest.skip("solo Windows")
    der, fn = _fake()
    certs = [{"thumb": "AB" * 20, "name": "Ana Pérez", "issuer": "Entidad X", "until": dt.datetime(2030, 1, 1), "signing": True},
             {"thumb": "CD" * 20, "name": "localhost", "issuer": "localhost", "until": dt.datetime(2030, 1, 1), "signing": False}]
    monkeypatch.setattr(wincert, "list_certs", lambda: certs)
    monkeypatch.setattr(wincert, "make_signer", lambda thumb: ("firmante", thumb))
    dlg = signature_ui.SignDialog(None, 2)
    dlg.cb_src.setCurrentIndex(dlg.cb_src.findData("windows"))
    assert dlg.cb_wcert.count() == 1 and dlg.cb_wcert.currentData() == "AB" * 20      # el de servidor web no aparece
    assert dlg._form.isRowVisible(dlg._wc_row) and not dlg._form.isRowVisible(dlg.ed_pw)   # Windows pide el PIN
    assert dlg.make_signer() == (("firmante", "AB" * 20), None)


@pytest.mark.skipif(not os.environ.get("PDFRAPID_TEST_WINCERT"), reason="sin certificado de prueba en Windows")
def test_firma_windows_real(tmp_path):
    out = str(tmp_path / "w.pdf")
    signing.sign_pdf(_pdf(tmp_path), out, None, None, signer=wincert.make_signer(os.environ["PDFRAPID_TEST_WINCERT"]))
    assert signing.list_signatures(out)[0]["integra"]
