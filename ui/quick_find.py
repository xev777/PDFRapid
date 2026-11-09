# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Búsqueda rápida de la barra superior, al estilo «buscar siguiente»: no busca mientras se escribe.
▶ (o Enter) salta a la siguiente coincidencia y ◀ a la anterior, una por pulsación, desde la página actual.
Solo lee las páginas necesarias hasta la próxima coincidencia (por tramos, sin congelar la ventana), así que
es inmediata aunque el documento tenga miles de páginas. Al llegar al final (o al inicio) avisa; la siguiente
pulsación continúa desde el otro extremo."""
from core.i18n import T, Tf
import time
from PyQt6.QtCore import QTimer
from core.search import find_in_page


class QuickFind:
    CHUNK_S = 0.03                       # tiempo máximo de trabajo seguido antes de devolver el control a Qt

    def __init__(self, win, label):
        self.win, self.label = win, label
        self.reset()

    def reset(self):
        self.term, self.pos, self._hits, self._edge = None, None, {}, None
        self._job = getattr(self, "_job", 0) + 1
        self.label.setText("")

    def clear(self):
        v = self.win._viewer
        if v and v.doc: v.highlight_search(-1, [])
        self.reset()

    def _page_hits(self, doc, p):
        if p not in self._hits: self._hits[p] = find_in_page(doc[p], self.term)
        return self._hits[p]

    def step(self, d: int, term: str):
        v = self.win._viewer
        term = (term or "").strip()
        if not (v and v.doc and term): return
        if term != self.term:
            self.reset(); self.term = term
        doc, n = v.doc, len(v.doc)
        if self._edge is not None and self._edge == d:          # ya se avisó del final: dar la vuelta
            p, i = (0, -1) if d > 0 else (n - 1, None)
            self._edge = None
        elif self.pos is None or self._moved(v):                  # primera vez, o el usuario se desplazó: desde aquí
            p, i = v.current, (-1 if d > 0 else None)
        else:
            p, i = self.pos
        self._edge = None
        if i is None: i = len(self._page_hits(doc, p))           # «antes del final» de la página p
        hits = self._page_hits(doc, p)
        if 0 <= i + d < len(hits):                                # otra coincidencia en la misma página
            return self._show(p, i + d)
        self._job += 1
        self._scan(self._job, p + d, d)

    def _scan(self, job, p, d):
        """Recorre páginas en la dirección `d` hasta encontrar una con coincidencias."""
        v = self.win._viewer
        if job != self._job or not (v and v.doc): return
        doc, n, t0 = v.doc, len(v.doc), time.monotonic()
        while 0 <= p < n:
            hits = self._page_hits(doc, p)
            if hits:
                return self._show(p, 0 if d > 0 else len(hits) - 1)
            p += d
            if time.monotonic() - t0 > self.CHUNK_S:
                self.label.setText(Tf("p. {0}…", p + 1))
                QTimer.singleShot(0, lambda: self._scan(job, p, d)); return
        self._edge = d
        msg = T("Fin del documento. ▶ sigue desde el inicio.") if d > 0 else T("Inicio del documento. ◀ sigue desde el final.")
        self.label.setText(T("fin") if d > 0 else T("inicio"))
        self.win._status(Tf("«{0}»: {1}", self.term, msg))

    def _moved(self, v) -> bool:
        """¿El usuario se desplazó lejos de la última coincidencia mostrada (más de una pantalla)?"""
        sb = v.scroll.verticalScrollBar()
        return abs(sb.value() - getattr(self, "_shown_at", sb.value())) > v.scroll.viewport().height()

    def _show(self, p, i):
        v = self.win._viewer
        hits = self._hits[p]
        self.pos = (p, i)
        # search_for da coordenadas sin rotar; el visor dibuja en coordenadas visibles (igual que el panel de búsqueda)
        m = v.doc[p].rotation_matrix
        v.highlight_search(p, [hits[i] * m])                     # solo la actual: se pinta según se avanza
        self._shown_at = v.scroll.verticalScrollBar().value()
        self.label.setText(Tf("p. {0} · {1}/{2}", p + 1, i + 1, len(hits)))
