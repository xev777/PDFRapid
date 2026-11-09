# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
# PyInstaller en modo carpeta (--onedir): las bibliotecas LGPL (Qt) quedan como archivos sustituibles.
# Uso: venv\Scripts\python -m PyInstaller packaging\pdfrapid.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = SPECPATH + "/.."
datas = [(ROOT + "/locales", "locales"), (ROOT + "/LICENSE", "."), (ROOT + "/docs/guia", "docs/guia"),
         (ROOT + "/packaging/THIRD_PARTY_NOTICES.txt", "."), (ROOT + "/packaging/pdfrapid.ico", ".")]
datas += collect_data_files("rapidocr") + collect_data_files("pyhanko") + collect_data_files("pyhanko_certvalidator")
hidden = collect_submodules("rapidocr") + collect_submodules("pyhanko") + collect_submodules("qrcode") + collect_submodules("pkcs11") + ["zxingcpp"]
# Módulos propios importados de forma diferida (dentro de funciones): incluirlos todos para que el .exe no falle.
for _p in ("core", "ui", "dialogs", "models", "utils"):
    hidden += collect_submodules(_p)

a = Analysis([ROOT + "/main.py"], pathex=[ROOT], datas=datas, hiddenimports=hidden,
             excludes=["tkinter", "matplotlib", "pytest", "IPython", "PyQt5", "PySide6", "PySide2"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PDFRapid", console=False,
          icon=ROOT + "/packaging/pdfrapid.ico", upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="PDFRapid", upx=False)
