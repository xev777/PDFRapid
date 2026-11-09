# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Lista de componentes (SBOM, formato CycloneDX 1.5) de lo que lleva el instalador: las dependencias de
requirements.txt y requirements-ocr.txt con todas las suyas, en las versiones instaladas, más Python.
También escribe esas versiones exactas en un archivo de requisitos para revisar vulnerabilidades (pip-audit).
Uso: venv\\Scripts\\python packaging\\sbom.py <salida.cdx.json> <requisitos-fijados.txt> <versión>"""
import datetime as dt
import json
import platform
import re
import sys
import uuid
from importlib import metadata

ROOT_REQS = ("requirements.txt", "requirements-ocr.txt")


def _name(req: str) -> str:
    return re.split(r"[\s;<>=!~\[(]", req.strip(), maxsplit=1)[0].lower().replace("_", "-")


def roots(paths=ROOT_REQS) -> list:
    out = []
    for p in paths:
        for line in open(p, encoding="utf-8"):
            line = line.split("#")[0].strip()
            if line and not line.startswith("-"): out.append(_name(line))
    return out


def closure(names) -> dict:
    """{nombre: Distribution} de los paquetes y todas sus dependencias obligatorias (sin «extras»)."""
    seen, todo = {}, list(names)
    while todo:
        n = todo.pop()
        if n in seen: continue
        try:
            d = metadata.distribution(n)
        except metadata.PackageNotFoundError:
            continue                                        # dependencia solo de otra plataforma
        seen[n] = d
        for r in d.requires or []:
            if "extra ==" in r: continue
            marker = r.split(";", 1)[1] if ";" in r else ""
            if marker:
                try:
                    from packaging.markers import Marker
                    if not Marker(marker).evaluate(): continue
                except Exception:
                    pass
            todo.append(_name(r))
    return seen


def _license(d) -> str:
    m = d.metadata
    if m.get("License-Expression"): return m["License-Expression"]
    if (m.get("License") or "").strip(): return m["License"].strip().splitlines()[0][:80]
    return next((c.split("::")[-1].strip() for c in m.get_all("Classifier") or [] if c.startswith("License ::")), "")


def build(version: str) -> tuple:
    comps = closure(roots())
    components = [{"type": "application", "name": "python", "version": platform.python_version(),
                   "purl": f"pkg:generic/python@{platform.python_version()}", "licenses": [{"license": {"id": "PSF-2.0"}}]}]
    for n, d in sorted(comps.items()):
        c = {"type": "library", "name": d.metadata["Name"], "version": d.version,
             "purl": f"pkg:pypi/{n}@{d.version}"}
        lic = _license(d)
        if lic: c["licenses"] = [{"license": {"name": lic}}]
        components.append(c)
    bom = {"bomFormat": "CycloneDX", "specVersion": "1.5", "serialNumber": f"urn:uuid:{uuid.uuid4()}", "version": 1,
           "metadata": {"timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "component": {"type": "application", "name": "PDFRapid", "version": version,
                                      "licenses": [{"license": {"id": "AGPL-3.0-or-later"}}],
                                      "supplier": {"name": "Fernando Erazo"}}},
           "components": components}
    pinned = [f"{d.metadata['Name']}=={d.version}" for _, d in sorted(comps.items())]
    return bom, pinned


if __name__ == "__main__":
    out, reqs, version = sys.argv[1:4]
    bom, pinned = build(version)
    with open(out, "w", encoding="utf-8") as f: json.dump(bom, f, indent=1, ensure_ascii=False)
    with open(reqs, "w", encoding="utf-8") as f: f.write("\n".join(pinned) + "\n")
    print(f"SBOM: {len(bom['components'])} componentes → {out}")
