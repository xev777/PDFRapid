# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Las dependencias que se distribuyen deben tener licencia compatible con la AGPL-3.0."""
from importlib.metadata import distributions, requires
import re

# palabras que identifican licencias compatibles (permisivas, LGPL, GPLv3, AGPLv3, MPL-2.0)
OK = ("MIT", "BSD", "APACHE", "PSF", "PYTHON SOFTWARE", "ISC", "ZLIB", "0BSD", "MPL", "MOZILLA",
      "LGPL", "LESSER", "AGPL", "AFFERO", "GPL-3", "GPLV3", "GPL V3", "GNU GENERAL PUBLIC LICENSE V3",
      "UNLICENSE", "CMU", "HPND", "UNICODE")
NO = ("GPL-2.0-ONLY", "GPLV2 ONLY", "SSPL", "BUSL", "COMMONS CLAUSE", "NON-COMMERCIAL", "PROPRIETARY", "CC-BY-NC")
# solo para desarrollar (no se incluyen en el programa)
DEV = {"pytest", "iniconfig", "pluggy", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile",
       "pywin32-ctypes", "pyflakes", "autoflake", "pip", "setuptools", "packaging", "colorama", "pygments"}
# revisadas a mano: sus metadatos dicen algo que no coincide con el texto real de la licencia
REVISADAS = {"qrcode": "BSD-3-Clause + MIT (archivo LICENSE revisado el 2026-10-28; el clasificador "
                       "'Other/Proprietary' de sus metadatos es un error del paquete)"}
ROOTS = ["pymupdf", "pypdf", "pyqt6", "pdf2docx", "pyhanko", "rapidocr", "onnxruntime", "mammoth", "qrcode", "python-pkcs11"]


def _norm(n): return re.sub(r"[-_.]+", "-", n).lower()


def _licencia(d):
    m = d.metadata
    txt = " ".join([m.get("License-Expression") or "", (m.get("License") or "")[:200]] +
                   [c for c in (m.get_all("Classifier") or []) if c.startswith("License")])
    return txt.upper()


def _incluidas():
    """Dependencias de ejecución (cierre transitivo de ROOTS)."""
    dists = {_norm(d.metadata["Name"]): d for d in distributions()}
    vistas, pend = set(), [_norm(r) for r in ROOTS]
    while pend:
        n = pend.pop()
        if n in vistas or n not in dists: continue
        vistas.add(n)
        for req in requires(dists[n].metadata["Name"]) or []:
            if "extra ==" in req: continue
            pend.append(_norm(re.split(r"[ ;<>=!~\[(]", req, 1)[0]))
    return {n: dists[n] for n in vistas if n not in DEV}


def test_licencias_compatibles():
    malas = []
    for n, d in _incluidas().items():
        lic = _licencia(d)
        if n in REVISADAS: continue
        if any(x in lic for x in NO) or not any(x in lic for x in OK):
            malas.append(f"{n}: {lic[:80] or 'sin licencia declarada'}")
    assert not malas, "Licencias a revisar:\n" + "\n".join(malas)


def test_bloqueo_de_red_activo():
    """Comprueba que la vigilancia de red de conftest funciona (si no, las pruebas no demostrarían nada)."""
    import socket
    import pytest
    with pytest.raises(AssertionError):
        socket.create_connection(("example.com", 80), timeout=1)
