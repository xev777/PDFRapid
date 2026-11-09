# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Autoguardado para recuperar el trabajo tras un cierre inesperado.
Cada documento con cambios guarda `<id>.json` (ruta original y objetos por página, en puntos PDF) y,
si se modificó el contenido del PDF (páginas, tachado, marca de agua…), `<id>.pdf` con una copia.
Los PDF con contraseña nunca se copian descifrados: de ellos solo se guardan los objetos.
Al guardar o cerrar normalmente se borran; los que quedan de un proceso que ya no existe se ofrecen al iniciar."""
import ctypes
import json
import os
import time
from core.portable import data_dir


def _dir() -> str:
    d = os.environ.get("PDFRAPID_RECOVERY_DIR") or os.path.join(data_dir(), "recovery")
    os.makedirs(d, exist_ok=True)
    return d


def _alive(pid: int) -> bool:
    """¿Sigue abierto el proceso `pid`? (sin enviarle señales)."""
    if pid == os.getpid(): return True
    if os.name != "nt":
        try: os.kill(pid, 0); return True
        except OSError: return False
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)              # PROCESS_QUERY_LIMITED_INFORMATION
    if not h: return False
    code = ctypes.c_ulong()
    ok = k.GetExitCodeProcess(h, ctypes.byref(code)); k.CloseHandle(h)
    return bool(ok) and code.value == 259              # STILL_ACTIVE


def save(uid: str, path: str, pages: dict, doc_bytes: bytes = None):
    d = _dir()
    if doc_bytes is not None:
        tmp = os.path.join(d, uid + ".pdf.tmp")
        with open(tmp, "wb") as f: f.write(doc_bytes)
        os.replace(tmp, os.path.join(d, uid + ".pdf"))
    meta = {"pid": os.getpid(), "path": path, "time": time.time(), "pages": {str(k): v for k, v in pages.items()},
            "pdf": doc_bytes is not None or os.path.exists(os.path.join(d, uid + ".pdf"))}
    tmp = os.path.join(d, uid + ".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f: json.dump(meta, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(d, uid + ".json"))


def remove(uid: str):
    for ext in (".json", ".pdf"):
        try: os.remove(os.path.join(_dir(), uid + ext))
        except OSError: pass


def pending() -> list:
    """Autoguardados de procesos que ya no existen: [{uid, path, time, pages, pdf (ruta o None)}]."""
    out, d = [], _dir()
    for name in os.listdir(d):
        if not name.endswith(".json"): continue
        uid = name[:-5]
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f: m = json.load(f)
            if _alive(int(m.get("pid", 0))): continue
            pdf = os.path.join(d, uid + ".pdf")
            out.append({"uid": uid, "path": m.get("path") or "", "time": m.get("time", 0),
                        "pages": {int(k): v for k, v in m.get("pages", {}).items()},
                        "pdf": pdf if m.get("pdf") and os.path.exists(pdf) else None})
        except Exception:
            remove(uid)                                 # archivo dañado: no sirve para recuperar
    return sorted(out, key=lambda r: r["time"])
