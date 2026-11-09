# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Canvas de página: Dibujo, selección e interacción con anotaciones"""
from core.i18n import T, Tf
import math
import base64
import pymupdf
from PyQt6.QtWidgets import (QLabel, QFileDialog, QDialog, QRubberBand,
                             QScrollArea, QToolTip)
from PyQt6.QtCore import (Qt, pyqtSignal, QPointF, QRectF, QRect, QSize, QPoint,
                          QByteArray)
from PyQt6.QtGui import (QPixmap, QImage, QPainter, QPen, QColor, QCursor)
from models.annotation import Ann
from dialogs.text_dialog import TextDialog
from core.constants import (HANDLE_CURSORS, T_ARROW, T_COMMENT, T_DARROW, T_HAND, T_IMAGE, T_INK, T_LASSO, T_LINE, T_MEASURE, T_OCR_REGION, T_QRLENS, T_SELECT, T_SIGN, T_STAMP, T_TEXT, T_TEXTBOX, T_TXTSEL, T_FILL)
from core.logger import log
from ui.canvas_draw import DrawMixin
from ui.canvas_edit import EditMixin
from ui.canvas_text import TextMixin
from ui.canvas_guides import GuidesMixin
from ui.canvas_arrange import ArrangeMixin
from ui.canvas_fill import FillMixin
from ui.canvas_images import ImagesMixin
from ui.canvas_measure import MeasureMixin, Scale
from ui import qr_lens
from core.settings import AppSettings
from ui.styles import C



_ROT_CURSOR = None


def _rot_cursor():
    """Cursor de flechas curvas para girar (dibujado una vez)."""
    global _ROT_CURSOR
    if _ROT_CURSOR is None:
        from PyQt6.QtSvg import QSvgRenderer
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke-linecap="round" '
               'stroke-linejoin="round"><path d="M5 12a7 7 0 0 1 12-5M19 12a7 7 0 0 1-12 5" stroke="white" stroke-width="4"/>'
               '<path d="M17 3v4h-4M7 21v-4h4" stroke="white" stroke-width="4"/>'
               '<path d="M5 12a7 7 0 0 1 12-5M19 12a7 7 0 0 1-12 5" stroke="black" stroke-width="1.8"/>'
               '<path d="M17 3v4h-4M7 21v-4h4" stroke="black" stroke-width="1.8"/></g></svg>')
        pm = QPixmap(26, 26); pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm); QSvgRenderer(QByteArray(svg.encode())).render(p); p.end()
        _ROT_CURSOR = QCursor(pm, 13, 13)
    return _ROT_CURSOR


class PageCanvas(QLabel, DrawMixin, EditMixin, TextMixin, GuidesMixin, ArrangeMixin, FillMixin, ImagesMixin, MeasureMixin):
    pending_signature = None               # PNG en base64 de la firma o sello a colocar
    pick_box = None                        # (callback, (ancho, alto) en pt): elegir con el ratón dónde va la firma digital
    pick_label = None                      # texto del recuadro de vista previa (None = «Firma»)
    fmt_clip = None                        # formato copiado con «Copiar formato» (dict de estilo)
    night = False                          # modo de lectura nocturno (colores invertidos y suavizados)
    rotation_step = None                   # grados por paso con Ctrl (de Preferencias; se lee una vez)
    sig_changed = pyqtSignal(int)          # hubo un cambio (para la bandera dirty)
    sig_committed = pyqtSignal(int)        # se registró un paso de deshacer en esta página
    sig_before_doc_edit = pyqtSignal(int)  # se va a modificar el contenido del PDF
    sig_selected = pyqtSignal(object)
    sig_search_highlight = pyqtSignal(list)
    sig_link = pyqtSignal(dict)            # clic en un enlace del PDF (interno o web)

    def __init__(self, page_num, doc, zoom, parent=None):
        super().__init__(parent)
        self.page_num = page_num
        self.doc = doc
        self.zoom = zoom
        self.tool = T_SELECT
        self.anns = []
        self._search_rects = []
        self.p_stroke = QColor(C['accent'])
        self.p_fill = None
        self.p_width = 1.5
        self.p_opacity = 1.0
        self.p_style = "solid"
        self.p_fname = "Arial"
        self.p_fsize = 12
        self.p_fcolor = QColor("#111111")
        self._sel = None
        self._sel_multi = []
        self._handle = -1
        self._moving = False
        self._drawing = False
        self._rotating = False
        self._drag0 = QPointF()
        self._dragl = QPointF()
        self._rot_center = QPointF()
        self._rot_start = 0.0
        self._history = []
        self._redo_stack = []
        self._pending = None   # estado antes de la interacción en curso
        self._rb = None
        self._rb_origin = QPoint()
        self._tsel_start = None
        self._tsel_rects = []
        self._tsel_text = ""
        self._words = []
        self._links = []       # [(Rect visible, enlace de PyMuPDF)]
        self._on_link = False
        self._prect = None
        self._spans = []
        self._ocr_rect = None
        self._measure = None                # [inicio, fin] de la herramienta Medir (px)
        self._mpoly_reset()                 # vértices de Medir perímetro / área (px)
        self.init_guides()
        self._inline = None
        self._inline_ann = None
        self._ink = None
        self._pan = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self._base = None      # imagen de la página; None = aún no renderizada
        self._calc_size()

    def _calc_size(self):
        """Tamaño en pantalla de la página sin renderizarla."""
        pg = self.doc[self.page_num]
        self._prect = pg.rect
        ir = (pg.rect * pymupdf.Matrix(self.zoom, self.zoom)).irect
        self._bw, self._bh = ir.width, ir.height
        self.setFixedSize(self._bw, self._bh)

    def ensure_loaded(self):
        """Renderiza la página si no lo está (carga perezosa)."""
        if self._base is None:
            self._render()
            self._load_text()
            self._redraw()

    def unload(self):
        """Libera la imagen y el texto de la página; se regeneran al volver a verla."""
        if self._base is None or self._inline or self._drawing or self._moving: return
        self._base = None
        self._words = []
        self._spans = []
        self.clear()

    def _render(self):
        try:
            pg = self.doc[self.page_num]
            mat = pymupdf.Matrix(self.zoom, self.zoom)
            pix = pg.get_pixmap(matrix=mat, alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            if PageCanvas.night:                  # invertir y acotar: fondo gris oscuro, texto gris claro
                img = img.convertToFormat(QImage.Format.Format_RGB32); img.invertPixels()
                p = QPainter(img)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten); p.fillRect(img.rect(), QColor(46, 48, 52))
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Darken); p.fillRect(img.rect(), QColor(214, 216, 220))
                p.end()
            self._base = QPixmap.fromImage(img)
            self._prect = pg.rect
            self._bw, self._bh = self._base.width(), self._base.height()
            self.setFixedSize(self._bw, self._bh)
        except Exception:
            log.exception(f"render p{self.page_num}")

    def _load_text(self):
        try:
            pg = self.doc[self.page_num]
            rot = pg.rotation_matrix          # el texto se extrae sin rotar; se pasa a lo visible
            self._words = [(*(pymupdf.Rect(w[:4]) * rot), *w[4:]) for w in pg.get_text("words")]
            self._links = [(pymupdf.Rect(l["from"]), l) for l in pg.get_links()        # ya en la página visible
                           if l.get("kind") in (pymupdf.LINK_GOTO, pymupdf.LINK_URI, pymupdf.LINK_NAMED)]
            self._spans = []
            for b in pg.get_text("rawdict").get("blocks", []):
                if b.get("type") != 0: continue
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        chars = span.get("chars", [])
                        if not chars: continue
                        self._spans.append({
                            "text": " ".join(c["c"] for c in chars),
                            "bbox": span["bbox"],
                            "vbbox": tuple(pymupdf.Rect(span["bbox"]) * rot),
                            "font": span.get("font", "Arial"),
                            "size": max(4, span.get("size", 12)),
                            "color": span.get("color", 0),
                            "origin": span.get("origin", (span["bbox"][0], span["bbox"][3]))
                        })
        except Exception as e:
            log.warning(f"load_text p{self.page_num}: {e}")

    def _redraw(self):
        if self._base is None: return
        try:
            pm = QPixmap(self._base)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            if self.tool == T_TEXT:
                for sp in self._spans:
                    r = self._ps(sp["vbbox"])
                    p.fillRect(r, QColor(255, 220, 50, 40))
                    p.setPen(QPen(QColor(255, 180, 0, 130), 1, Qt.PenStyle.DotLine))
                    p.drawRect(r)
            for r in map(self._ps, self._search_rects):         # multiplicar: el texto encontrado sigue legible
                if not self.night: p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
                p.fillRect(r, QColor(255, 210, 0, 150))
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            for a in self.anns:
                if not a.hidden: self._draw(p, a)
            if self._tsel_rects:
                if not self.night: p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
                for r in self._tsel_rects:
                    p.fillRect(r, QColor(120, 180, 255, 140))
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            p.end()
            self.setPixmap(pm)
        except Exception:
            log.exception(f"redraw p{self.page_num}")

    def _ps(self, bbox):
        if not self._prect: return QRectF()
        w, h = self._bw, self._bh
        sx = w / self._prect.width
        sy = h / self._prect.height
        return QRectF(bbox[0]*sx, bbox[1]*sy, (bbox[2]-bbox[0])*sx, (bbox[3]-bbox[1])*sy)

    def _s2p(self, sx, sy):
        if not self._prect: return 0.0, 0.0
        w, h = self._bw, self._bh
        return sx * self._prect.width / w, sy * self._prect.height / h

    def _p2s(self, px, py):
        if not self._prect: return 0.0, 0.0
        w, h = self._bw, self._bh
        return px * w / self._prect.width, py * h / self._prect.height

    def _srect2p(self, x1, y1, x2, y2):
        if not self._prect: return pymupdf.Rect(0, 0, 1, 1)
        w, h = self._bw, self._bh
        rw, rh = self._prect.width, self._prect.height
        return pymupdf.Rect(min(x1,x2)*rw/w, min(y1,y2)*rh/h, max(x1,x2)*rw/w, max(y1,y2)*rh/h)

    @staticmethod
    def _state(anns):
        skip = ("selected", "comment_visible", "id")
        return [{k: v for k, v in a.to_dict().items() if k not in skip} for a in anns]

    def _snap(self):
        """Marca el inicio de una interacción que puede modificar objetos."""
        self._pending = [a.clone() for a in self.anns]

    def _commit(self):
        """Cierra la interacción: si algo cambió, crea un paso de deshacer."""
        before, self._pending = self._pending, None
        if before is None or self._state(before) == self._state(self.anns):
            return
        for a in before: a.selected = False
        self._history.append(before)
        self._redo_stack.clear()
        if len(self._history) > 80:
            self._history.pop(0)
        self.sig_committed.emit(self.page_num)
        self.sig_changed.emit(self.page_num)

    def undo(self):
        if not self._history: return
        self._redo_stack.append([a.clone() for a in self.anns])
        self.anns = self._history.pop()
        self._sel_multi.clear()
        self._desel()
        self._redraw()
        self.sig_changed.emit(self.page_num)

    def redo(self):
        if not self._redo_stack: return
        self._history.append([a.clone() for a in self.anns])
        self.anns = self._redo_stack.pop()
        self._sel_multi.clear()
        self._desel()
        self._redraw()
        self.sig_changed.emit(self.page_num)

    def set_tool(self, t):
        self.tool = t
        self._close_inline()
        cur = {
            T_SELECT: Qt.CursorShape.ArrowCursor, T_LASSO: Qt.CursorShape.CrossCursor,
            T_TXTSEL: Qt.CursorShape.IBeamCursor, T_TEXT: Qt.CursorShape.IBeamCursor,
            T_TEXTBOX: Qt.CursorShape.CrossCursor, T_COMMENT: Qt.CursorShape.PointingHandCursor,
            T_OCR_REGION: Qt.CursorShape.CrossCursor, T_IMAGE: Qt.CursorShape.ArrowCursor,
            T_HAND: Qt.CursorShape.OpenHandCursor
        }.get(t, Qt.CursorShape.CrossCursor)
        self.setCursor(cur)
        self._tool_cursor = cur
        if t not in (T_SELECT, T_LASSO, T_TXTSEL): self._desel()
        if t != T_MEASURE: self._measure = None; self._mpoly_reset()
        if t != T_QRLENS: qr_lens.hide()
        if t != T_TXTSEL:
            self._tsel_rects = []
            self._tsel_text = ""
        self._redraw()

    def _desel(self):
        for a in self.anns: a.selected = False
        self._sel = None
        self._handle = -1
        self._sel_multi.clear()
        self.sig_selected.emit(None)

    def _setsel(self, a):
        self._desel()
        a.selected = True
        self._sel = a
        self.sig_selected.emit(a)

    # ── herramienta Medir ──
    def _measure_snap(self, pt, mods):
        """Con Ctrl el ángulo avanza en pasos (como las líneas)."""
        a = self._measure[0]
        if not mods & Qt.KeyboardModifier.ControlModifier: return pt
        d = math.hypot(pt.x() - a.x(), pt.y() - a.y()); step = self._step()
        ang = round(math.degrees(math.atan2(pt.y() - a.y(), pt.x() - a.x())) / step) * step
        return QPointF(a.x() + d * math.cos(math.radians(ang)), a.y() + d * math.sin(math.radians(ang)))

    def measure_info(self):
        """(distancia, Δx, Δy, ángulo) en puntos PDF de la medida actual, o None."""
        if not self._measure or not self._prect or not self._bw: return None
        a, b = self._measure; k = self._prect.width / self._bw
        dx, dy = (b.x() - a.x()) * k, (b.y() - a.y()) * k
        return math.hypot(dx, dy), dx, dy, -math.degrees(math.atan2(dy, dx))

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self.guides_visible and (self.guides["v"] or self.guides["h"]) or self._guide_preview or self._snap_lines:
            p = QPainter(self); self.paint_guides(p); p.end()
        if getattr(self, "_pick_ghost", None) and PageCanvas.pick_box and not getattr(self, "_picking", False):
            self._paint_pick_ghost()
        if self.tool == T_QRLENS and self.underMouse():           # marcar los QR que la lupa puede leer
            p = QPainter(self); p.setPen(QPen(QColor(C["accent"]), 1.5, Qt.PenStyle.DashLine)); k = self._gk()
            for r, _ in qr_lens.qr_codes(self.doc, self.page_num):
                p.drawRect(QRectF(r.x0 * k - 3, r.y0 * k - 3, r.width * k + 6, r.height * k + 6))
            p.end()
        if self.tool == T_MEASURE: self._paint_mpoly()
        info = self.measure_info()
        if not info or info[0] < 0.5: return
        from ui.ruler import Ruler, fmt
        a, b = self._measure; u = Ruler.unit
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = QColor(C["accent"])
        p.setPen(QPen(acc, 1.5)); p.drawLine(a, b)
        for q in (a, b):                                   # topes perpendiculares
            n = QPointF(-(b.y() - a.y()), b.x() - a.x()); ln = math.hypot(n.x(), n.y()) or 1
            n = QPointF(n.x() / ln * 6, n.y() / ln * 6); p.drawLine(q - n, q + n)
        ang = info[3] + 0.0 if abs(info[3]) >= 0.05 else 0.0
        txt = Tf("{0}  ·  {1}°   (ancho {2}, alto {3})", Scale.length(info[0]), f"{ang:.1f}", Scale.length(abs(info[1])),
                 Scale.length(abs(info[2])))
        fm = p.fontMetrics(); w, h = fm.horizontalAdvance(txt) + 12, fm.height() + 6
        x = min(max(b.x() + 10, 2), self.width() - w - 2); y = min(max(b.y() + 10, 2), self.height() - h - 2)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(acc); p.drawRoundedRect(QRectF(x, y, w, h), 4, 4)
        p.setPen(QColor("#ffffff")); p.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, txt)
        p.end()

    def _pick_rect(self, pos) -> QRectF:
        """Recuadro del tamaño de la firma centrado en `pos` (px), sin salirse de la página."""
        w, h = (v * self._gk() for v in PageCanvas.pick_box[1])
        x = min(max(pos.x() - w / 2, 0), max(self.width() - w, 0)); y = min(max(pos.y() - h / 2, 0), max(self.height() - h, 0))
        return QRectF(x, y, w, h)

    def _paint_pick_ghost(self):
        """Vista previa de dónde quedará la firma: sigue al ratón; un clic la coloca."""
        r = self._pick_rect(self._pick_ghost)
        p = QPainter(self); acc = QColor(C["accent"])
        fill = QColor(acc); fill.setAlpha(40); p.fillRect(r, fill)
        p.setPen(QPen(acc, 1.5, Qt.PenStyle.DashLine)); p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, PageCanvas.pick_label or T("Firma"))
        p.end()

    def leaveEvent(self, ev):
        if getattr(self, "_pick_ghost", None):
            self._pick_ghost = None; self.update()
        if self.tool == T_QRLENS: qr_lens.hide()
        super().leaveEvent(ev)

    def set_search_rects(self, rects):
        self._search_rects = rects
        self._redraw()

    def mousePressEvent(self, ev):
        pt = QPointF(ev.position())
        self.setFocus()
        if PageCanvas.pick_box and ev.button() == Qt.MouseButton.LeftButton:   # elegir el recuadro de la firma
            self._rb_origin = ev.position().toPoint()
            if not self._rb: self._rb = QRubberBand(QRubberBand.Shape.Rectangle, self)
            self._rb.setGeometry(QRect(self._rb_origin, QSize())); self._rb.show()
            self._picking = True
            return
        if self.tool == T_QRLENS and ev.button() == Qt.MouseButton.LeftButton:
            t = qr_lens.copy(self, ev.position())
            w = self.window()
            if hasattr(w, "_status"): w._status(T("Texto del código QR copiado.") if t else T("No hay un código QR aquí."))
            return
        if ev.button() == Qt.MouseButton.RightButton:
            if self._guide_menu(pt, ev.globalPosition().toPoint()):
                return
            if self.tool == T_TXTSEL and self._tsel_text:
                self._tsel_menu(ev.globalPosition().toPoint())
                return
            self._ctx_menu(pt, ev.globalPosition().toPoint())
            return
        if ev.button() != Qt.MouseButton.LeftButton: return
        if self._sel and self.tool not in (T_TXTSEL, T_HAND, T_INK):   # aunque Ctrl esté presionado
            h = self._sel.hit_handle(pt)
            if h < 0 and self._sel.rot_zone(pt):
                self._rotating = True
                self._rot_center = self._sel.brect().center()
                self._rot_start = math.degrees(math.atan2(pt.y() - self._rot_center.y(), pt.x() - self._rot_center.x())) - self._sel.rotation
                self._snap()
                return
            if h >= 0:
                self._snap(); self._handle = h; self._dragl = pt
                return
        self._mv0 = None; self._snap_lines = []
        if self.tool == T_SELECT and self._guide_press(pt):
            return
        if self.tool in (T_SELECT, T_TXTSEL) and not any(a.hit(pt) for a in self.anns):
            l = self._link_at(pt)
            if l:
                self.sig_link.emit(l)
                return
        try:
            if self.tool == T_IMAGE:
                path, _ = QFileDialog.getOpenFileName(self, T("Insertar Imagen"), "",
                                                      T("Imágenes (*.png *.jpg *.jpeg *.bmp *.webp *.tiff *.svg)"))
                if path:
                    try:
                        with open(path, "rb") as f:
                            img_b64 = base64.b64encode(f.read()).decode('utf-8')
                        a = Ann("image", x1=pt.x(), y1=pt.y(), x2=pt.x()+200, y2=pt.y()+200, image_data=img_b64)
                        self._snap()
                        self.anns.append(a)
                        self._setsel(a)
                        self._redraw()
                        self._commit()
                    except Exception:
                        log.exception("Image insert")
                return
            if self.tool == T_TXTSEL:
                self._tsel_start = pt
                self._tsel_rects = []
                self._tsel_text = ""
                self._redraw()
                return
            if self.tool == T_LASSO:
                self._rb_origin = ev.position().toPoint()
                if not self._rb: self._rb = QRubberBand(QRubberBand.Shape.Rectangle, self)
                self._rb.setGeometry(QRect(self._rb_origin, QSize()))
                self._rb.show()
                return
            if self.tool == T_TEXT:
                for sp in self._spans:
                    r = self._ps(sp["vbbox"])
                    if r.adjusted(-4,-4,4,4).contains(pt):
                        self._edit_native(sp)
                        return
                self._text_dlg(pt)
                return
            if self.tool == T_COMMENT:
                self._add_comment(pt)
                return
            if self.tool == T_MEASURE:
                if type(self).measure_mode != "dist": self._mpoly_click(pt, ev.modifiers()); return
                self._measure = [pt, pt]; self.update()
                return
            if self.tool == T_OCR_REGION:
                self._rb_origin = ev.position().toPoint()
                if not self._rb: self._rb = QRubberBand(QRubberBand.Shape.Rectangle, self)
                self._rb.setGeometry(QRect(self._rb_origin, QSize()))
                self._rb.show()
                return
            if self.tool == T_SELECT:
                ctrl = ev.modifiers() & Qt.KeyboardModifier.ControlModifier
                hit = None
                for a in reversed(self.anns):
                    if a.hit(pt):
                        hit = a
                        break
                if hit:
                    if ctrl:
                        self._snap()
                        if hit in self._sel_multi:
                            self._sel_multi.remove(hit)
                            hit.selected = False
                        else:
                            self._sel_multi.append(hit)
                            hit.selected = True
                        self._sel = hit
                        self._redraw()
                        return
                    else:
                        self._snap()
                        if hit not in self._sel_multi: self._pick(hit)    # si ya estaba en la selección, se mueve todo
                        else: self._sel = hit
                        self._moving = True
                        self._dragl = pt
                        if hit.kind == "comment":
                            hit.comment_visible = not hit.comment_visible
                else:
                    if not ctrl:
                        self._sel_multi.clear()
                        self._desel()
                self._redraw()
                return
            if self.tool == T_INK:                      # lápiz: el trazo sigue al ratón
                self._snap()
                self._ink = Ann("ink", x1=pt.x(), y1=pt.y(), x2=pt.x(), y2=pt.y(), points=[[pt.x(), pt.y()]],
                                stroke=self.p_stroke.name(), stroke_width=max(self.p_width, 2), opacity=self.p_opacity)
                self.anns.append(self._ink)
                return
            if self.tool == T_FILL:                     # rellenar y firmar: símbolo con un clic
                self._place_fill(pt)
                return
            if self.tool in (T_SIGN, T_STAMP) and PageCanvas.pending_signature:
                self._place_signature(pt, 150 if self.tool == T_STAMP else 170)
                return
            if self.tool == T_HAND:                     # mano: desplazar la vista arrastrando
                sa = self._scroll_area()
                self._pan = (ev.globalPosition(), sa.horizontalScrollBar().value(), sa.verticalScrollBar().value()) if sa else None
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return
            self._snap()
            pt = self._magnet_pt(pt, ev.modifiers())
            self._drawing = True
            self._drag0 = pt
            self._dragl = pt
        except Exception:
            log.exception("mousePressEvent")

    def _link_at(self, pt):
        for r, l in self._links:
            if self._ps(r).contains(pt): return l
        return None

    def _hover_link(self, pt) -> bool:
        """Cursor de mano y destino del enlace bajo el ratón (herramientas de lectura)."""
        l = self._link_at(pt) if self.tool in (T_SELECT, T_TXTSEL) and not self._sel else None
        if l:
            if not self._on_link:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                self.setToolTip(l.get("uri") or f"Ir a la página {l.get('page', 0) + 1}")
            self._on_link = True
            return True
        if self._on_link:
            self._on_link = False
            self.setCursor(getattr(self, "_tool_cursor", Qt.CursorShape.ArrowCursor))
            self.setToolTip("")
        return False

    def mouseMoveEvent(self, ev):
        pt = QPointF(ev.position())
        if getattr(self, "_picking", False):
            self._rb.setGeometry(QRect(self._rb_origin, ev.position().toPoint()).normalized())
            return
        if PageCanvas.pick_box:                                # el recuadro de la firma sigue al ratón
            self._pick_ghost = ev.position(); self.update()
            return
        if self.tool == T_QRLENS:
            qr_lens.move(self, ev.position(), ev.globalPosition().toPoint()); self.update()
            return
        if ev.buttons() == Qt.MouseButton.NoButton and self._hover_link(pt):
            return
        if self.tool == T_INK and self._ink:
            self._ink.points.append([pt.x(), pt.y()]); self._ink.fit_bbox(); self._redraw()
            return
        if self.tool == T_HAND and self._pan:
            g0, h0, v0 = self._pan; d = ev.globalPosition() - g0; sa = self._scroll_area()
            sa.horizontalScrollBar().setValue(int(h0 - d.x())); sa.verticalScrollBar().setValue(int(v0 - d.y()))
            return
        if self._guide_move(pt):
            return
        if ev.buttons() == Qt.MouseButton.NoButton and self.tool == T_SELECT and self._guide_hover(pt):
            return
        if self.tool == T_MEASURE and type(self).measure_mode != "dist":
            self._mpoly_move(pt, ev.modifiers())
            return
        if self.tool == T_MEASURE and self._measure and ev.buttons() & Qt.MouseButton.LeftButton:
            self._measure[1] = self._measure_snap(pt, ev.modifiers()); self.update()
            return
        try:
            if self.tool in (T_LASSO, T_OCR_REGION) and self._rb:
                self._rb.setGeometry(QRect(self._rb_origin, ev.position().toPoint()).normalized())
                return
            if self.tool == T_TXTSEL and self._tsel_start:
                if (pt - self._tsel_start).manhattanLength() > 3:
                    self._update_tsel(self._tsel_start, pt)
                return
            if (self._sel and ev.buttons() == Qt.MouseButton.NoButton and self.tool not in (T_TXTSEL, T_HAND, T_INK)
                    and not (self._moving or self._rotating or self._handle >= 0)):     # solo cursor al pasar el ratón
                h = self._sel.hit_handle(pt)
                if h < 0 and self._sel.rot_zone(pt):
                    self.setCursor(_rot_cursor()); return
                if h >= 0:
                    self.setCursor(HANDLE_CURSORS.get(h, Qt.CursorShape.SizeAllCursor)); return
                if self.tool == T_SELECT:
                    self.setCursor(Qt.CursorShape.SizeAllCursor if self._sel.hit(pt) else Qt.CursorShape.ArrowCursor)
                    return
                self.setCursor(getattr(self, "_tool_cursor", Qt.CursorShape.CrossCursor))
            if self._rotating or self._handle >= 0:
                if self._rotating and self._sel:
                    dx = pt.x() - self._rot_center.x()
                    dy = pt.y() - self._rot_center.y()
                    rot = (math.degrees(math.atan2(dy,dx)) - self._rot_start) % 360
                    if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:       # Shift queda libre para otra función
                        step = self._step()                             # con Ctrl/Shift: de N en N grados
                        rot = (round(rot / step) * step) % 360
                    self._sel.rotation = rot
                    QToolTip.showText(ev.globalPosition().toPoint(), f"{rot:.0f}°", self)
                    self._redraw()
                    return
                if self._handle >= 0 and self._sel:
                    pt = self._magnet_pt(pt, ev.modifiers(), [self._sel])
                    dx = pt.x() - self._dragl.x()
                    dy = pt.y() - self._dragl.y()
                    self._sel.resize(self._handle, dx, dy)
                    self._dragl = pt
                    self._redraw()
                    return
            if self.tool == T_SELECT:
                if self._moving and self._sel:
                    targets = self._sel_multi if self._sel_multi else [self._sel]
                    self._move_snapped(targets, pt, ev.modifiers())
                    self._redraw()
                    return
            if self._drawing:
                pt = self._magnet_pt(pt, ev.modifiers())
                if ev.modifiers() & Qt.KeyboardModifier.ControlModifier: self._snap_lines = []
                pt = self._snap_angle(self._drag0, pt, ev.modifiers())
                self._dragl = pt
                self._prev_draw(pt)
        except Exception:
            log.exception("mouseMoveEvent")

    def mouseReleaseEvent(self, ev):
        if getattr(self, "_picking", False):
            self._picking = False; self._rb.hide()
            self._finish_pick(QRectF(self._rb.geometry()))
            return
        if self._guide_release(QPointF(ev.position())):
            return
        self._release(ev)
        self._mv0 = None
        if self._snap_lines: self._snap_lines = []; self.update()

    def _release(self, ev):
        if self.tool == T_HAND:
            self._pan = None; self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if self.tool == T_INK and self._ink:
            a, self._ink = self._ink, None
            if len(a.points) < 2: self.anns.remove(a)
            self._redraw(); self._commit()
            return
        if ev.button() != Qt.MouseButton.LeftButton: return
        pt = QPointF(ev.position())
        try:
            if self.tool == T_LASSO and self._rb:
                rb_r = QRectF(self._rb.geometry())
                self._rb.hide()
                self._snap()
                for a in self.anns:
                    if not (a.locked or a.hidden) and a not in self._sel_multi and rb_r.contains(a.brect()):
                        a.selected = True
                        self._sel_multi.append(a)
                if self._sel_multi: self._sel = self._sel_multi[-1]
                self._redraw()
                return
            if self.tool == T_OCR_REGION and self._rb:
                rb_r = QRectF(self._rb.geometry())
                self._rb.hide()
                if rb_r.width() > 10 and rb_r.height() > 10:
                    self._ocr_rect = rb_r
                    self.sig_search_highlight.emit([rb_r])
                return
            if self.tool == T_TXTSEL:
                self._tsel_start = None
                return
            if self._rotating:
                self._rotating = False
                self._commit()
                return
            if self._handle >= 0:
                self._handle = -1
                self._commit()
                return
            if self.tool == T_SELECT:
                if self._moving:
                    self._moving = False
                    self._commit()
                    return
            if self._drawing:
                self._drawing = False
                pt = self._snap_angle(self._drag0, self._magnet_pt(pt, ev.modifiers()), ev.modifiers())
                dx = abs(pt.x() - self._drag0.x())
                dy = abs(pt.y() - self._drag0.y())
                if dx > 4 or dy > 4:
                    a = self._make_ann(self._drag0, pt)
                    if self.tool == T_TEXTBOX:
                        dlg = TextDialog(self, box=True)
                        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_text.strip():
                            a.text = dlg.result_text
                            a.font_name = dlg.result_font
                            a.font_size = dlg.result_size
                            a.font_bold = dlg.result_bold
                            a.font_italic = dlg.result_italic
                            a.font_underline = dlg.result_under
                            a.text_color = dlg.result_color
                            a.box_bg = dlg.result_bg
                            a.box_border = dlg.result_bd
                            a.box_bw = dlg.result_bw
                            self.anns.append(a)
                            self._setsel(a)
                            self._commit()
                    else:
                        self.anns.append(a)
                        self._setsel(a)
                        self._commit()
                self._redraw()
        except Exception:
            log.exception("mouseReleaseEvent")

    def mouseDoubleClickEvent(self, ev):
        pt = QPointF(ev.position())
        if self.tool == T_MEASURE and self._mpoly_finish(): return
        try:
            if self.tool == T_SELECT:
                for a in reversed(self.anns):
                    if a.kind in ("text", "textbox") and a.hit(pt):
                        self._open_inline(a)
                        return
                    if a.kind == "comment" and a.hit(pt):
                        self._edit_comment(a)
                        return
        except Exception:
            log.exception("dblClick")

    def _finish_pick(self, rect):
        """Recuadro elegido (px) → puntos de la página visible. Un clic sin arrastrar usa el tamaño estándar."""
        cb, (w, h) = PageCanvas.pick_box
        k = self._gk()
        if rect.width() < 12 or rect.height() < 12:          # clic: donde se veía el recuadro
            rect = self._pick_rect(rect.center())
        else:
            rect = rect.intersected(QRectF(self.rect())) if QRectF(self.rect()).contains(rect.center()) else rect
        self._pick_ghost = None; self.update()
        box = (rect.left() / k, rect.top() / k, rect.right() / k, rect.bottom() / k)
        PageCanvas.pick_box = None
        cb(self.page_num, box)

    def keyPressEvent(self, ev):
        k = ev.key()
        mod = ev.modifiers()
        ctrl = mod & Qt.KeyboardModifier.ControlModifier
        shift = mod & Qt.KeyboardModifier.ShiftModifier
        if self.tool == T_MEASURE:                        # Medir: Intro termina, Retroceso quita un vértice, Esc borra
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._mpoly_finish(): return
            if k == Qt.Key.Key_Backspace and self._mpoly_back(): return
            if k == Qt.Key.Key_Escape and (self._mpoly or self._measure):
                self._mpoly_reset(); self._measure = None; self.update(); return
        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._delete_sel()
        elif k == Qt.Key.Key_Escape:
            self._close_inline()
            self._desel()
            self._redraw()
        elif ctrl and k == Qt.Key.Key_C:
            if self._tsel_text: self._copy_text()
            elif self._sel: self._copy(self._sel)
        elif ctrl and k == Qt.Key.Key_X and self._sel:
            self._cut(self._sel)
        elif ctrl and k == Qt.Key.Key_V:
            pos = self.mapFromGlobal(QCursor.pos())
            self._paste(QPointF(pos) if self.rect().contains(pos) else None)
        elif ctrl and k == Qt.Key.Key_A and self.tool == T_TXTSEL and self._words:
            self._update_tsel(QPointF(*self._p2s(*self._words[0][:2])), QPointF(*self._p2s(*self._words[-1][2:4])))
        elif ctrl and k == Qt.Key.Key_A:
            self._sel_multi = [a for a in self.anns if not (a.locked or a.hidden)]
            for a in self._sel_multi: a.selected = True
            self._sel = self._sel_multi[-1] if self._sel_multi else None
            self._redraw()
        elif ctrl and k == Qt.Key.Key_D:
            self._duplicate()
        else:
            step = 10 if shift else 1
            targets = self._sel_multi if self._sel_multi else ([self._sel] if self._sel else [])
            if targets and k in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right):
                self._snap()
                _moves = {Qt.Key.Key_Up: (0,-step), Qt.Key.Key_Down: (0,step),
                          Qt.Key.Key_Left: (-step,0), Qt.Key.Key_Right: (step,0)}
                dx, dy = _moves[k]
                for a in targets: a.move(dx, dy)
                self._redraw()
                self._commit()
            else:
                super().keyPressEvent(ev)

    def _scroll_area(self):
        w = self.parentWidget()
        while w is not None and not isinstance(w, QScrollArea): w = w.parentWidget()
        return w

    @staticmethod
    def _step():
        if PageCanvas.rotation_step is None:
            PageCanvas.rotation_step = AppSettings().get_rotation_step()
        return max(1, PageCanvas.rotation_step)

    def _snap_angle(self, p0, pt, mods):
        """Al dibujar líneas y flechas con Ctrl: la dirección va de N en N grados (como un graficador)."""
        if self.tool not in (T_LINE, T_ARROW, T_DARROW) or not mods & Qt.KeyboardModifier.ControlModifier:
            return pt
        dx, dy = pt.x() - p0.x(), pt.y() - p0.y()
        step = math.radians(self._step())
        ang = round(math.atan2(dy, dx) / step) * step
        ln = math.hypot(dx, dy)
        QToolTip.showText(QCursor.pos(), f"{math.degrees(-ang) % 360:.0f}°", self)
        return QPointF(p0.x() + ln * math.cos(ang), p0.y() + ln * math.sin(ang))

    def re_render(self, zoom):
        self._measure = None
        try:
            ow, oh = self._bw, self._bh
            self.zoom = zoom
            self._calc_size()
            sx = self._bw/ow if ow else 1
            sy = self._bh/oh if oh else 1
            fn = lambda x, y: (x * sx, y * sy)
            groups = [self.anns, *self._history, *self._redo_stack]
            if self._pending: groups.append(self._pending)
            for g in groups:           # el historial también está en píxeles de pantalla
                for a in g: self._map(a, fn, sx)
            self._tsel_rects = []
            self._tsel_text = ""
            if self._base is not None:
                self._render()
                self._load_text()
                self._redraw()
        except Exception:
            log.exception(f"re_render p{self.page_num}")

    # ── conversión pantalla <-> puntos PDF (sin rotación de página) ─────────
    def _to_page(self, m=None):
        sx = self._bw / self._prect.width
        sy = self._bh / self._prect.height
        m = m or self.doc[self.page_num].derotation_matrix
        return lambda x, y: tuple(pymupdf.Point(x / sx, y / sy) * m)

    def _from_page(self):
        sx = self._bw / self._prect.width
        sy = self._bh / self._prect.height
        m = self.doc[self.page_num].rotation_matrix
        def f(x, y):
            q = pymupdf.Point(x, y) * m
            return q.x * sx, q.y * sy
        return f

    @staticmethod
    def _map(a, fn, k):
        a.x1, a.y1 = fn(a.x1, a.y1)
        a.x2, a.y2 = fn(a.x2, a.y2)
        a.points = [list(fn(x, y)) for x, y in a.points]
        a.corner_r *= k
        a.arrow_size *= k

    def anns_to_page(self) -> list:
        """Objetos de la página como dicts en puntos PDF (para guardar)."""
        fn, k = self._to_page(), self._prect.width / self._bw
        out = []
        for a in self.anns:
            c = a.clone()
            self._map(c, fn, k)
            out.append(c.to_dict())
        return out

    def anns_from_page(self, dicts: list):
        """Carga objetos guardados (dicts en puntos PDF)."""
        fn, k = self._from_page(), self._bw / self._prect.width
        self.anns = []
        for d in dicts:
            try:
                a = Ann.from_dict(d)
                self._map(a, fn, k)
                self.anns.append(a)
            except Exception:
                log.exception(f"anns_from_page p{self.page_num}")
        self._redraw()

    def reload_page(self, old_derotation=None, shift=(0.0, 0.0)):
        """Vuelve a dibujar la página tras cambiar el documento o su rotación,
        conservando objetos e historial en la posición correcta.
        `old_derotation`: derotation_matrix de la página antes del cambio.
        `shift`: desplazamiento del origen de la página (pt) al cambiar su caja de recorte."""
        to_page = self._to_page(old_derotation)
        self._calc_size()
        from_page = self._from_page()
        dx, dy = shift

        def fn(x, y):
            px, py = to_page(x, y)
            return from_page(px + dx, py + dy)
        groups = [self.anns, *self._history, *self._redo_stack]
        if self._pending: groups.append(self._pending)
        for g in groups:
            for a in g: self._map(a, fn, 1.0)
        self._tsel_rects = []
        self._tsel_text = ""
        if self._base is not None:
            self._render()
            self._load_text()
            self._redraw()
