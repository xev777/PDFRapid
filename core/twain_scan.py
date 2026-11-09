# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Escaneo por TWAIN (TWAINDSM.dll de 64 bits) para los escáneres que no se registran en WIA, como muchos Epson,
Canon o Brother que usan su propio programa (Epson Scan 2…). Se abre la ventana del controlador del fabricante.
Va dentro del programa, en un hilo de trabajo: lanzarse a sí mismo en un proceso oculto hacía que Windows Defender
lo tomara por un troyano (Trojan:Win32/Bearfoos.A!ml)."""
import ctypes
import ctypes.wintypes as wt
import os
import sys

DG_CONTROL, DG_IMAGE = 1, 2
DAT_IDENTITY, DAT_EVENT, DAT_PARENT, DAT_PENDINGXFERS, DAT_USERINTERFACE, DAT_IMAGENATIVEXFER = 3, 2, 4, 5, 9, 0x0104
MSG_GET, MSG_GETDEFAULT, MSG_GETFIRST, MSG_GETNEXT, MSG_RESET = 1, 3, 4, 5, 7
MSG_XFERREADY, MSG_CLOSEDSREQ, MSG_CLOSEDSOK = 0x0101, 0x0102, 0x0103
MSG_OPENDSM, MSG_CLOSEDSM, MSG_OPENDS, MSG_CLOSEDS, MSG_USERSELECT = 0x0301, 0x0302, 0x0401, 0x0402, 0x0403
MSG_DISABLEDS, MSG_ENABLEDS, MSG_PROCESSEVENT, MSG_ENDXFER = 0x0501, 0x0502, 0x0601, 0x0701
TWRC_SUCCESS, TWRC_CANCEL, TWRC_DSEVENT, TWRC_XFERDONE, TWRC_ENDOFLIST = 0, 3, 4, 6, 7


class TW_VERSION(ctypes.Structure):
    _pack_ = 2
    _fields_ = [("MajorNum", ctypes.c_uint16), ("MinorNum", ctypes.c_uint16), ("Language", ctypes.c_uint16),
                ("Country", ctypes.c_uint16), ("Info", ctypes.c_char * 34)]


class TW_IDENTITY(ctypes.Structure):
    _pack_ = 2
    _fields_ = [("Id", ctypes.c_uint32), ("Version", TW_VERSION), ("ProtocolMajor", ctypes.c_uint16),
                ("ProtocolMinor", ctypes.c_uint16), ("SupportedGroups", ctypes.c_uint32),
                ("Manufacturer", ctypes.c_char * 34), ("ProductFamily", ctypes.c_char * 34),
                ("ProductName", ctypes.c_char * 34)]


class TW_USERINTERFACE(ctypes.Structure):
    _pack_ = 2
    _fields_ = [("ShowUI", ctypes.c_uint16), ("ModalUI", ctypes.c_uint16), ("hParent", ctypes.c_void_p)]


class TW_PENDINGXFERS(ctypes.Structure):
    _pack_ = 2
    _fields_ = [("Count", ctypes.c_uint16), ("EOJ", ctypes.c_uint32)]


class TW_EVENT(ctypes.Structure):
    _pack_ = 2
    _fields_ = [("pEvent", ctypes.c_void_p), ("TWMessage", ctypes.c_uint16)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]


class TwainError(Exception):
    pass


def _dib_to_bmp(handle) -> bytes:
    """Mapa de bits en memoria global (transferencia nativa de TWAIN) → archivo .bmp."""
    k32 = ctypes.windll.kernel32
    k32.GlobalLock.restype = ctypes.c_void_p; k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalSize.restype = ctypes.c_size_t; k32.GlobalSize.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]; k32.GlobalFree.argtypes = [ctypes.c_void_p]
    ptr = k32.GlobalLock(handle)
    try:
        size = k32.GlobalSize(handle)
        dib = ctypes.string_at(ptr, size)
    finally:
        k32.GlobalUnlock(handle); k32.GlobalFree(handle)
    bih = BITMAPINFOHEADER.from_buffer_copy(dib[:ctypes.sizeof(BITMAPINFOHEADER)])
    colors = bih.biClrUsed or (1 << bih.biBitCount if bih.biBitCount <= 8 else 0)
    off = 14 + bih.biSize + colors * 4 + (12 if bih.biCompression == 3 and bih.biSize == 40 else 0)
    head = b"BM" + (14 + len(dib)).to_bytes(4, "little") + b"\0\0\0\0" + off.to_bytes(4, "little")
    return head + dib


class Session:
    def __init__(self):
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "TWAINDSM.dll")
        if not os.path.isfile(path): raise FileNotFoundError(path)
        self.dsm = ctypes.WinDLL(path)
        self.entry = self.dsm.DSM_Entry
        self.entry.restype = ctypes.c_uint16
        self.entry.argtypes = [ctypes.POINTER(TW_IDENTITY), ctypes.POINTER(TW_IDENTITY), ctypes.c_uint32,
                               ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p]
        self.app = TW_IDENTITY()
        self.app.Version.MajorNum, self.app.Version.MinorNum = 1, 0
        self.app.Version.Language, self.app.Version.Country = 13, 1                  # inglés/EE. UU. (genérico)
        self.app.Version.Info = b"PDFRapid"
        self.app.ProtocolMajor, self.app.ProtocolMinor = 1, 9                         # TWAIN 1.9: bucle de mensajes
        self.app.SupportedGroups = DG_CONTROL | DG_IMAGE
        self.app.Manufacturer, self.app.ProductFamily, self.app.ProductName = b"PDFRapid", b"PDFRapid", b"PDFRapid"
        self.src = None
        u32 = ctypes.windll.user32
        u32.CreateWindowExW.restype = wt.HWND
        u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
        self.hwnd = u32.CreateWindowExW(0, "STATIC", "PDFRapid", 0, 0, 0, 0, 0, None, None, None, None)
        self.hwnd_ref = ctypes.c_void_p(self.hwnd)
        if self.call(None, DG_CONTROL, DAT_PARENT, MSG_OPENDSM, ctypes.byref(self.hwnd_ref)) != TWRC_SUCCESS:
            raise TwainError("No se pudo iniciar TWAIN")

    def call(self, dest, dg, dat, msg, data):
        return self.entry(ctypes.byref(self.app), ctypes.byref(dest) if dest is not None else None, dg, dat, msg, data)

    def sources(self) -> list:
        out, s = [], TW_IDENTITY()
        rc = self.call(None, DG_CONTROL, DAT_IDENTITY, MSG_GETFIRST, ctypes.byref(s))
        while rc == TWRC_SUCCESS:
            out.append(s.ProductName.decode("latin-1")); s = TW_IDENTITY()
            rc = self.call(None, DG_CONTROL, DAT_IDENTITY, MSG_GETNEXT, ctypes.byref(s))
        return out

    def open_source(self, choose: bool):
        s = TW_IDENTITY()
        msg = MSG_USERSELECT if choose else MSG_GETDEFAULT
        rc = self.call(None, DG_CONTROL, DAT_IDENTITY, msg, ctypes.byref(s))
        if rc == TWRC_CANCEL: return False
        if rc != TWRC_SUCCESS or self.call(None, DG_CONTROL, DAT_IDENTITY, MSG_OPENDS, ctypes.byref(s)) != TWRC_SUCCESS:
            raise TwainError("No se pudo abrir el escáner (TWAIN)")
        self.src = s
        return True

    def acquire(self, dst: str) -> list:
        """Muestra la ventana del escáner y guarda cada página: dst, luego dst_2.png, dst_3.png…"""
        ui = TW_USERINTERFACE(1, 1, self.hwnd)
        if self.call(self.src, DG_CONTROL, DAT_USERINTERFACE, MSG_ENABLEDS, ctypes.byref(ui)) not in (0, 2):
            raise TwainError("El escáner no respondió (TWAIN)")
        u32 = ctypes.windll.user32
        msg, pages, done = wt.MSG(), [], False
        while not done and u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            ev = TW_EVENT(ctypes.cast(ctypes.byref(msg), ctypes.c_void_p), 0)
            rc = self.call(self.src, DG_CONTROL, DAT_EVENT, MSG_PROCESSEVENT, ctypes.byref(ev))
            if ev.TWMessage == MSG_XFERREADY:
                pages += self._transfer(dst, len(pages)); done = True
            elif ev.TWMessage in (MSG_CLOSEDSREQ, MSG_CLOSEDSOK):
                done = True
            if rc != TWRC_DSEVENT:
                u32.TranslateMessage(ctypes.byref(msg)); u32.DispatchMessageW(ctypes.byref(msg))
        self.call(self.src, DG_CONTROL, DAT_USERINTERFACE, MSG_DISABLEDS, ctypes.byref(ui))
        return pages

    def _transfer(self, dst, n) -> list:
        from PIL import Image
        import io
        out, pend = [], TW_PENDINGXFERS()
        while True:
            h = ctypes.c_void_p()
            rc = self.call(self.src, DG_IMAGE, DAT_IMAGENATIVEXFER, MSG_GET, ctypes.byref(h))
            if rc == TWRC_XFERDONE and h.value:
                p = dst if n + len(out) == 0 else f"{os.path.splitext(dst)[0]}_{n + len(out) + 1}.png"
                im = Image.open(io.BytesIO(_dib_to_bmp(h.value)))
                im.save(p, dpi=im.info.get("dpi", (200, 200))); out.append(p)
            elif rc == TWRC_CANCEL:
                pass
            else:
                self.call(self.src, DG_CONTROL, DAT_PENDINGXFERS, MSG_RESET, ctypes.byref(pend)); break
            self.call(self.src, DG_CONTROL, DAT_PENDINGXFERS, MSG_ENDXFER, ctypes.byref(pend))
            if pend.Count == 0: break
        return out

    def close(self):
        if self.src is not None: self.call(None, DG_CONTROL, DAT_IDENTITY, MSG_CLOSEDS, ctypes.byref(self.src))
        self.call(None, DG_CONTROL, DAT_PARENT, MSG_CLOSEDSM, ctypes.byref(self.hwnd_ref))
        ctypes.windll.user32.DestroyWindow(self.hwnd)


def scan(dst: str):
    """Escanea por TWAIN en el hilo actual (que no debe ser el de la interfaz: el bucle de mensajes espera
    a que se cierre la ventana del escáner). None si no hay TWAIN ni escáneres, False si se canceló,
    o la lista de páginas guardadas. TwainError si el escáner falla."""
    ole = ctypes.windll.ole32.OleInitialize(None) in (0, 1)     # algunos controladores usan OLE en su ventana
    try:
        try:
            s = Session()
        except (OSError, TwainError):
            return None
        try:
            found = s.sources()
            if not found: return None
            if not s.open_source(choose=len(found) > 1): return False
            return s.acquire(dst) or False
        finally:
            s.close()
    finally:
        if ole: ctypes.windll.ole32.OleUninitialize()


if __name__ == "__main__":                       # prueba manual: python core/twain_scan.py salida.png
    print(scan(sys.argv[1]))
