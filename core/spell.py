# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Corrector ortográfico de Windows (API Spell Checking, Windows 8+), sin dependencias ni conexión: usa los
diccionarios de los idiomas instalados en Windows y el diccionario personal del usuario (lo que «añades» queda en
%APPDATA%\\Microsoft\\Spelling). Se llama por COM con ctypes. Fuera de Windows, o sin el idioma, no hace nada."""
import ctypes
import sys

_checkers = {}            # etiqueta de idioma → Checker (o None si no hay)


if sys.platform == "win32":
    from ctypes import HRESULT, POINTER, WINFUNCTYPE, byref, c_ulong, c_void_p, c_wchar_p
    from ctypes import wintypes

    _ole32 = ctypes.OleDLL("ole32")
    _ole32.CoTaskMemFree.restype = None
    _ole32.CoTaskMemFree.argtypes = [c_void_p]

    class _GUID(ctypes.Structure):
        _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort), ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]

    def _guid(s):
        g = _GUID(); _ole32.CLSIDFromString(c_wchar_p("{" + s + "}"), byref(g)); return g

    CLSID_FACTORY = "7AB36653-1796-484B-BDFA-E74F1DB7C1DC"
    IID_FACTORY = "8E018A9D-2415-4677-BF08-794EA61F94BB"

    def _method(obj, index, *argtypes):
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
        return WINFUNCTYPE(HRESULT, c_void_p, *argtypes)(vtbl[index])

    def _release(obj):
        if obj:
            vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
            WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])(obj)

    def _strings(enum) -> list:
        """Lee un IEnumString y lo libera."""
        out = []
        try:
            nxt = _method(enum, 3, c_ulong, POINTER(c_void_p), POINTER(c_ulong))
            while True:
                s, n = c_void_p(), c_ulong()
                if nxt(enum, 1, byref(s), byref(n)) != 0 or not n.value: break
                out.append(ctypes.wstring_at(s.value)); _ole32.CoTaskMemFree(s)
        finally:
            _release(enum)
        return out

    _factory = None

    def _get_factory():
        global _factory
        if _factory is None:
            try:
                try: _ole32.CoInitializeEx(None, 2)          # ya iniciado por Qt: da igual
                except OSError: pass
                p = c_void_p()
                _ole32.CoCreateInstance(byref(_guid(CLSID_FACTORY)), None, 1 | 4, byref(_guid(IID_FACTORY)), byref(p))
                _factory = p
            except OSError:
                _factory = False
        return _factory or None

    class Checker:
        def __init__(self, ptr, tag):
            self.p, self.tag = ptr, tag

        def errors(self, text: str) -> list:
            """[(inicio, largo)] de las palabras mal escritas (posiciones en unidades UTF-16, como Qt)."""
            if not text.strip(): return []
            enum = c_void_p(); out = []
            _method(self.p, 4, c_wchar_p, POINTER(c_void_p))(self.p, text, byref(enum))
            try:
                nxt = _method(enum, 3, POINTER(c_void_p))
                while True:
                    err = c_void_p()
                    if nxt(enum, byref(err)) != 0 or not err: break
                    a, b = c_ulong(), c_ulong()
                    _method(err, 3, POINTER(c_ulong))(err, byref(a)); _method(err, 4, POINTER(c_ulong))(err, byref(b))
                    out.append((a.value, b.value)); _release(err)
            finally:
                _release(enum)
            return out

        def suggest(self, word: str) -> list:
            enum = c_void_p()
            _method(self.p, 5, c_wchar_p, POINTER(c_void_p))(self.p, word, byref(enum))
            return _strings(enum)[:8]

        def add(self, word: str):
            """Al diccionario personal de Windows (lo comparten Office y otros programas)."""
            _method(self.p, 6, c_wchar_p)(self.p, word)

        def ignore(self, word: str):
            """Solo mientras la app esté abierta."""
            _method(self.p, 7, c_wchar_p)(self.p, word)

    def languages() -> list:
        f = _get_factory()
        if not f: return []
        enum = c_void_p()
        try:
            _method(f, 3, POINTER(c_void_p))(f, byref(enum))
        except OSError:
            return []
        return _strings(enum)

    def _create(tag):
        f = _get_factory()
        if not f: return None
        ok = wintypes.BOOL()
        try:
            _method(f, 4, c_wchar_p, POINTER(wintypes.BOOL))(f, tag, byref(ok))
            if not ok.value: return None
            p = c_void_p(); _method(f, 5, c_wchar_p, POINTER(c_void_p))(f, tag, byref(p))
            return Checker(p, tag)
        except OSError:
            return None
else:
    def languages() -> list:
        return []

    def _create(tag):
        return None


def checker(lang: str = "es"):
    """Corrector para el idioma ("es", "en" o una etiqueta como "es-MX"), o None si Windows no lo tiene."""
    if lang in _checkers: return _checkers[lang]
    langs = languages()
    try:                                            # preferir la variante del sistema (es-EC, en-GB…)
        from PyQt6.QtCore import QLocale
        sys_tag = QLocale.system().name().replace("_", "-")
    except Exception:
        sys_tag = ""
    if "-" not in lang and sys_tag.split("-")[0] == lang and sys_tag in langs: lang_tag = sys_tag
    else: lang_tag = lang
    tag = lang_tag if lang_tag in langs else next((t for t in langs if t.lower().split("-")[0] == lang.lower().split("-")[0]), None)
    if tag is None and lang in ("es", "en"):
        tag = {"es": "es-ES", "en": "en-US"}[lang]
    _checkers[lang] = _create(tag) if tag else None
    return _checkers[lang]
