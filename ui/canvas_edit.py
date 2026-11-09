# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Edición de objetos: menú contextual, portapapeles, orden, duplicar, borrar, colocar firmas. Parte de PageCanvas (ui/canvas.py)."""
from core.i18n import T, Tf
import base64
import json
from PyQt6.QtWidgets import (QDialog, QApplication, QMenu)
from PyQt6.QtCore import (QPointF, QMimeData, QByteArray, QBuffer, QIODevice)
from PyQt6.QtGui import QImage
from models.annotation import Ann
from dialogs.props_dialog import PropsDialog

from ui.styles import MENU_SS
from ui.icons import get_icon

ANN_MIME = "application/x-pdfgm-ann"   # objetos de PDFRapid en el portapapeles


class EditMixin:
    def _ctx_menu(self, pt, gpt):
        hit = None
        for a in reversed(self.anns):
            if a.hit(pt): hit = a; break
        if hit and hit not in self._sel_multi and self._sel is not hit:
            self._pick(hit)
            self._redraw()
        menu = QMenu(self)
        menu.setStyleSheet(MENU_SS)
        if self._sel_multi and len(self._sel_multi) > 1:
            n = len(self._sel_multi)
            hdr = menu.addAction(Tf("  {0} objetos seleccionados", n))
            hdr.setEnabled(False)
            menu.addSeparator()
            ap = menu.addAction(get_icon("format"), T("Formato del grupo…"))
            ad = menu.addAction(get_icon("duplicate"), T("Duplicar grupo"))
            menu.addSeparator()
            arr = self._arrange_menu(menu, list(self._sel_multi))
            menu.addSeparator()
            ax = menu.addAction(get_icon("delete"), T("Eliminar grupo"))
            menu.addSeparator()
            menu.addAction(get_icon("close"), T("Cancelar")).triggered.connect(lambda: (self._desel(), self._redraw()))
            chosen = menu.exec(gpt)
            if chosen == ap:
                dlg = PropsDialog(self._sel_multi[0], self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self._snap()
                    for a in self._sel_multi: dlg.apply(a)
                    self._redraw()
                    self._commit()
            elif chosen == ad: self._dup_group()
            elif chosen == ax: self._delete_sel()
            elif chosen in arr: arr[chosen]()
            return
        if hit:
            KIND_NAMES = {"line": "Línea", "rect": "Rectángulo", "rrect": "Rect. redondeado",
                          "circle": "Círculo", "triangle": "Triángulo", "text": "Texto",
                          "textbox": "Caja de texto", "highlight": "Resaltado", "comment": "Comentario",
                          "arrow": "Flecha →", "darrow": "Flecha ↔", "arrow_shape": "Figura flecha", "image": "Imagen",
                          "ink": "Dibujo a mano", "underline": "Subrayado", "strikeout": "Tachado"}
            hdr = menu.addAction(f"  {T(KIND_NAMES.get(hit.kind, hit.kind))}")
            hdr_f = hdr.font()
            hdr_f.setBold(True)
            hdr.setFont(hdr_f)
            hdr.setEnabled(False)
            menu.addSeparator()
            ac = menu.addAction(get_icon("cut"), T("Cortar"))
            acp = menu.addAction(get_icon("copy"), T("Copiar"))
            menu.addSeparator()
            om = menu.addMenu(get_icon("order"), T("Orden"))
            af = om.addAction(T("Traer al frente"))
            ab = om.addAction(T("Enviar al fondo"))
            afw = om.addAction(T("Adelantar"))
            abw = om.addAction(T("Atrasar"))
            menu.addSeparator()
            ae = menu.addAction(get_icon("text"), T("Editar texto…")) if hit.kind in ("text", "textbox", "comment") else None
            acr = menu.addAction(get_icon("crop"), T("Recortar imagen…")) if hit.kind == "image" and hit.image_data else None
            menu.addSeparator()
            adup = menu.addAction(get_icon("duplicate"), T("Duplicar"))
            menu.addSeparator()
            apr = menu.addAction(get_icon("format"), T("Formato del objeto…"))
            menu.addSeparator()
            arr = self._arrange_menu(menu, [hit])
            menu.addSeparator()
            adel = menu.addAction(get_icon("delete"), T("Eliminar"))
            chosen = menu.exec(gpt)
            if chosen == ac: self._cut(hit)
            elif chosen == acp: self._copy(hit)
            elif chosen == af: self._order(hit, "front")
            elif chosen == ab: self._order(hit, "back")
            elif chosen == afw: self._order(hit, "fwd")
            elif chosen == abw: self._order(hit, "bwd")
            elif ae and chosen == ae: self._text_dlg(QPointF(hit.x1, hit.y1), hit)
            elif acr and chosen == acr: self._crop_image(hit)
            elif chosen == adup: self._duplicate()
            elif chosen == apr: self._props_dlg(hit)
            elif chosen == adel: self._delete_sel()
            elif chosen in arr: arr[chosen]()
        else:
            apaste = menu.addAction(get_icon("paste"), T("Pegar"))
            md = QApplication.clipboard().mimeData()
            apaste.setEnabled(bool(md) and (md.hasFormat(ANN_MIME) or md.hasImage() or md.hasText()))
            menu.addSeparator()
            asa = menu.addAction(get_icon("select_all"), T("Seleccionar todo"))
            menu.addSeparator()
            arr = self._restore_menu(menu)
            arr.update(self._image_menu(menu, pt))      # imagen del PDF bajo el ratón
            chosen = menu.exec(gpt)
            if chosen == apaste:
                self._paste(pt)
            elif chosen == asa:
                self._sel_multi = [a for a in self.anns if not (a.locked or a.hidden)]
                for a in self._sel_multi: a.selected = True
                self._sel = self._sel_multi[-1] if self._sel_multi else None
                self._redraw()
            elif chosen in arr: arr[chosen]()

    def _crop_image(self, a):
        """Recorta la imagen (se puede deshacer con Ctrl+Z); el resto queda en su sitio y a la misma escala."""
        from dialogs.crop_dialog import CropDialog
        img = QImage.fromData(base64.b64decode(a.image_data))
        if img.isNull(): return
        dlg = CropDialog(img, self.window())
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        r = dlg.crop_rect()
        if r == img.rect() or r.isEmpty(): return
        self._snap()
        apply_crop(a, img, r)
        self._redraw(); self._commit()

    def _cut(self, a):
        self._copy(a)
        self._snap()
        self.anns.remove(a)
        self._desel()
        self._redraw()
        self._commit()

    def _copy(self, a):
        """Copia el objeto al portapapeles del sistema (formato propio + texto si lo tiene)."""
        c = a.clone(); c.selected = False
        md = QMimeData()
        md.setData(ANN_MIME, QByteArray(json.dumps(c.to_dict()).encode("utf-8")))
        if getattr(a, "text", ""): md.setText(a.text)
        QApplication.clipboard().setMimeData(md)

    def _paste(self, at=None):
        """Pega un objeto de Pdfgm, una imagen o texto del portapapeles (en `at` o desplazado)."""
        md = QApplication.clipboard().mimeData()
        if not md: return
        if md.hasFormat(ANN_MIME):
            a = Ann.from_dict(json.loads(bytes(md.data(ANN_MIME)).decode("utf-8")))
        elif md.hasImage():
            buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly)
            QImage(md.imageData()).save(buf, "PNG")
            img = QImage(md.imageData())
            w = min(img.width(), self._bw * 0.6); h = img.height() * w / max(img.width(), 1)
            a = Ann("image", x1=0, y1=0, x2=w, y2=h,
                    image_data=base64.b64encode(bytes(buf.data())).decode("utf-8"))
        elif md.hasText() and md.text().strip():
            txt = md.text().strip()
            a = Ann("text", x1=0, y1=0, x2=300, y2=30, text=txt, font_name=self.p_fname,
                    font_size=self.p_fsize, text_color=self.p_fcolor.name())
        else:
            return
        dx, dy = (at.x() - a.x1, at.y() - a.y1) if at else (15, 15)
        a.move(dx, dy)
        self._snap()
        self.anns.append(a)
        self._setsel(a)
        self._redraw()
        self._commit()

    def _place_signature(self, pt, width=170):
        """Coloca la firma o el sello elegido centrado en el clic (mismo tamaño en el papel a cualquier zoom)."""
        data = type(self).pending_signature
        img = QImage.fromData(base64.b64decode(data))
        w = width * self.zoom
        h = w * img.height() / max(img.width(), 1)
        self._snap()
        a = Ann("image", x1=pt.x() - w / 2, y1=pt.y() - h / 2, x2=pt.x() + w / 2, y2=pt.y() + h / 2, image_data=data)
        self.anns.append(a); self._setsel(a); self._redraw(); self._commit()

    def _order(self, a, m):
        self._snap()
        idx = self.anns.index(a)
        n = len(self.anns)
        self.anns.remove(a)
        if m == "front": self.anns.append(a)
        elif m == "back": self.anns.insert(0, a)
        elif m == "fwd": self.anns.insert(min(idx+1, n-1), a)
        elif m == "bwd": self.anns.insert(max(idx-1, 0), a)
        self._redraw()
        self._commit()

    def _props_dlg(self, a):
        dlg = PropsDialog(a, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._snap()
            dlg.apply(a)
            self._redraw()
            self._commit()

    def _duplicate(self):
        targets = self._sel_multi if self._sel_multi else ([self._sel] if self._sel else [])
        if not targets: return
        self._snap()
        for a in targets:
            d = a.clone()
            d.move(15, 15)
            self.anns.append(d)
        self._redraw()
        self._commit()

    def _dup_group(self):
        self._snap()
        new_anns = []
        for a in self._sel_multi:
            d = a.clone()
            d.move(15, 15)
            new_anns.append(d)
            self.anns.append(d)
        for a in self._sel_multi: a.selected = False
        self._sel_multi = new_anns
        for a in new_anns: a.selected = True
        if new_anns: self._sel = new_anns[-1]
        self._redraw()
        self._commit()

    def _delete_sel(self):
        targets = self._sel_multi if self._sel_multi else ([self._sel] if self._sel else [])
        if not targets: return
        self._snap()
        for a in targets:
            if a in self.anns: self.anns.remove(a)
        self._sel_multi.clear()
        self._desel()
        self._redraw()
        self._commit()


def apply_crop(a, img: QImage, r):
    """Deja en `a` solo la parte `r` (píxeles) de `img`, conservando posición, escala y giro en la página."""
    b = a.brect()
    W, H = img.width(), img.height()
    nx, ny = b.x() + r.x() / W * b.width(), b.y() + r.y() / H * b.height()
    nw, nh = r.width() / W * b.width(), r.height() / H * b.height()
    c = a._rot(QPointF(nx + nw / 2, ny + nh / 2), a.rotation)    # centro visible (con el giro aplicado)
    a.x1, a.y1, a.x2, a.y2 = c.x() - nw / 2, c.y() - nh / 2, c.x() + nw / 2, c.y() + nh / 2
    out = img.copy(r)
    buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly)
    out.save(buf, "PNG") if out.hasAlphaChannel() else out.save(buf, "JPG", 92)
    a.image_data = base64.b64encode(bytes(buf.data())).decode("ascii")
