# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Imágenes que ya trae el PDF: clic derecho sobre una → convertir en objeto (mover, tamaño, girar, recortar…),
reemplazar, guardar o eliminar. Parte de PageCanvas (ui/canvas.py)."""
import base64
import pymupdf
from PyQt6.QtCore import QBuffer, QIODevice
from PyQt6.QtGui import QImage, QTransform
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from core import page_images
from core.i18n import T, Tf
from models.annotation import Ann
from ui.icons import get_icon


class ImagesMixin:
    def _viewer_of(self):
        w = self.parentWidget()
        while w is not None and not hasattr(w, "apply_doc_change"): w = w.parentWidget()
        return w

    def _doc_image_at(self, pt):
        if not self.doc or not self._prect: return None
        x, y = self._to_page()(pt.x(), pt.y())
        return page_images.image_at(self.doc[self.page_num], pymupdf.Point(x, y))

    def _image_menu(self, menu, pt) -> dict:
        """Opciones para la imagen del PDF bajo el ratón (si la hay)."""
        img = self._doc_image_at(pt)
        if not img: return {}
        menu.addSeparator()
        h = menu.addAction(T("  Imagen del documento")); f = h.font(); f.setBold(True); h.setFont(f); h.setEnabled(False)
        acts = {
            menu.addAction(get_icon("image"), T("Convertir en objeto (mover, tamaño, recortar…)")): lambda: self._img_to_object(img),
            menu.addAction(get_icon("swap"), T("Reemplazar imagen…")): lambda: self._img_replace(img),
            menu.addAction(get_icon("save"), T("Guardar imagen como…")): lambda: self._img_save(img),
            menu.addAction(get_icon("delete"), T("Eliminar imagen")): lambda: self._img_delete(img),
        }
        return acts

    def _can_edit_doc(self) -> bool:
        from ui.doc_tools import _can_modify
        return _can_modify(self.window())

    def _img_to_object(self, img):
        v, xref = self._viewer_of(), img["xref"]
        if not (v and self._can_edit_doc()): return
        n = page_images.uses(self.doc, xref)
        title = T("Convertir imagen en objeto")
        if n > 1:
            QMessageBox.information(self.window(), title, Tf(
                "Esta imagen se repite en {0} lugares del documento (por ejemplo, un logotipo en cada página).\n"
                "No se puede convertir solo esta; sí puedes reemplazarla o eliminarla en todos a la vez.", n)); return
        if img["rotated"]:
            QMessageBox.information(self.window(), title, T(
                "Esta imagen está girada o volteada dentro del PDF y no se puede convertir.\n"
                "Sí puedes reemplazarla, guardarla o eliminarla.")); return
        qimg = QImage.fromData(page_images.png(self.doc, xref))
        rot = self.doc[self.page_num].rotation
        if rot: qimg = qimg.transformed(QTransform().rotate(rot))     # página girada: la imagen se ve girada
        buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.WriteOnly); qimg.save(buf, "PNG")
        fn, b = self._from_page(), img["bbox"]
        (ax, ay), (bx, by) = fn(b.x0, b.y0), fn(b.x1, b.y1)
        a = Ann("image", x1=min(ax, bx), y1=min(ay, by), x2=max(ax, bx), y2=max(ay, by),
                image_data=base64.b64encode(bytes(buf.data())).decode("ascii"))
        page_no = self.page_num
        v.apply_doc_change(lambda d: page_images.delete(d[page_no], xref))
        self._snap(); self.anns.append(a); self._setsel(a); self._redraw(); self._commit()
        v.merge_undo(2)                                   # quitar la imagen + crear el objeto: un solo Ctrl+Z
        self._status(T("La imagen ahora es un objeto: muévela, cambia su tamaño, gírala o recórtala. Ctrl+Z deshace."))

    def _img_replace(self, img):
        v, xref = self._viewer_of(), img["xref"]
        if not (v and self._can_edit_doc()): return
        path, _ = QFileDialog.getOpenFileName(self.window(), T("Reemplazar imagen"), "",
                                              T("Imágenes (*.png *.jpg *.jpeg *.bmp *.webp *.tiff)"))
        if not path: return
        n = page_images.uses(self.doc, xref)
        if n > 1 and QMessageBox.question(self.window(), T("Reemplazar imagen"), Tf(
                "Esta imagen se repite en {0} lugares del documento. Se reemplazará en todos.\n\n¿Continuar?", n)) \
                != QMessageBox.StandardButton.Yes:
            return
        page_no = self.page_num
        v.apply_doc_change(lambda d: page_images.replace(d[page_no], xref, path))
        self._status(T("Imagen reemplazada (ocupa el mismo espacio). Ctrl+Z deshace."))

    def _img_save(self, img):
        path, _ = QFileDialog.getSaveFileName(self.window(), T("Guardar imagen"), T("imagen") + ".png",
                                              T("Imagen PNG (*.png);;Imagen JPEG (*.jpg)"))
        if not path: return
        try:
            page_images.save(self.doc, img["xref"], path)
            self._status(Tf("Imagen guardada: {0}", path))
        except Exception as e:
            QMessageBox.warning(self.window(), T("Guardar imagen"), Tf("No se pudo guardar la imagen:\n{0}", e))

    def _img_delete(self, img):
        v, xref = self._viewer_of(), img["xref"]
        if not (v and self._can_edit_doc()): return
        n = page_images.uses(self.doc, xref)
        msg = (Tf("Esta imagen se repite en {0} lugares del documento y se eliminará de todos.", n) if n > 1
               else T("Se eliminará esta imagen del documento."))
        if QMessageBox.question(self.window(), T("Eliminar imagen"), msg + "\n\n" + T("Se puede deshacer con Ctrl+Z. ¿Eliminarla?")) \
                != QMessageBox.StandardButton.Yes:
            return
        page_no = self.page_num
        v.apply_doc_change(lambda d: page_images.delete(d[page_no], xref))
        self._status(T("Imagen eliminada. Ctrl+Z deshace."))
