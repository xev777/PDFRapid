# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Configuración y preferencias de la aplicación"""
import os
from core.portable import qsettings
from core.constants import MAX_RECENT

class AppSettings:
    """Singleton para manejar configuraciones persistentes."""
    _inst = None

    def __new__(cls):
        if not cls._inst:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __init__(self):
        self._s = qsettings("PDFManager")   # clave interna: conserva la configuración previa

    def add_recent(self, path: str):
        """Agrega un archivo a la lista de recientes."""
        rec = self.get_recent()
        if path in rec:
            rec.remove(path)
        rec.insert(0, path)
        self._s.setValue("recent", rec[:MAX_RECENT])

    def get_recent(self) -> list:
        """Obtiene la lista de archivos recientes existentes."""
        r = self._s.value("recent", [])
        return [x for x in (r if isinstance(r, list) else [r]) if os.path.exists(x)]

    def clear_recent(self):
        """Limpia la lista de archivos recientes."""
        self._s.setValue("recent", [])

    def get_author(self) -> str:
        """Nombre que firma comentarios y sellos (por defecto, el usuario de Windows)."""
        return self._s.value("author", "") or os.environ.get("USERNAME") or os.environ.get("USER") or "Usuario"

    def set_author(self, name: str): self._s.setValue("author", name.strip())

    def get_rotation_step(self) -> int:
        """Grados por paso al rotar objetos o dibujar líneas con Ctrl."""
        return int(self._s.value("rotation_step", 15))

    def set_rotation_step(self, deg: int): self._s.setValue("rotation_step", int(deg))

    def get_ruler_unit(self) -> str:
        u = self._s.value("ruler_unit", "mm")
        return u if u in ("mm", "cm", "in") else "mm"

    def set_ruler_unit(self, u: str): self._s.setValue("ruler_unit", u)

    def get_str(self, key: str, default: str) -> str:
        return str(self._s.value(key, default))

    def set_str(self, key: str, value: str): self._s.setValue(key, value)

    def get_bool(self, key: str, default: bool) -> bool:
        return str(self._s.value(key, "true" if default else "false")).lower() == "true"

    def set_bool(self, key: str, on: bool): self._s.setValue(key, "true" if on else "false")

    def get_rulers_shown(self) -> bool:
        return str(self._s.value("rulers_shown", "true")).lower() == "true"

    def set_rulers_shown(self, on: bool): self._s.setValue("rulers_shown", "true" if on else "false")

    def get_last_dir(self) -> str:
        """Última carpeta usada al abrir/guardar (o Documentos si ya no existe)."""
        d = self._s.value("last_dir", "")
        if d and os.path.isdir(d):
            return d
        docs = os.path.join(os.path.expanduser("~"), "Documents")
        return docs if os.path.isdir(docs) else os.path.expanduser("~")

    def set_last_dir(self, path: str):
        """Recuerda la carpeta de `path` (archivo o carpeta)."""
        d = path if os.path.isdir(path) else os.path.dirname(path)
        if d:
            self._s.setValue("last_dir", d)

    # ── dónde se quedó cada documento (página y zoom) ──
    MAX_POSITIONS = 200

    def _positions(self) -> dict:
        import json
        try:
            d = json.loads(self._s.value("positions", "{}") or "{}")
            return d if isinstance(d, dict) else {}
        except (ValueError, TypeError):
            return {}

    @staticmethod
    def _pos_key(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    def get_position(self, path: str):
        """(página, zoom) donde se dejó `path`, o None."""
        p = self._positions().get(self._pos_key(path))
        try:
            return int(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            return None

    def set_position(self, path: str, page: int, zoom: float):
        """Recuerda la página y el zoom de `path` (los 200 documentos más recientes)."""
        import json, time
        d = self._positions()
        d[self._pos_key(path)] = [int(page), round(float(zoom), 4), int(time.time())]
        if len(d) > self.MAX_POSITIONS:
            d = dict(sorted(d.items(), key=lambda kv: kv[1][2] if len(kv[1]) > 2 else 0)[-self.MAX_POSITIONS:])
        self._s.setValue("positions", json.dumps(d))
