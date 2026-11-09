# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Apertura y guardado seguro de PDFs.

Los documentos se abren desde memoria para no dejar el archivo bloqueado
(en Windows, MuPDF mantiene el archivo abierto y no se puede sobrescribir).
El guardado escribe primero un temporal en la misma carpeta y luego lo
reemplaza de forma atómica: si algo falla, el original queda intacto.
"""
import os
import re
import secrets
import tempfile
import pymupdf


PERM_ALL = 0xF3C   # bits de permiso con significado (imprimir, modificar, copiar, anotar, …)


class PasswordRequired(Exception):
    """El PDF pide contraseña para abrirse (o la dada es incorrecta)."""


def open_pdf(path: str, password: str = None) -> pymupdf.Document:
    """Abre un PDF cargándolo en memoria (no bloquea el archivo)."""
    with open(path, "rb") as f:
        doc = pymupdf.open(stream=f.read(), filetype="pdf")
    needed = doc.needs_pass
    auth = doc.authenticate(password or "") if needed else 0
    if needed and not auth:
        doc.close()
        raise PasswordRequired(path)
    doc.pdfgm_crypt = _crypt_info(doc, password if needed else None, auth)
    return doc


def _crypt_info(doc, password, auth):
    """Datos para volver a cifrar al guardar: MuPDF no conserva el cifrado al reescribir
    un documento abierto desde memoria. None si el PDF no está cifrado."""
    if not doc.metadata.get("encryption"):
        return None
    perm = 0xFFF
    kind, val = doc.xref_get_key(-1, "Encrypt")
    if kind == "xref":
        kind, val = "dict", doc.xref_object(int(val.split()[0]), compressed=True)
    m = re.search(r"/P\s*(-?\d+)", val) if kind == "dict" else None
    if m:
        perm = int(m.group(1)) & 0xFFF           # permisos originales, aunque se abriera como propietario
    return {"user_pw": password or "",
            "owner_pw": password if auth & 4 else None,   # None = contraseña de propietario desconocida
            "only_owner_pw": bool(auth & 4) and not auth & 2,
            "permissions": perm}


def crypt_warning(crypt) -> str:
    """Aviso si al guardar no se puede conservar alguna contraseña ('' si no hace falta)."""
    if not crypt:
        return ""
    if crypt["only_owner_pw"]:
        return ("Lo abriste con la contraseña de propietario: al guardar, esa misma contraseña "
                "pasará a ser también la de apertura. Los permisos se conservan.")
    if crypt["owner_pw"] is None and crypt["permissions"] & PERM_ALL != PERM_ALL:
        return ("Se conservan la contraseña de apertura y los permisos del documento, pero la "
                "contraseña de propietario original no se puede conservar.")
    return ""


def save_pdf(doc: pymupdf.Document, path: str, crypt=None, **opts):
    """Guarda `doc` en `path` (puede ser el archivo original).
    `crypt` (de un documento cifrado) vuelve a aplicar contraseña y permisos."""
    crypt = crypt or getattr(doc, "pdfgm_crypt", None)
    kw = {}
    if crypt:
        kw = dict(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=crypt["user_pw"],
                  owner_pw=crypt["owner_pw"] or crypt["user_pw"] or secrets.token_urlsafe(24),
                  permissions=crypt["permissions"])
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(suffix=".pdf", prefix=".pdfgm-", dir=folder)
    os.close(fd)
    try:
        doc.save(tmp, **(opts or dict(garbage=2, deflate=True, use_objstms=1)), **kw)   # garbage=3 es muy lento en PDFs grandes
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
