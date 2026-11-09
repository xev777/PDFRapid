# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Firmar con un certificado instalado en Windows (almacén «Personal» del usuario).
Muchos tokens y tarjetas inteligentes registran ahí su certificado al conectarse, y las entidades de certificación
suelen instalarlo así: no hace falta el archivo .p12 ni la biblioteca PKCS#11. La clave privada nunca sale de
Windows (o del token): se le pide firmar el resumen con CNG (NCryptSignHash), y Windows muestra su propia
ventana de PIN si el dispositivo la necesita. Solo Windows; sin dependencias nuevas (ctypes)."""
import asyncio
import ctypes
import hashlib
import sys
from ctypes import wintypes as wt
from core.i18n import T, Tf

CERT_STORE_PROV_SYSTEM_W = 10
CERT_SYSTEM_STORE_CURRENT_USER = 0x00010000
CERT_STORE_READONLY_FLAG = 0x00008000
CERT_STORE_OPEN_EXISTING_FLAG = 0x00004000
CERT_KEY_PROV_INFO_PROP_ID = 2
CRYPT_ACQUIRE_ONLY_NCRYPT_KEY_FLAG = 0x00040000
CRYPT_ACQUIRE_SILENT_FLAG = 0x00000040
BCRYPT_PAD_PKCS1 = 0x2
NTE_USER_CANCELLED = 0x80090036
SCARD_W_CANCELLED_BY_USER = 0x8010006E


_NOT_DOCS = {"server_auth", "code_signing", "time_stamping", "ocsp_signing"}   # usos que no son para firmar documentos


class CERT_CONTEXT(ctypes.Structure):
    _fields_ = [("dwCertEncodingType", wt.DWORD), ("pbCertEncoded", ctypes.POINTER(ctypes.c_ubyte)),
                ("cbCertEncoded", wt.DWORD), ("pCertInfo", ctypes.c_void_p), ("hCertStore", ctypes.c_void_p)]


PCCERT_CONTEXT = ctypes.POINTER(CERT_CONTEXT)


class BCRYPT_PKCS1_PADDING_INFO(ctypes.Structure):
    _fields_ = [("pszAlgId", wt.LPCWSTR)]


def available() -> bool:
    return sys.platform == "win32"


def _libs():
    c32, nc = ctypes.WinDLL("crypt32", use_last_error=True), ctypes.WinDLL("ncrypt")
    c32.CertOpenStore.restype = ctypes.c_void_p
    c32.CertOpenStore.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.LPCWSTR]
    c32.CertEnumCertificatesInStore.restype = PCCERT_CONTEXT
    c32.CertEnumCertificatesInStore.argtypes = [ctypes.c_void_p, PCCERT_CONTEXT]
    c32.CertGetCertificateContextProperty.argtypes = [PCCERT_CONTEXT, wt.DWORD, ctypes.c_void_p, ctypes.POINTER(wt.DWORD)]
    c32.CertDuplicateCertificateContext.restype = PCCERT_CONTEXT
    c32.CertDuplicateCertificateContext.argtypes = [PCCERT_CONTEXT]
    c32.CertFreeCertificateContext.argtypes = [PCCERT_CONTEXT]
    c32.CertCloseStore.argtypes = [ctypes.c_void_p, wt.DWORD]
    c32.CryptAcquireCertificatePrivateKey.argtypes = [PCCERT_CONTEXT, wt.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                                                       ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.BOOL)]
    nc.NCryptSignHash.restype = ctypes.c_long
    nc.NCryptSignHash.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_char_p, wt.DWORD, ctypes.c_void_p, wt.DWORD,
                                  ctypes.POINTER(wt.DWORD), wt.DWORD]
    nc.NCryptFreeObject.argtypes = [ctypes.c_size_t]
    return c32, nc


def _open_store(c32):
    h = c32.CertOpenStore(CERT_STORE_PROV_SYSTEM_W, 0, None, CERT_SYSTEM_STORE_CURRENT_USER | CERT_STORE_READONLY_FLAG
                          | CERT_STORE_OPEN_EXISTING_FLAG, "MY")
    if not h: raise OSError(T("No se pudo abrir el almacén de certificados de Windows."))
    return h


def _der(ctx) -> bytes:
    return ctypes.string_at(ctx.contents.pbCertEncoded, ctx.contents.cbCertEncoded)


def _thumb(der: bytes) -> str:
    return hashlib.sha1(der, usedforsecurity=False).hexdigest().upper()   # huella de Windows, no es seguridad


def list_certs(only_valid=True) -> list:
    """Certificados con clave privada del almacén Personal: [{thumb, name, issuer, until, signing}].
    `signing`: su uso permite firmar documentos (firma digital / no repudio). No pide PIN."""
    if not available(): return []
    from asn1crypto import x509
    from datetime import datetime, timezone
    c32, _ = _libs()
    store = _open_store(c32); out = []
    try:
        ctx = c32.CertEnumCertificatesInStore(store, None)
        while ctx:
            size = wt.DWORD(0)
            if c32.CertGetCertificateContextProperty(ctx, CERT_KEY_PROV_INFO_PROP_ID, None, ctypes.byref(size)):
                der = _der(ctx); cert = x509.Certificate.load(der)
                until = cert["tbs_certificate"]["validity"]["not_after"].native
                ku = cert.key_usage_value.native if cert.key_usage_value else None
                eku = set(cert.extended_key_usage_value.native) if cert.extended_key_usage_value else None
                signing = (ku is None or bool({"digital_signature", "non_repudiation"} & set(ku))) and                     (eku is None or not eku <= _NOT_DOCS)              # p. ej. el de un servidor web no sirve
                if not (only_valid and until < datetime.now(timezone.utc)):
                    out.append({"thumb": _thumb(der), "name": cert.subject.native.get("common_name") or cert.subject.human_friendly,
                                "issuer": cert.issuer.native.get("common_name") or cert.issuer.human_friendly,
                                "until": until, "signing": signing})
            ctx = c32.CertEnumCertificatesInStore(store, ctx)      # libera el anterior
    finally:
        c32.CertCloseStore(store, 0)
    return sorted(out, key=lambda c: (not c["signing"], c["name"].lower()))


def _find(c32, store, thumb):
    ctx = c32.CertEnumCertificatesInStore(store, None)
    while ctx:
        if _thumb(_der(ctx)) == thumb.upper():
            return c32.CertDuplicateCertificateContext(ctx)
        ctx = c32.CertEnumCertificatesInStore(store, ctx)
    return None


def _ecdsa_der(raw: bytes) -> bytes:
    """CNG devuelve r‖s; CMS necesita la secuencia DER (r, s)."""
    from asn1crypto.algos import DSASignature
    n = len(raw) // 2
    return DSASignature({"r": int.from_bytes(raw[:n], "big"), "s": int.from_bytes(raw[n:], "big")}).dump()


def sign_digest(thumb: str, digest: bytes, hash_name: str, ec: bool) -> bytes:
    """Firma el resumen `digest` con la clave del certificado `thumb`. Windows pide el PIN si hace falta."""
    c32, nc = _libs()
    store = _open_store(c32)
    ctx = _find(c32, store, thumb)
    try:
        if not ctx: raise ValueError(T("El certificado ya no está instalado en Windows (¿se desconectó el token?)."))
        key, spec, free = ctypes.c_size_t(0), wt.DWORD(0), wt.BOOL(0)
        if not c32.CryptAcquireCertificatePrivateKey(ctx, CRYPT_ACQUIRE_ONLY_NCRYPT_KEY_FLAG, None, ctypes.byref(key),
                                                     ctypes.byref(spec), ctypes.byref(free)):
            raise ValueError(Tf("No se pudo acceder a la clave privada del certificado (código {0:#x}).",
                                ctypes.get_last_error() & 0xFFFFFFFF))
        try:
            pad = None if ec else BCRYPT_PKCS1_PADDING_INFO(hash_name.upper())
            flags = 0 if ec else BCRYPT_PAD_PKCS1
            ppad = ctypes.byref(pad) if pad else None
            n = wt.DWORD(0)
            st = nc.NCryptSignHash(key.value, ppad, digest, len(digest), None, 0, ctypes.byref(n), flags)
            if st == 0:
                buf = ctypes.create_string_buffer(n.value)
                st = nc.NCryptSignHash(key.value, ppad, digest, len(digest), buf, n.value, ctypes.byref(n), flags)
            if st != 0:
                code = st & 0xFFFFFFFF
                if code in (NTE_USER_CANCELLED, SCARD_W_CANCELLED_BY_USER):
                    raise ValueError(T("Firma cancelada."))
                raise ValueError(Tf("Windows no pudo firmar con este certificado (código {0:#x}).", code))
            raw = buf.raw[:n.value]
            return _ecdsa_der(raw) if ec else raw
        finally:
            if free.value: nc.NCryptFreeObject(key.value)
    finally:
        if ctx: c32.CertFreeCertificateContext(ctx)
        c32.CertCloseStore(store, 0)


def cert_der(thumb: str) -> bytes:
    c32, _ = _libs()
    store = _open_store(c32)
    try:
        ctx = _find(c32, store, thumb)
        if not ctx: raise ValueError(T("El certificado ya no está instalado en Windows (¿se desconectó el token?)."))
        try: return _der(ctx)
        finally: c32.CertFreeCertificateContext(ctx)
    finally:
        c32.CertCloseStore(store, 0)


def make_signer(thumb: str, sign_fn=None, der: bytes = None):
    """Firmante de pyHanko para el certificado `thumb` del almacén de Windows.
    `sign_fn(digest, hash_name, ec)` y `der` permiten sustituir Windows (pruebas)."""
    from asn1crypto import x509
    cert = x509.Certificate.load(der or cert_der(thumb))
    return _signer_class()(cert, sign_fn or (lambda dg, h, ec: sign_digest(thumb, dg, h, ec)))


_cls = None


def _signer_class():
    """Clase del firmante (pyHanko se importa solo al firmar: el arranque del programa no lo carga)."""
    global _cls
    if _cls is None:
        from pyhanko.sign.signers import Signer

        class WinCertSigner(Signer):
            def __init__(self, cert, sign_fn):
                super().__init__(signing_cert=cert)
                self._sign_fn = sign_fn
                self._ec = cert.public_key.algorithm == "ec"

            def estimate_raw_signature_size_bytes(self):
                bits = self.signing_cert.public_key.bit_size
                return (bits + 7) // 8 * 2 + 16 if self._ec else (bits + 7) // 8

            async def async_sign_raw(self, data: bytes, digest_algorithm: str, dry_run=False) -> bytes:
                if dry_run:
                    return bytes(self.estimate_raw_signature_size_bytes())
                digest = hashlib.new(digest_algorithm, data).digest()
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, self._sign_fn, digest, digest_algorithm, self._ec)
        _cls = WinCertSigner
    return _cls
