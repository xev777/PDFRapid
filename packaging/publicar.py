# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Exporta el código público (sin documentos internos) a una carpeta para el repositorio xev777/PDFRapid.
Uso: venv/Scripts/python packaging/publicar.py <carpeta destino>"""
import os, shutil, subprocess, sys  # nosec B404

PRIVADOS = ("CLAUDE.md", "docs/BITACORA.md", "docs/hallazgos.md", "docs/distribucion.md", "docs/ANALISIS_LEGAL.md",
            "docs/pendientes-cliente.txt", "docs/interno/")


def main(dest):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.split()  # nosec
    for f in files:
        if f.startswith(PRIVADOS):
            continue
        os.makedirs(os.path.join(dest, os.path.dirname(f)), exist_ok=True)
        shutil.copy2(os.path.join(root, f), os.path.join(dest, f))


if __name__ == "__main__":
    main(sys.argv[1])
