# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Visor de PDF: Maneja múltiples PageCanvas, zoom y scroll"""
from core.i18n import T, Tf
import bisect
import uuid
import pymupdf
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QScrollArea, QFrame, QMessageBox,
                             QLabel, QPushButton, QSizePolicy, QStackedWidget)
from PyQt6.QtCore import pyqtSignal, Qt, QSize, QPoint, QTimer, QRect, QEvent, QUrl
from PyQt6.QtGui import QPainter, QPixmap, QImage, QColor, QDesktopServices
from ui.canvas import PageCanvas
from models.annotation import Ann
from core.constants import APP_NAME
from core.logger import log
from core.pdf_io import open_pdf, save_pdf
from core import ann_store, recovery
from core.settings import AppSettings
from ui.styles import C
from ui.icons import get_icon
from ui.ruler import Ruler, RulerCorner



SAFE_SCHEMES = ("http", "https", "mailto")


def safe_link(uri: str) -> bool:
    """Solo enlaces web y de correo. Un PDF malicioso puede usar file://, rutas de red (filtran el usuario de
    Windows) o protocolos de Windows con fallos conocidos (ms-msdt:, search-ms:…)."""
    u = QUrl(uri.strip())
    return u.isValid() and u.scheme().lower() in SAFE_SCHEMES and (u.scheme().lower() == "mailto" or bool(u.host()))

class _PagesArea(QWidget):
    """Contenedor de páginas sin QLayout (los layouts de Qt no pasan de 524 287 px de alto
    y aplastan las páginas de documentos largos). Cada página es un único widget (el lienzo);
    el marco y el número de página se dibujan aquí, solo en la zona visible."""
    MARGIN, GAP, LABEL_H, HGAP = 24, 8, 26, 14
    mode = "continuous"      # "continuous" (una columna) | "two" (dos páginas) | "cover" (dos, con portada sola)

    def __init__(self):
        super().__init__()
        self.items = []
        self._tops = []        # y de cada página, para encontrar las visibles con bisect

    def clear(self):
        for w in self.items:
            w.setParent(None)
            w.deleteLater()
        self.items, self._tops = [], []

    def rows(self) -> list:
        """Páginas por fila según el modo: [[0], [1], …] o [[0, 1], [2, 3], …] o [[0], [1, 2], …]."""
        n = len(self.items)
        if self.mode == "continuous": return [[i] for i in range(n)]
        start = 1 if self.mode == "cover" and n else 0
        return ([[0]] if start else []) + [list(range(i, min(i + 2, n))) for i in range(start, n, 2)]

    def relayout(self):
        rows = self.rows()
        row_w = lambda r: sum(self.items[i].width() for i in r) + self.HGAP * (len(r) - 1)
        content_w = max((row_w(r) for r in rows), default=0) + 2 * self.MARGIN
        width = max(content_w, self.parentWidget().width() if self.parentWidget() else 0)
        y, self._tops = self.MARGIN, [0] * len(self.items)
        for r in rows:
            x = (width - row_w(r)) // 2
            for i in r:
                w = self.items[i]; w.move(x, y); self._tops[i] = y; x += w.width() + self.HGAP
            y += max(self.items[i].height() for i in r) + self.LABEL_H + self.GAP
        self.setMinimumSize(content_w, y - self.GAP + self.MARGIN if self.items else 0)
        self.update()

    def paintEvent(self, ev):
        if not self.items: return
        r = ev.rect()
        p = QPainter(self)
        p.setPen(QColor(C['border']))
        f = p.font(); f.setPixelSize(11); p.setFont(f)
        i = max(bisect.bisect_right(self._tops, r.top()) - 1, 0)
        while i > 0 and self._tops[i - 1] == self._tops[i]: i -= 1      # la otra página de la misma fila
        while i < len(self.items) and self._tops[i] <= r.bottom():
            g = self.items[i].geometry()
            p.fillRect(g, Qt.GlobalColor.white)
            p.setPen(QColor(C['border'])); p.drawRect(g.adjusted(-1, -1, 0, 0))
            p.setPen(QColor(C['muted']))
            p.drawText(QRect(g.left(), g.bottom() + 4, g.width(), self.LABEL_H - 6),
                       Qt.AlignmentFlag.AlignCenter, Tf("Página {0}", i + 1))
            i += 1
        p.end()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if ev.oldSize().width() != ev.size().width():
            self.relayout()           # recentrar


class Viewer(QWidget):
    count_changed = pyqtSignal(int)
    scroll_changed = pyqtSignal(int, int)
    current_changed = pyqtSignal(int)
    wheel_zoom = pyqtSignal(int)
    annotations_changed = pyqtSignal()        # página que ocupa el centro de la vista
    MAX_DOC_UNDO_BYTES = 200 * 1024 * 1024   # memoria máx. para copias del PDF en deshacer
    open_requested = pyqtSignal()
    doc_replaced = pyqtSignal()      # el objeto pymupdf.Document cambió (deshacer de texto nativo)
    toc_changed = pyqtSignal()       # marcadores cambiados por deshacer/rehacer
    pages_changed = pyqtSignal()     # cambió la apariencia de páginas (rotación)

    def __init__(self, props, parent=None):
        super().__init__(parent)
        self.doc = None
        self.path = None
        self.dirty = False  # Hay cambios sin guardar
        # Pila global de deshacer: ("ann", pág) | ("rot", [págs], grados) | ("doc", bytes)
        self._undo = []
        self._redo = []
        self.zoom = Ann.SCALE = 1.5
        self.tool = "select"
        self.props = props
        self.canvases = []
        self.current = 0
        self._back, self._fwd = [], []     # historial de saltos (enlaces, índice, ir a página)
        self.crypt = None          # cifrado original (ver core.pdf_io._crypt_info)
        self.uid = uuid.uuid4().hex   # nombre de su autoguardado (core.recovery)
        self._doc_rev = self._saved_rev = 0   # cambios al contenido del PDF / ya autoguardados
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.verticalScrollBar().valueChanged.connect(
            lambda: self.scroll_changed.emit(
                self.scroll.horizontalScrollBar().value(),
                self.scroll.verticalScrollBar().value()
            )
        )
        self.scroll.verticalScrollBar().valueChanged.connect(self._update_visible)
        self.scroll.viewport().installEventFilter(self)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.empty_state = self._build_empty_state()
        self.stack.addWidget(self.empty_state)
        # reglas (Vista → Reglas) alrededor del área de páginas
        self._hover_cv = None
        self.guides = {}                # {página: {"v": [x pt], "h": [y pt]}}: guías (solo en pantalla)
        self._gprev = None              # lienzo con la vista previa de la guía que se arrastra desde la regla
        self.doc_view = QWidget(); g = QGridLayout(self.doc_view)
        g.setContentsMargins(0, 0, 0, 0); g.setSpacing(0)
        self.ruler_corner, self.hruler, self.vruler = RulerCorner(self), Ruler(self, True), Ruler(self, False)
        g.addWidget(self.ruler_corner, 0, 0); g.addWidget(self.hruler, 0, 1); g.addWidget(self.vruler, 1, 0)
        g.addWidget(self.scroll, 1, 1)
        self.set_rulers(Ruler.shown)
        for sb in (self.scroll.verticalScrollBar(), self.scroll.horizontalScrollBar()):
            sb.valueChanged.connect(self._update_rulers)
        self.stack.addWidget(self.doc_view)
        self.pages = _PagesArea()
        self.pages.setStyleSheet(f"background:{C['canvas']};")
        self.scroll.setWidget(self.pages)

    def _build_empty_state(self):
        frame = QFrame()
        frame.setObjectName("empty_state")
        lay = QVBoxLayout(frame)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("app_logo", color=C['icon_muted'], size=64).pixmap(QSize(64, 64)))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon_lbl)

        title = QLabel(T("Ningún PDF abierto"))
        title.setObjectName("empty_state_title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        sub = QLabel(T("Abre un archivo PDF para empezar a editarlo"))
        sub.setObjectName("empty_state_sub")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)

        btn = QPushButton(T("Abrir PDF…"))
        btn.setObjectName("empty_state_cta")
        btn.setIcon(get_icon("open", color=C['icon_active']))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.open_requested.emit)
        btn_row = QVBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addLayout(btn_row)

        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return frame

    def allows(self, perm) -> bool:
        """Permiso del documento (pymupdf.PDF_PERM_*): imprimir, copiar, anotar, modificar."""
        return bool(self.doc and self.doc.permissions & perm)

    @property
    def readonly(self) -> bool:
        return bool(self.doc) and not self.allows(pymupdf.PDF_PERM_ANNOTATE)

    def load(self, path, password=None):
        self.doc = open_pdf(path, password)
        self.crypt = self.doc.pdfgm_crypt     # se conserva aunque el documento se reemplace (deshacer)
        self.path = path
        stored = ann_store.extract(self.doc)
        self._undo.clear(); self._redo.clear()
        self.guides = ann_store.read_guides(self.doc)
        self._build()
        for pno, dicts in stored.items():
            if pno < len(self.canvases): self.canvases[pno].anns_from_page(dicts)
        self.stack.setCurrentWidget(self.doc_view)
        self.count_changed.emit(len(self.doc))
        self.dirty = False

    def _build(self):
        self.pages.clear()
        self.canvases.clear(); self._hover_cv = None
        for i in range(len(self.doc)):
            try:
                cv = PageCanvas(i, self.doc, self.zoom)
                cv.set_tool(self.tool)
                self._sync(cv)
                cv.sig_selected.connect(self.props.load)
                cv.sig_link.connect(self._follow_link)
                cv.sig_changed.connect(self._mark_dirty)
                cv.sig_committed.connect(lambda pno: self._push(("ann", pno)))
                cv.sig_before_doc_edit.connect(lambda _: self._push(("doc", self.doc.tobytes())))
                cv.setParent(self.pages)
                cv.installEventFilter(self)              # posición del ratón para las reglas
                cv.guides = self.guides.setdefault(i, {"v": [], "h": []})
                self.pages.items.append(cv)
                self.canvases.append(cv)
            except Exception:
                log.exception(f"_build p{i}")
        self.pages.relayout()
        for cv in self.canvases[:2]: cv.ensure_loaded()
        QTimer.singleShot(0, self._update_visible)

    def _update_visible(self):
        """Renderiza solo las páginas visibles (±1) y libera las lejanas."""
        if not self.canvases: return
        vp = self.scroll.viewport()
        vis = [i for i, cv in enumerate(self.canvases)
               if cv.mapTo(vp, QPoint(0, cv.height())).y() >= 0
               and cv.mapTo(vp, QPoint(0, 0)).y() <= vp.height()] or [0]
        mid = vp.height() // 2
        cur = next((i for i in vis if self.canvases[i].mapTo(vp, QPoint(0, self.canvases[i].height())).y() >= mid), vis[-1])
        if cur != self.current:
            self.current = cur
            self.current_changed.emit(cur)
            self._update_rulers()
        lo = vis[0] - 1
        hi = min(vis[-1], vis[0] + 8) + 1   # tope de seguridad: nunca más de ~10 páginas
        for i, cv in enumerate(self.canvases):
            if lo <= i <= hi: cv.ensure_loaded()
            elif i < lo - 5 or i > hi + 5: cv.unload()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        QTimer.singleShot(0, self._update_visible)

    def _sync(self, cv):
        cv.p_stroke = self.props.stroke_color
        cv.p_fill = self.props.fill_color
        cv.p_width = self.props.line_width
        cv.p_opacity = self.props.opacity
        cv.p_style = self.props.stroke_style
        cv.p_fname = self.props.font_name
        cv.p_fsize = self.props.font_size
        cv.p_fcolor = self.props.text_color

    def set_tool(self, t):
        self.tool = t
        for cv in self.canvases:
            cv.set_tool(t)
            self._sync(cv)

    def delete_selected(self):
        for cv in self.canvases:
            if cv._sel or cv._sel_multi:
                cv._delete_sel()
                break

    # ── deshacer / rehacer ───────────────────────────────────────────────
    def _push(self, entry):
        if entry[0] != "ann": self._doc_rev += 1
        self._undo.append(entry)
        self._redo.clear()
        if len(self._undo) > 100: self._undo.pop(0)
        # las copias completas del PDF pesan: si superan el límite se recorta lo más antiguo
        docs = lambda: [e for e in self._undo if e[0] == "doc"]
        while len(docs()) > 1 and sum(len(e[1]) for e in docs()) > self.MAX_DOC_UNDO_BYTES:
            i = next(i for i, e in enumerate(self._undo) if e[0] == "doc")
            del self._undo[:i + 1]

    def merge_undo(self, n: int):
        """Las últimas `n` entradas se deshacen y rehacen juntas (un solo Ctrl+Z)."""
        if n > 1 and len(self._undo) >= n:
            last = self._undo[-n:]; del self._undo[-n:]
            self._undo.append(("multi", last))

    def can_undo(self): return bool(self._undo)
    def can_redo(self): return bool(self._redo)

    def _apply(self, entry, forward):
        """Aplica una entrada de la pila. Devuelve la entrada inversa."""
        kind = entry[0]
        if kind != "ann": self._doc_rev += 1
        if kind == "ann":
            cv = self.canvases[entry[1]]
            cv.redo() if forward else cv.undo()
            return entry
        if kind == "toc":
            current = self.doc.get_toc(simple=False)
            self.doc.set_toc(entry[1]); self.toc_changed.emit()
            return ("toc", current)
        if kind == "crop":
            return ("crop", self._set_crops(entry[1]))
        if kind == "multi":                   # varias entradas que se deshacen/rehacen juntas
            subs = entry[1] if forward else entry[1][::-1]
            out = [self._apply(e, forward) for e in subs]
            return ("multi", out if forward else out[::-1])
        if kind == "rot":
            _, pages, deg = entry
            self._rotate(pages, deg if forward else -deg)
            return entry
        current = self.doc.tobytes()
        self._replace_doc(entry[1])
        return ("doc", current)

    def undo(self):
        if not self._undo: return
        self._redo.append(self._apply(self._undo.pop(), forward=False))
        self.dirty = True

    def redo(self):
        if not self._redo: return
        self._undo.append(self._apply(self._redo.pop(), forward=True))
        self.dirty = True

    # ── operaciones sobre páginas ────────────────────────────────────────
    def _rotate(self, pages, deg):
        for i in pages:
            if not (0 <= i < len(self.doc)): continue
            pg = self.doc[i]
            old = pg.derotation_matrix
            pg.set_rotation((pg.rotation + deg) % 360)
            if i < len(self.canvases): self.canvases[i].reload_page(old)
        self.pages.relayout()
        self.pages_changed.emit()

    def _set_crops(self, crops: dict) -> dict:
        """Aplica {página: caja de recorte (MediaBox, sin rotar)}; devuelve las anteriores (para deshacer).
        Los objetos se desplazan con el contenido."""
        old = {}
        for i, r in crops.items():
            pg = self.doc[i]; o = pg.cropbox; m = pg.derotation_matrix
            old[i] = tuple(o)
            pg.set_cropbox(pymupdf.Rect(r))
            n = pg.cropbox
            shift = (o.x0 - n.x0, o.y0 - n.y0)
            g = self.guides.get(i)
            if g and (g["v"] or g["h"]):                  # las guías siguen al contenido, como los objetos
                q = pymupdf.Point(0, 0) * m
                t = pymupdf.Point(q.x + shift[0], q.y + shift[1]) * pg.rotation_matrix
                g["v"][:] = [x + t.x for x in g["v"]]; g["h"][:] = [y + t.y for y in g["h"]]
            if i < len(self.canvases): self.canvases[i].reload_page(m, shift)
        self.pages.relayout(); self._update_visible()
        self.pages_changed.emit()
        return old

    def crop_pages(self, crops: dict):
        if not (self.doc and crops): return
        self._push(("crop", self._set_crops(crops)))
        self._mark_dirty()

    def rotate_pages(self, pages, deg):
        if not self.doc: return
        self._rotate(pages, deg)
        self._push(("rot", list(pages), deg))
        self.dirty = True

    def _replace_doc(self, data: bytes):
        """Sustituye el documento por otra versión (mismas páginas)."""
        old = self.doc
        self.doc = pymupdf.open(stream=data, filetype="pdf")
        for cv in self.canvases:
            m = old[cv.page_num].derotation_matrix
            cv.doc = self.doc
            cv.reload_page(m)
        self.pages.relayout()
        old.close()
        self.doc_replaced.emit()

    def zoom_to(self, z):
        self.zoom = z
        Ann.SCALE = z
        for cv in self.canvases: cv.re_render(z)
        self.pages.relayout()
        self._update_visible()
        self._update_rulers()

    def set_page_layout(self, mode):
        cur = self.current
        _PagesArea.mode = mode
        self.pages.relayout(); self._update_visible()
        if self.canvases: self.go_to(cur)

    def go_to(self, idx):
        """Lleva la parte superior de la página `idx` arriba de la vista."""
        if 0 <= idx < len(self.canvases):
            self.scroll.verticalScrollBar().setValue(self.canvases[idx].y() - _PagesArea.MARGIN // 2)
            self._update_visible()

    def jump(self, idx):
        """Salto que se puede deshacer con Atrás (Alt+←)."""
        if 0 <= idx < len(self.canvases) and idx != self.current:
            self._back.append(self.current); self._fwd.clear()
        self.go_to(idx)

    def back(self):
        if self._back:
            self._fwd.append(self.current); self.go_to(self._back.pop())

    def forward(self):
        if self._fwd:
            self._back.append(self.current); self.go_to(self._fwd.pop())

    def _follow_link(self, l):
        if l.get("kind") == pymupdf.LINK_URI:
            uri = l.get("uri", "")
            if not safe_link(uri):                          # file://, rutas de red, ms-msdt:, javascript:…
                QMessageBox.warning(self, T("Abrir enlace"), Tf("Por seguridad, este tipo de enlace no se abre desde el "
                                                              "PDF:\n\n{0}", uri[:300])); return
            if QMessageBox.question(self, T("Abrir enlace"), Tf("¿Abrir en el navegador?\n\n{0}", uri)) \
                    == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl(uri))
        elif l.get("page", -1) >= 0:
            self.jump(l["page"])

    # ── reglas ──
    def set_rulers(self, on: bool):
        for w in (self.ruler_corner, self.hruler, self.vruler): w.setVisible(on)

    def ruler_page(self):
        """Página de referencia de las reglas: la que está bajo el ratón o, si no, la actual."""
        if self._hover_cv is not None: return self._hover_cv
        return self.canvases[self.current] if 0 <= self.current < len(self.canvases) else None

    def canvas_at(self, gpos):
        for cv in self.canvases:
            if cv.isVisible() and cv.rect().contains(cv.mapFromGlobal(gpos)): return cv
        return None

    def ruler_drag(self, axis, gpos, done=False):
        """Guía arrastrada desde una regla: vista previa en la página bajo el ratón; al soltar se crea."""
        cv = self.canvas_at(gpos)
        if self._gprev is not None and self._gprev is not cv:
            self._gprev._guide_preview = None; self._gprev.update()
        self._gprev = cv
        if cv is None: return
        q = cv.mapFromGlobal(gpos); v = (q.x() if axis == "v" else q.y()) / cv._gk()
        if done:
            cv._guide_preview = None; self._gprev = None
            cv.add_guide(axis, v)
        else:
            cv._guide_preview = (axis, v)
        cv.update()

    def clear_guides(self):
        if any(g["v"] or g["h"] for g in self.guides.values()): self._mark_dirty()
        for g in self.guides.values(): g["v"].clear(); g["h"].clear()
        for cv in self.canvases: cv.update()

    def _update_rulers(self, *_):
        if self.hruler.isVisible():
            self.hruler.update(); self.vruler.update()

    def eventFilter(self, obj, ev):
        if isinstance(obj, PageCanvas):
            t = ev.type()
            if t == QEvent.Type.MouseMove:
                self._hover_cv = obj
                self.hruler.cursor_g = self.vruler.cursor_g = ev.globalPosition().toPoint()
                self._update_rulers()
            elif t == QEvent.Type.Leave:
                self._hover_cv = None
                self.hruler.cursor_g = self.vruler.cursor_g = None
                self._update_rulers()
            return False
        if ev.type() == QEvent.Type.Wheel and ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.wheel_zoom.emit(1 if ev.angleDelta().y() > 0 else -1)      # Ctrl + rueda = zoom
            return True
        return super().eventFilter(obj, ev)

    def fit(self, mode):
        """Zoom para que la página actual ocupe el ancho ('width') o entre entera ('page')."""
        if not self.canvases: return
        cur = self.current
        r = self.doc[cur].rect
        vp = self.scroll.viewport()
        per_row = 1 if _PagesArea.mode == "continuous" else 2
        z = (vp.width() - 2 * _PagesArea.MARGIN - _PagesArea.HGAP * (per_row - 1)) / (r.width * per_row)
        if mode == "page":
            z = min(z, (vp.height() - _PagesArea.MARGIN - _PagesArea.LABEL_H) / r.height)
        self.zoom_to(max(0.25, min(z, 6.0)))
        self.go_to(cur)

    def highlight_search(self, page_num, rects):
        for cv in self.canvases: cv.set_search_rects([])
        if 0 <= page_num < len(self.canvases):
            cv = self.canvases[page_num]
            cv.set_search_rects(rects)
            if rects:                                   # centrar la coincidencia en la vista
                r = cv._ps(rects[0])
                self.scroll.verticalScrollBar().setValue(int(cv.y() + r.center().y() - self.scroll.viewport().height() / 2))
                self.scroll.horizontalScrollBar().setValue(int(cv.x() + r.center().x() - self.scroll.viewport().width() / 2))
                self._update_visible()
            else:
                self.go_to(page_num)

    def _mark_dirty(self, *_):
        self.dirty = True
        self.annotations_changed.emit()

    def flatten(self) -> int:
        """Aplana: comentarios, marcas, sellos, firmas visuales, dibujos y formularios pasan a ser parte del
        contenido de la página (ya no se pueden editar). No toca las zonas marcadas para tachado definitivo.
        Devuelve cuántos objetos se aplanaron. Se puede deshacer."""
        pages = {}
        for i, cv in enumerate(self.canvases):
            dicts = [d for a, d in zip(cv.anns, cv.anns_to_page()) if a.kind != "redact"]
            if dicts: pages[i] = dicts
        native = sum(1 for pg in self.doc for _ in pg.annots()) + sum(1 for pg in self.doc for _ in pg.widgets())
        if not pages and not native: return 0
        subs = [("doc", self.doc.tobytes())]
        out = ann_store.export(self.doc, pages)
        try:
            out.bake(annots=True, widgets=True)
            data = out.tobytes()
        finally:
            out.close()
        for i in pages:                       # los objetos pasan al contenido: quitarlos del lienzo (deshacible)
            cv = self.canvases[i]
            cv._desel(); cv._history.append([a.clone() for a in cv.anns]); cv._redo_stack.clear()
            cv.anns = [a for a in cv.anns if a.kind == "redact"]
            subs.append(("ann", i))
        self._replace_doc(data)
        for cv in self.canvases:
            if cv._base is not None: cv._redraw()
        self._push(("multi", subs))
        self._mark_dirty()
        self.pages_changed.emit()
        return sum(len(v) for v in pages.values()) + native

    def set_toc(self, toc: list):
        """Reemplaza los marcadores del documento (se puede deshacer)."""
        old = self.doc.get_toc(simple=False)
        self.doc.set_toc(toc)
        self._push(("toc", old))
        self._mark_dirty()

    def apply_doc_change(self, fn):
        """Cambia el contenido del PDF con `fn(doc)` (marca de agua, tachado…): se puede deshacer."""
        self._push(("doc", self.doc.tobytes()))
        result = fn(self.doc)
        for cv in self.canvases:
            if cv._base is not None:
                cv._render(); cv._load_text(); cv._redraw()
        self._mark_dirty()
        self.pages_changed.emit()
        return result

    def edit_form(self, page_no, xref, value):
        """Rellena un campo del formulario (cambia el PDF: se puede deshacer)."""
        from core.pdf_tools import set_field
        self._push(("doc", self.doc.tobytes()))
        set_field(self.doc, page_no, xref, value)
        cv = self.canvases[page_no]
        if cv._base is not None:
            cv._render(); cv._load_text(); cv._redraw()
        self._mark_dirty()

    def save(self, path):
        if not self.doc: return
        pages = {i: cv.anns_to_page() for i, cv in enumerate(self.canvases) if cv.anns}
        out = ann_store.export(self.doc, pages, self.guides)
        try:
            save_pdf(out, path, self.crypt)
        finally:
            out.close()
        self.path = path
        self.dirty = False
        self._doc_rev = self._saved_rev = 0
        recovery.remove(self.uid)

    def autosave(self):
        """Copia de seguridad de los cambios sin guardar (ver core.recovery)."""
        if not (self.doc and self.dirty): return
        try:
            pages = {i: cv.anns_to_page() for i, cv in enumerate(self.canvases) if cv.anns}
            data = None
            if self._doc_rev and self._doc_rev != self._saved_rev and not self.crypt:
                data = self.doc.tobytes()
            recovery.save(self.uid, self.path or "", pages, data)
            self._saved_rev = self._doc_rev
        except Exception:
            log.exception("autosave")

    def remember_position(self):
        """Guarda la página y el zoom para volver ahí al reabrir el documento."""
        if self.doc is not None and self.path and self.canvases:
            try:
                AppSettings().set_position(self.path, self.current, self.zoom)
            except Exception:
                log.debug("remember_position", exc_info=True)

    def close(self):
        self.remember_position()
        recovery.remove(self.uid)
        self._doc_rev = self._saved_rev = 0
        try:
            if self.doc: self.doc.close()
        except Exception:
            log.debug("close doc", exc_info=True)
        self.doc = None
        self.path = None
        self.dirty = False
        self.crypt = None; self._crypt_ok = False
        self._back.clear(); self._fwd.clear()
        self._undo.clear(); self._redo.clear()
        self.canvases.clear(); self._hover_cv = None
        self.pages.clear()
        self.stack.setCurrentWidget(self.empty_state)
        self.count_changed.emit(0)

    def print_doc(self):
        if not self.doc: return
        if not self.allows(pymupdf.PDF_PERM_PRINT):
            QMessageBox.information(self, T("Documento protegido"), T("El autor de este documento no permite imprimirlo."))
            return
        from ui.print_ui import print_viewer
        print_viewer(self)

    def export_copy(self):
        """Copia del documento con las anotaciones de Pdfgm incluidas."""
        pages = {i: cv.anns_to_page() for i, cv in enumerate(self.canvases) if cv.anns}
        return ann_store.export(self.doc, pages)
