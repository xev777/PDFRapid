# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Escaneo TWAIN (sin abrir la ventana del escáner)."""
import ctypes
import os
import pytest
from core import convert, twain_scan

pytestmark = pytest.mark.skipif(os.name != "nt", reason="solo Windows")


def test_estructuras_como_twain_h():                       # alineación de 2 bytes, como en twain.h
    assert ctypes.sizeof(twain_scan.TW_IDENTITY) == 156
    assert ctypes.sizeof(twain_scan.TW_USERINTERFACE) == 12
    assert ctypes.sizeof(twain_scan.TW_PENDINGXFERS) == 6


def test_dib_a_bmp():
    """Mapa de bits de 24 bits en memoria global → .bmp que Pillow abre con su tamaño."""
    from PIL import Image
    import io
    w, h = 3, 2; stride = (w * 3 + 3) & ~3
    bih = twain_scan.BITMAPINFOHEADER(40, w, h, 1, 24, 0, stride * h, 7874, 7874, 0, 0)
    data = bytes(bih) + b"\xff" * stride * h
    k32 = ctypes.windll.kernel32
    k32.GlobalAlloc.restype = ctypes.c_void_p; k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]; k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    hnd = k32.GlobalAlloc(0x0002, len(data)); ctypes.memmove(k32.GlobalLock(hnd), data, len(data)); k32.GlobalUnlock(hnd)
    im = Image.open(io.BytesIO(twain_scan._dib_to_bmp(hnd)))
    assert im.size == (3, 2) and round(im.info["dpi"][0]) == 200


def _wia(code, llamadas):
    def ps(*a, **k):
        llamadas.append(a); return type("R", (), {"returncode": code, "stderr": "", "stdout": ""})()
    return ps


def test_twain_primero_sin_powershell(monkeypatch, tmp_path):
    """Con escáner TWAIN no se lanza PowerShell ni ningún proceso (Defender lo tomaba por troyano)."""
    llamadas = []
    monkeypatch.setattr(convert, "_ps", _wia(4, llamadas))
    monkeypatch.setattr(twain_scan, "scan", lambda dst: [dst])
    assert convert.scan_page(str(tmp_path / "p.png")) == [str(tmp_path / "p.png")] and not llamadas


def test_sin_twain_usa_wia(monkeypatch, tmp_path):
    llamadas = []
    monkeypatch.setattr(convert, "_ps", _wia(3, llamadas))
    monkeypatch.setattr(twain_scan, "scan", lambda dst: None)
    assert convert.scan_page(str(tmp_path / "p.png")) is False and llamadas


def test_sin_escaner(monkeypatch, tmp_path):
    monkeypatch.setattr(convert, "_ps", _wia(4, []))
    monkeypatch.setattr(twain_scan, "scan", lambda dst: None)
    with pytest.raises(convert.ScanError, match="escáner"):
        convert.scan_page(str(tmp_path / "p.png"))


def test_powershell_sin_bypass(monkeypatch):
    vistos = []
    monkeypatch.setattr(convert.subprocess, "run", lambda cmd, **k: vistos.append(cmd))
    convert._ps("exit 0", {}, 5)
    assert "Bypass" not in vistos[0] and "-ExecutionPolicy" not in vistos[0]
