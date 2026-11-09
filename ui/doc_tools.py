# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Diálogos de herramientas de documento (menú Archivo) y panel de formulario."""
from core.i18n import T, Tf
import os
import pymupdf
from PyQt6.QtCore import Qt, QTimer, QThread, QEventLoop
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QCheckBox,
                             QRadioButton, QComboBox, QSpinBox, QDialogButtonBox, QPushButton, QFileDialog,
                             QMessageBox, QInputDialog, QWidget, QScrollArea, QGroupBox, QProgressDialog)
from core import pdf_tools
from core.pages import parse_ranges
from core.pdf_io import save_pdf
from core.logger import log
from core.constants import APP_NAME, APP_VERSION


def _buttons(dlg, ok_text):
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText(T("Cancelar"))
    bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
    return bb


class _Job(QThread):
    def __init__(self, fn):
        super().__init__(); self.fn, self.result, self.error = fn, None, None

    def run(self):
        try:
            self.result = self.fn()
        except Exception as e:
            log.exception("tarea en segundo plano"); self.error = e


def run_with_progress(win, title, text, fn):
    """Ejecuta `fn` en segundo plano con una ventana de espera (la app no se congela).
    Devuelve (resultado, error)."""
    dlg = QProgressDialog(text, None, 0, 0, win)
    dlg.setWindowTitle(title); dlg.setMinimumDuration(300); dlg.setWindowModality(Qt.WindowModality.WindowModal)
    job = _Job(fn); loop = QEventLoop()
    job.finished.connect(loop.quit); job.start(); loop.exec(); dlg.close()
    return job.result, job.error


def _size(n): return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{n / 1024:.0f} KB"


# ── proteger ──────────────────────────────────────────────────────────────────
class ProtectDialog(QDialog):
    def __init__(self, parent, crypt):
        super().__init__(parent)
        self.setWindowTitle(T("Proteger con contraseña")); self.setMinimumWidth(400)
        self.remove = False
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.ed_user, self.ed_user2 = QLineEdit(), QLineEdit()
        self.ed_owner = QLineEdit()
        for e in (self.ed_user, self.ed_user2, self.ed_owner): e.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_user.setPlaceholderText(T("vacía = se abre sin contraseña"))
        self.ed_owner.setPlaceholderText(T("necesaria para restringir permisos"))
        form.addRow(T("Contraseña para abrir:"), self.ed_user)
        form.addRow(T("Repetir:"), self.ed_user2)
        form.addRow(T("Contraseña de propietario:"), self.ed_owner)
        lay.addLayout(form)
        g = QGroupBox(T("Permitir a quien lo abra:")); gl = QVBoxLayout(g)
        self.checks = {}
        allowed = crypt["permissions"] if crypt else 0xFFFF
        for key, bits, text in pdf_tools.PERMS:
            cb = QCheckBox(T(text)); cb.setChecked(bool(allowed & bits)); gl.addWidget(cb); self.checks[key] = cb
        lay.addWidget(g)
        lay.addWidget(QLabel(T("Se aplica al guardar (cifrado AES-256).")))
        row = QHBoxLayout()
        if crypt:
            b = QPushButton(T("Quitar protección")); b.setObjectName("flat")
            b.clicked.connect(self._remove); row.addWidget(b)
        row.addStretch(); row.addWidget(_buttons(self, T("Aplicar"))); lay.addLayout(row)

    def _remove(self):
        self.remove = True; self.accept()

    def accept(self):
        if not self.remove:
            if self.ed_user.text() != self.ed_user2.text():
                QMessageBox.warning(self, T("Contraseña"), T("Las contraseñas para abrir no coinciden.")); return
            restricted = not all(cb.isChecked() for cb in self.checks.values())
            if restricted and not self.ed_owner.text():
                QMessageBox.warning(self, T("Contraseña"), T("Para restringir permisos indica una contraseña de propietario.")); return
            if not self.ed_user.text() and not restricted:
                QMessageBox.warning(self, T("Contraseña"), T("Indica una contraseña para abrir o restringe algún permiso.")); return
        super().accept()

    def crypt(self):
        allowed = {k for k, cb in self.checks.items() if cb.isChecked()}
        return pdf_tools.make_crypt(self.ed_user.text(), self.ed_owner.text(), allowed)


def protect(win):
    v = win._viewer
    if not (v and v.doc): return
    if v.crypt and v.crypt["owner_pw"] is None and v.crypt["permissions"] & 0xF3C != 0xF3C:
        pw, ok = QInputDialog.getText(win, T("Contraseña de propietario"),
                                      T("Para cambiar la protección escribe la contraseña de propietario:"),
                                      QLineEdit.EchoMode.Password)
        if not ok: return
        if not (v.path and pdf_tools.is_owner_password(v.path, pw)):
            QMessageBox.warning(win, T("Contraseña"), T("La contraseña de propietario no es correcta.")); return
        v.doc.authenticate(pw)                      # con la de propietario: todos los permisos
        v.crypt["owner_pw"] = pw
    dlg = ProtectDialog(win, v.crypt)
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    v.crypt = None if dlg.remove else dlg.crypt()
    v._crypt_ok = True
    v._mark_dirty(0)
    win._update_info()
    win._status(T("Protección quitada: se guardará sin contraseña.") if dlg.remove
                else T("Protección lista: se aplicará al guardar."))


# ── comprimir ─────────────────────────────────────────────────────────────────
def compress(win):
    v = win._viewer
    if not (v and v.doc): return
    dlg = QDialog(win); dlg.setWindowTitle(T("Comprimir PDF")); lay = QVBoxLayout(dlg)
    radios = {}
    for key, (text, _) in pdf_tools.LEVELS.items():
        r = QRadioButton(T(text)); radios[key] = r; lay.addWidget(r)
    radios["balanced"].setChecked(True)
    lay.addWidget(QLabel(T("Se guarda como un archivo nuevo; el original no cambia.\n"
                         "Los PDF escaneados o con fotos se reducen mucho; los de texto y capturas de pantalla, poco.")))
    lay.addWidget(_buttons(dlg, T("Comprimir…")))
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    level = next(k for k, r in radios.items() if r.isChecked())
    base = os.path.splitext(v.path or "documento.pdf")[0]
    path, _ = QFileDialog.getSaveFileName(win, T("Guardar PDF comprimido"), base + "_comprimido.pdf", T("PDF Files (*.pdf)"))
    if not path: return
    before = os.path.getsize(v.path) if v.path and os.path.exists(v.path) else len(v.doc.tobytes())
    out = v.export_copy()

    def job():
        pdf_tools.compress(out, level)
        save_pdf(out, path, v.crypt, **pdf_tools.SAVE_OPTS)
    _, err = run_with_progress(win, "Comprimir PDF", "Comprimiendo… en documentos grandes puede tardar unos minutos.", job)
    out.close()
    if err:
        QMessageBox.critical(win, T("Comprimir"), str(err)); return
    after = os.path.getsize(path)
    win._status(Tf("PDF comprimido: {0} → {1} ({2} % menos) · {3}", _size(before), _size(after), 100 - after * 100 // max(before, 1), path))


# ── exportar a Word ───────────────────────────────────────────────────────────
def export_word(win):
    """PDF → .docx con pdf2docx (texto, tablas e imágenes; la maquetación compleja puede variar)."""
    v = win._viewer
    if not (v and v.doc): return
    if not v.allows(pymupdf.PDF_PERM_COPY):
        QMessageBox.information(win, T("Documento protegido"), T("El autor de este documento no permite extraer su contenido.")); return
    try:
        from pdf2docx import Converter
    except ImportError:
        QMessageBox.information(win, T("Exportar a Word"), T("Falta un componente. Ejecuta:\npip install pdf2docx")); return
    dlg = QDialog(win); dlg.setWindowTitle(T("Exportar a Word")); form = QFormLayout(dlg)
    ed_pages = QLineEdit(); ed_pages.setPlaceholderText(Tf("todas ({0}) · o ej. 1-10", len(v.doc)))
    form.addRow(T("Páginas:"), ed_pages)
    note = QLabel(T("Se conservan texto, párrafos, tablas e imágenes. Diseños muy elaborados pueden necesitar "
                  "retoques en Word. Las marcas de PDFRapid no se exportan."))
    note.setWordWrap(True); form.addRow(note); form.addRow(_buttons(dlg, T("Exportar…")))
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    try:
        pages = parse_ranges(ed_pages.text(), len(v.doc)) if ed_pages.text().strip() else None
    except ValueError as e:
        QMessageBox.warning(win, T("Páginas"), str(e)); return
    muestra = pages or range(min(len(v.doc), 5))
    if not any(v.doc[i].get_text().strip() for i in list(muestra)[:5]):
        if QMessageBox.question(win, T("PDF escaneado"), T("Estas páginas parecen escaneadas (sin texto): en Word quedarían "
                                "como imágenes. Para obtener texto editable usa antes OCR → «Guardar PDF» y exporta ese archivo."
                                "\n\n¿Exportar de todos modos?")) != QMessageBox.StandardButton.Yes:
            return
    base = os.path.splitext(v.path or "documento.pdf")[0]
    path, _ = QFileDialog.getSaveFileName(win, T("Guardar como Word"), base + ".docx", T("Documento de Word (*.docx)"))
    if not path: return
    data = v.doc.tobytes()                       # ya descifrado en memoria

    def job():
        cv = Converter(stream=data)
        try:
            cv.convert(path, pages=pages)
        finally:
            cv.close()
    _, err = run_with_progress(win, "Exportar a Word", "Convirtiendo a Word… en documentos grandes puede tardar varios minutos.", job)
    if err:
        QMessageBox.critical(win, T("Exportar a Word"), Tf("No se pudo convertir:\n{0}", err)); return
    win._status(Tf("Exportado a Word: {0}", path))
    if QMessageBox.question(win, T("Exportar a Word"), T("Listo. ¿Abrir el documento en Word?")) == QMessageBox.StandardButton.Yes:
        os.startfile(path)


def export_other(win, fmt):
    """Archivo → Exportar → Excel (tablas), texto, HTML o Markdown."""
    from core import export
    v = win._viewer
    if not (v and v.doc): return
    if not v.allows(pymupdf.PDF_PERM_COPY):
        QMessageBox.information(win, T("Documento protegido"), T("El autor de este documento no permite extraer su contenido.")); return
    title = {"xlsx": T("Exportar a Excel"), "txt": T("Exportar a texto"), "html": T("Exportar a HTML"), "md": T("Exportar a Markdown")}[fmt]
    if not any(v.doc[i].get_text().strip() for i in range(min(len(v.doc), 5))):
        if QMessageBox.question(win, T("PDF escaneado"), T("Este PDF parece escaneado (sin texto). Para obtener texto usa "
                                "antes OCR → «Guardar PDF» y exporta ese archivo.\n\n¿Exportar de todos modos?")) != QMessageBox.StandardButton.Yes:
            return
    filters = {"xlsx": T("Libro de Excel (*.xlsx)"), "txt": T("Texto (*.txt)"), "html": T("Página web (*.html)"), "md": T("Markdown (*.md)")}
    base = os.path.splitext(v.path or "documento.pdf")[0]
    path, _ = QFileDialog.getSaveFileName(win, title, f"{base}.{fmt}", filters[fmt])
    if not path: return
    data = v.doc.tobytes()

    def job():
        d = pymupdf.open("pdf", data)
        try:
            if fmt == "xlsx": return export.to_xlsx(d, path)
            if fmt == "txt": return export.to_text(d, path)
            if fmt == "md": return export.to_markdown(d, path)
            return export.to_html(d, path, title=os.path.basename(base))
        finally:
            d.close()
    res, err = run_with_progress(win, title, T("Exportando…"), job)
    if err:
        QMessageBox.critical(win, title, Tf("No se pudo exportar:\n{0}", err)); return
    if fmt == "xlsx":
        n, how = res
        if not n:
            QMessageBox.information(win, title, T("No se encontraron tablas ni texto que exportar.")); return
        msg = Tf("{0} tabla(s), una por hoja.", n) if how == "tablas" else \
            T("No se detectaron tablas: se exportó el texto, una fila por línea y una hoja por página.")
    else:
        msg = T("Listo.")
    win._status(Tf("Exportado: {0}", path))
    if QMessageBox.question(win, title, msg + "\n\n" + T("¿Abrir el archivo?")) == QMessageBox.StandardButton.Yes:
        os.startfile(path)


# ── enlaces ───────────────────────────────────────────────────────────────────
class LinkDialog(QDialog):
    """Destino de un enlace: una página del documento o una dirección web."""
    def __init__(self, parent, n_pages, kind="page", target=0):
        super().__init__(parent)
        self.setWindowTitle(T("Enlace")); self.setMinimumWidth(380)
        lay = QVBoxLayout(self); form = QFormLayout()
        self.rb_page, self.rb_uri = QRadioButton(T("Ir a la página:")), QRadioButton(T("Abrir la dirección web:"))
        self.sp_page = QSpinBox(); self.sp_page.setRange(1, max(1, n_pages))
        self.ed_uri = QLineEdit(); self.ed_uri.setPlaceholderText("https://…  ·  mailto:…")
        if kind == "uri":
            self.rb_uri.setChecked(True); self.ed_uri.setText(str(target))
        else:
            self.rb_page.setChecked(True); self.sp_page.setValue(int(target) + 1)
        self.sp_page.valueChanged.connect(lambda: self.rb_page.setChecked(True))
        self.ed_uri.textEdited.connect(lambda: self.rb_uri.setChecked(True))
        form.addRow(self.rb_page, self.sp_page); form.addRow(self.rb_uri, self.ed_uri)
        lay.addLayout(form); lay.addWidget(_buttons(self, T("Aceptar")))

    def accept(self):
        from ui.viewer import safe_link
        if self.rb_uri.isChecked():
            u = self.ed_uri.text().strip()
            if u and "://" not in u and not u.lower().startswith("mailto:"):
                u = ("mailto:" if "@" in u else "https://") + u; self.ed_uri.setText(u)
            if not safe_link(u):
                QMessageBox.warning(self, T("Enlace"), T("Escribe una dirección web (https://…) o de correo (mailto:…).")); return
        super().accept()

    def value(self):
        return ("uri", self.ed_uri.text().strip()) if self.rb_uri.isChecked() else ("page", self.sp_page.value() - 1)


def add_link(win):
    """Documento → Enlaces → Añadir: dibujar la zona y elegir el destino."""
    if not _can_modify(win): return
    v = win._viewer

    def done(page, box):
        dlg = LinkDialog(win, len(v.doc), "page", min(page + 1, len(v.doc) - 1))
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        kind, target = dlg.value()
        v.apply_doc_change(lambda d: pdf_tools.add_link(d, page, box, kind, target))
        win._status(T("Enlace añadido. Se puede deshacer (Ctrl+Z)."))
    pick_box(win, (120, 18), T("Enlace"), done)


def manage_links(win):
    """Documento → Enlaces → Gestionar: lista de enlaces con ir, cambiar destino y eliminar."""
    from PyQt6.QtWidgets import QListWidget, QListWidgetItem
    v = win._viewer
    if not (v and v.doc): return
    dlg = QDialog(win); dlg.setWindowTitle(T("Enlaces del documento")); dlg.setMinimumSize(520, 360)
    lay = QVBoxLayout(dlg)
    lst = QListWidget(); lay.addWidget(lst, 1)
    row = QHBoxLayout()
    bt_go, bt_edit, bt_del = QPushButton(T("Ir")), QPushButton(T("Cambiar destino…")), QPushButton(T("Eliminar"))
    for b in (bt_go, bt_edit, bt_del): row.addWidget(b)
    row.addStretch(1)
    bt_close = QPushButton(T("Cerrar")); bt_close.clicked.connect(dlg.accept); row.addWidget(bt_close)
    lay.addLayout(row)
    editable = v.allows(pymupdf.PDF_PERM_MODIFY) and not v.readonly

    def fill():
        lst.clear()
        for l in pdf_tools.list_links(v.doc):
            dest = Tf("página {0}", l["target"] + 1) if l["kind"] == "page" else l["target"]
            it = QListWidgetItem(Tf("Pág. {0} → {1}", l["page"] + 1, dest)); it.setData(Qt.ItemDataRole.UserRole, l)
            lst.addItem(it)
        for b in (bt_go, bt_edit, bt_del): b.setEnabled(lst.count() > 0)
        bt_edit.setEnabled(editable and lst.count() > 0); bt_del.setEnabled(editable and lst.count() > 0)
        if lst.count(): lst.setCurrentRow(0)

    def cur():
        it = lst.currentItem(); return it.data(Qt.ItemDataRole.UserRole) if it else None

    def go():
        l = cur()
        if l: v.highlight_search(l["page"], [pymupdf.Rect(l["rect"])])

    def edit():
        l = cur()
        if not l: return
        d = LinkDialog(dlg, len(v.doc), l["kind"], l["target"])
        if d.exec() != QDialog.DialogCode.Accepted: return
        kind, target = d.value()
        v.apply_doc_change(lambda doc: pdf_tools.update_link(doc, l["page"], l["index"], kind, target)); fill()

    def delete():
        l = cur()
        if not l: return
        v.apply_doc_change(lambda doc: pdf_tools.delete_link(doc, l["page"], l["index"])); fill()
    bt_go.clicked.connect(go); bt_edit.clicked.connect(edit); bt_del.clicked.connect(delete)
    lst.itemDoubleClicked.connect(lambda _: go())
    fill()
    if not lst.count():
        lst.addItem(T("Este documento no tiene enlaces. Usa Documento → Enlaces → Añadir enlace."))
        lst.setEnabled(False)
    dlg.exec()


def export_pdfa(win):
    """Guarda una copia PDF/A-2b (archivo a largo plazo) con las marcas actuales, e informa de lo que cambió."""
    from core import pdfa
    from core.ann_store import export as ann_export
    v = win._viewer
    if not (v and v.doc): return
    signed = any(w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE and w.field_value
                 for p in v.doc for w in (p.widgets() or []))
    msg = T("PDF/A es el formato para conservar documentos a largo plazo que piden muchos trámites y archivos: "
            "incrusta las tipografías y el perfil de color, y quita lo que podría dejar de funcionar con los años "
            "(JavaScript, adjuntos, contraseña).\n\nSe guarda una copia; el documento abierto no cambia.")
    if signed:
        msg += "\n\n" + T("Este documento tiene firmas digitales: la copia ya no las tendrá válidas. "
                          "Para un PDF/A firmado, convierte primero y firma después la copia.")
    if QMessageBox.question(win, T("Guardar como PDF/A"), msg + "\n\n" + T("¿Continuar?")) != QMessageBox.StandardButton.Yes:
        return
    base = os.path.splitext(v.path or "documento.pdf")[0]
    path, _ = QFileDialog.getSaveFileName(win, T("Guardar como PDF/A"), base + "_PDFA.pdf", T("Archivos PDF (*.pdf)"))
    if not path: return
    if v.path and os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(v.path)):
        QMessageBox.warning(win, T("Guardar como PDF/A"), T("Elige otro nombre: el original no se sobrescribe.")); return
    pages = {i: cv.anns_to_page() for i, cv in enumerate(v.canvases) if cv.anns}
    copy = ann_export(v.doc, pages, v.guides)

    def job():
        try:
            return pdfa.convert(copy, path, producer=f"{APP_NAME} {APP_VERSION}")
        finally:
            copy.close()
    rep, err = run_with_progress(win, "Guardar como PDF/A", "Convirtiendo a PDF/A…", job)
    if err:
        QMessageBox.critical(win, T("Guardar como PDF/A"), Tf("No se pudo convertir:\n{0}", err)); return
    lines = [Tf("Guardado como PDF/A-2b:\n{0}", path)]
    if rep["fuentes"]: lines.append(Tf("Tipografías incrustadas: {0}", ", ".join(sorted(set(rep["fuentes"])))))
    if rep["rasterizadas"]:
        lines.append(Tf("Páginas convertidas en imagen (con el texto buscable encima), porque usaban tipografías que no "
                        "están en este equipo o colores de imprenta: {0}", ", ".join(map(str, rep["rasterizadas"]))))
    if rep["cmyk_imagenes"]: lines.append(Tf("Imágenes pasadas de CMYK a RGB: {0}", rep["cmyk_imagenes"]))
    if rep["quitado"]: lines.append(Tf("Quitado: {0}", ", ".join(T(q) for q in rep["quitado"])))
    win._status(Tf("Guardado como PDF/A: {0}", path))
    if QMessageBox.question(win, T("Guardar como PDF/A"), "\n\n".join(lines) + "\n\n" + T("¿Abrir la copia?")) \
            == QMessageBox.StandardButton.Yes:
        win._open_path(path)


# ── imágenes ↔ PDF ────────────────────────────────────────────────────────────
def images_to_pdf(win):
    paths, _ = QFileDialog.getOpenFileNames(win, T("Elegir imágenes"), win._settings.get_last_dir(),
                                            T("Imágenes (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"))
    if not paths: return
    out_path, _ = QFileDialog.getSaveFileName(win, T("Guardar PDF"), os.path.join(os.path.dirname(paths[0]), "imagenes.pdf"),
                                              T("PDF Files (*.pdf)"))
    if not out_path: return
    try:
        doc = pdf_tools.images_to_pdf(paths)
        save_pdf(doc, out_path); doc.close()
    except Exception as e:
        log.exception("imagenes a pdf"); QMessageBox.critical(win, T("Crear PDF"), str(e)); return
    win._open_path(out_path)


def from_office(win):
    """Word, Excel o PowerPoint → PDF (con Microsoft Office o LibreOffice instalados en el equipo)."""
    from core import convert
    exts = " ".join("*" + e for e in convert.EXTS)
    src, _ = QFileDialog.getOpenFileName(win, T("Crear PDF desde Word, Excel o PowerPoint"), win._settings.get_last_dir(),
                                         Tf("Documentos de Office ({0})", exts))
    if not src: return
    kind = convert.kind_of(src)
    if not convert.available().get(kind) and not src.lower().endswith(".docx"):   # .docx: conversión básica
        QMessageBox.information(win, T("Crear PDF"), T(
            "Para convertir documentos de Word, Excel o PowerPoint se necesita Microsoft Office o LibreOffice "
            "(gratuito, libreoffice.org) instalado en este equipo.\n\nInstala uno de los dos y vuelve a intentarlo."))
        return
    out, _ = QFileDialog.getSaveFileName(win, T("Guardar PDF"), os.path.splitext(src)[0] + ".pdf", T("PDF Files (*.pdf)"))
    if not out: return
    how, err = run_with_progress(win, T("Crear PDF"), Tf("Convirtiendo {0}…", os.path.basename(src)),
                                 lambda: convert.office_to_pdf(src, out))
    if err:
        log.error(f"office_to_pdf: {err}")
        QMessageBox.warning(win, T("Crear PDF"), Tf("No se pudo convertir:\n{0}", err)); return
    win._open_path(out)
    if how == convert.BASIC:
        win._status(Tf("PDF creado con la conversión básica (sin Office ni LibreOffice, o no pudieron abrirlo): "
                       "el diseño puede diferir del original. {0}", out))
    else:
        win._status(Tf("PDF creado con {0}: {1}", how, out))


def scan(win):
    """Escanear una o varias páginas (diálogo de escaneo de Windows) y crear un PDF."""
    import tempfile
    from core import convert
    tmp = tempfile.mkdtemp(prefix="pdfrapid_scan_"); pages = []
    while True:
        dst = os.path.join(tmp, f"p{len(pages) + 1:03d}.png")
        ok, err = run_with_progress(win, T("Escanear"), T("Esperando al escáner…"), lambda: convert.scan_page(dst))
        if err:
            msg = T(convert.NO_SCANNER) if isinstance(err, convert.ScanError) and str(err) == convert.NO_SCANNER else str(err)
            QMessageBox.warning(win, T("Escanear"), msg); break
        if not ok: break
        pages += [dst] if ok is True else ok              # TWAIN con alimentador: varias páginas de una vez
        if QMessageBox.question(win, T("Escanear"), Tf("Página {0} escaneada. ¿Escanear otra página?", len(pages))) != QMessageBox.StandardButton.Yes: break
    if not pages: return
    out, _ = QFileDialog.getSaveFileName(win, T("Guardar PDF"), os.path.join(win._settings.get_last_dir(), "escaneo.pdf"),
                                         T("PDF Files (*.pdf)"))
    if not out: return
    try:
        doc = pdf_tools.images_to_pdf(pages); save_pdf(doc, out); doc.close()
    except Exception as e:
        log.exception("escanear"); QMessageBox.critical(win, T("Escanear"), str(e)); return
    win._open_path(out)
    win._dock_ocr.setVisible(True)                     # un escaneo es una imagen: ofrecer el OCR
    win._status(Tf("{0} página(s) escaneada(s). Usa «OCR todo el documento» para poder buscar y copiar el texto.", len(pages)))


def export_images(win):
    v = win._viewer
    if not (v and v.doc): return
    if not v.allows(pymupdf.PDF_PERM_COPY):
        QMessageBox.information(win, T("Documento protegido"), T("El autor de este documento no permite extraer su contenido.")); return
    dlg = QDialog(win); dlg.setWindowTitle(T("Exportar páginas como imágenes")); form = QFormLayout(dlg)
    cb_fmt = QComboBox(); cb_fmt.addItems([T("PNG (sin pérdida)"), T("JPG (más liviano)")])
    sp_dpi = QSpinBox(); sp_dpi.setRange(72, 600); sp_dpi.setValue(150); sp_dpi.setSuffix(" ppp")
    ed_pages = QLineEdit(); ed_pages.setPlaceholderText(Tf("todas · o ej. 1-3, 8 · actual: {0}", v.current + 1))
    form.addRow(T("Formato:"), cb_fmt); form.addRow(T("Resolución:"), sp_dpi); form.addRow(T("Páginas:"), ed_pages)
    form.addRow(_buttons(dlg, T("Exportar…")))
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    try:
        pages = parse_ranges(ed_pages.text(), len(v.doc)) if ed_pages.text().strip() else list(range(len(v.doc)))
    except ValueError as e:
        QMessageBox.warning(win, T("Páginas"), str(e)); return
    folder = QFileDialog.getExistingDirectory(win, T("Carpeta de destino"), os.path.dirname(v.path or win._settings.get_last_dir()))
    if not folder: return
    doc = v.export_copy()
    try:
        files = pdf_tools.export_images(doc, pages, folder, os.path.splitext(os.path.basename(v.path or "documento"))[0],
                                        "jpg" if cb_fmt.currentIndex() else "png", sp_dpi.value())
    finally:
        doc.close()
    win._status(Tf("{0} imagen(es) guardadas en {1}", len(files), folder))


# ── formulario ────────────────────────────────────────────────────────────────
FIELD_KIND_NAMES = {"text": "Texto", "multiline": "Texto de varias líneas", "check": "Casilla",
                    "radio": "Botón de opción", "combo": "Lista desplegable", "list": "Cuadro de lista"}


class FieldDialog(QDialog):
    """Propiedades de un campo de formulario: nombre, ayuda, obligatorio, solo lectura y, según el tipo,
    valor inicial, opciones y tamaño de letra."""
    def __init__(self, parent, kind, props, groups=()):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle(Tf("Campo: {0}", T(FIELD_KIND_NAMES[kind]))); self.setMinimumWidth(380)
        lay = QVBoxLayout(self); form = QFormLayout()
        if kind == "radio":                          # mismo nombre = mismo grupo (solo uno elegido)
            self.ed_name = QComboBox(); self.ed_name.setEditable(True); self.ed_name.addItems(list(groups))
            self.ed_name.setCurrentText(props.get("name", ""))
            form.addRow(T("Grupo:"), self.ed_name)
            hint = QLabel(T("Los botones del mismo grupo se excluyen entre sí: solo se puede elegir uno."))
            hint.setWordWrap(True); form.addRow(hint)
        else:
            self.ed_name = QLineEdit(props.get("name", "")); form.addRow(T("Nombre:"), self.ed_name)
        self.ed_tip = QLineEdit(props.get("tooltip", "")); self.ed_tip.setPlaceholderText(T("texto de ayuda al pasar el ratón"))
        form.addRow(T("Ayuda:"), self.ed_tip)
        self.ed_value = self.ed_choices = self.sp_size = None
        if kind in ("text", "multiline"):
            self.ed_value = QLineEdit(props.get("value", "")); form.addRow(T("Valor inicial:"), self.ed_value)
        if kind in ("combo", "list"):
            from PyQt6.QtWidgets import QPlainTextEdit
            self.ed_choices = QPlainTextEdit("\n".join(c for c in props.get("choices", []) if c))
            self.ed_choices.setPlaceholderText(T("una opción por línea")); self.ed_choices.setFixedHeight(90)
            form.addRow(T("Opciones:"), self.ed_choices)
        if kind in ("text", "multiline", "combo", "list"):
            self.sp_size = QSpinBox(); self.sp_size.setRange(0, 72); self.sp_size.setValue(int(props.get("fontsize", 0)))
            self.sp_size.setSpecialValueText(T("automático")); self.sp_size.setSuffix(" pt")
            form.addRow(T("Tamaño de letra:"), self.sp_size)
        self.cb_req = QCheckBox(T("Obligatorio")); self.cb_req.setChecked(props.get("required", False))
        self.cb_ro = QCheckBox(T("Solo lectura")); self.cb_ro.setChecked(props.get("readonly", False))
        form.addRow(self.cb_req); form.addRow(self.cb_ro)
        lay.addLayout(form); lay.addWidget(_buttons(self, T("Aceptar")))

    def accept(self):
        if self.ed_choices is not None and not self.choices():
            QMessageBox.warning(self, T("Opciones"), T("Escribe al menos una opción.")); return
        super().accept()

    def choices(self):
        return [c.strip() for c in self.ed_choices.toPlainText().splitlines() if c.strip()] if self.ed_choices else []

    def props(self) -> dict:
        name = self.ed_name.currentText() if isinstance(self.ed_name, QComboBox) else self.ed_name.text()
        out = {"name": pdf_tools.clean_name(name), "tooltip": self.ed_tip.text().strip(),
               "required": self.cb_req.isChecked(), "readonly": self.cb_ro.isChecked()}
        if self.ed_value is not None: out["value"] = self.ed_value.text()
        if self.ed_choices is not None: out["choices"] = self.choices()
        if self.sp_size is not None: out["fontsize"] = self.sp_size.value()
        return out


def _can_edit_form(win) -> bool:
    if not _can_modify(win): return False
    if win._viewer.readonly:
        QMessageBox.information(win, T("Formulario"), T("El documento está abierto como solo lectura.")); return False
    return True


def pick_box(win, size, label, done):
    """Dibujar con el ratón un recuadro en la página (o un clic para el tamaño `size` en pt). Esc cancela.
    Llama a done(página, (x0, y0, x1, y1) en puntos de la página visible)."""
    from PyQt6.QtGui import QShortcut, QKeySequence
    from ui.canvas import PageCanvas
    v = win._viewer
    esc = QShortcut(QKeySequence("Esc"), win)

    def restore():
        esc.setEnabled(False); esc.deleteLater(); PageCanvas.pick_label = None
        for cv in v.canvases:
            cv.setCursor(getattr(cv, "_tool_cursor", Qt.CursorShape.ArrowCursor)); cv._pick_ghost = None; cv.update()

    def picked(page, box):
        restore(); done(page, box)

    def cancel():
        PageCanvas.pick_box = None; restore(); win._status(T("Cancelado."))
    esc.activated.connect(cancel)
    PageCanvas.pick_box = (picked, size); PageCanvas.pick_label = label
    for cv in v.canvases: cv.setCursor(Qt.CursorShape.CrossCursor)
    win._status(T("Haz clic en la página o arrastra para darle otro tamaño. Esc cancela."))


def pick_field_box(win, kind, done):
    pick_box(win, pdf_tools.FIELD_SIZE[kind], T(FIELD_KIND_NAMES[kind]), done)


def add_form_field(win, kind):
    """Documento → Formulario → Añadir: se dibuja el campo en la página y luego se eligen sus propiedades."""
    if not _can_edit_form(win): return
    win._dock_form.setVisible(True)

    def done(page, box):
        v = win._viewer
        groups = pdf_tools.radio_groups(v.doc)
        if kind == "radio":
            name = groups[-1] if groups else pdf_tools.unique_name(v.doc, T("Opciones"))
        else:
            name = pdf_tools.unique_name(v.doc, pdf_tools.clean_name(T(FIELD_KIND_NAMES[kind]).split()[0]))
        dlg = FieldDialog(win, kind, {"name": name, "choices": [T("Opción 1"), T("Opción 2")]}, groups)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        props = dlg.props()
        v.apply_doc_change(lambda d: pdf_tools.add_field(d, page, box, kind, props))
        win._form_panel.refresh()
        win._status(Tf("Campo «{0}» añadido. Se puede deshacer (Ctrl+Z).", props["name"]))
    pick_field_box(win, kind, done)


def detect_fields_dialog(win):
    """Documento → Formulario → Detectar campos: líneas, guiones bajos, casillas y recuadros vacíos → campos."""
    from core import form_detect
    if not _can_edit_form(win): return
    v = win._viewer
    dlg = QDialog(win); dlg.setWindowTitle(T("Detectar campos de formulario")); lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(T("Busca líneas para escribir («Nombre: ____»), casillas y recuadros vacíos, y crea un campo "
                           "en cada uno, con el nombre de la etiqueta que tiene al lado.\nDespués revísalos en el panel "
                           "Formulario: puedes cambiarlos, moverlos o eliminarlos, y Ctrl+Z deshace todo.")))
    r_all = QRadioButton(T("Todas las páginas")); r_cur = QRadioButton(Tf("Solo la página actual ({0})", v.current + 1))
    r_all.setChecked(True); lay.addWidget(r_all); lay.addWidget(r_cur)
    lay.addWidget(_buttons(dlg, T("Detectar")))
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    pages = [v.current] if r_cur.isChecked() else range(len(v.doc))
    found = {p: f for p in pages if (f := form_detect.detect(v.doc[p]))}
    total = sum(len(f) for f in found.values())
    if not total:
        QMessageBox.information(win, T("Detectar campos de formulario"), T("No se encontraron líneas, casillas ni recuadros "
                                "vacíos donde poner campos.\nSi el PDF es escaneado (una imagen), no se pueden detectar: "
                                "crea los campos con «Añadir campo» o usa Rellenar y firmar (J).")); return
    checks = sum(1 for f in found.values() for x in f if x["kind"] == "check")
    if QMessageBox.question(win, T("Detectar campos de formulario"), Tf("Se encontraron {0} campos ({1} de texto y {2} casillas) "
                            "en {3} página(s).\n\n¿Crearlos?", total, total - checks, checks, len(found))) != QMessageBox.StandardButton.Yes:
        return
    n = v.apply_doc_change(lambda d: form_detect.apply(d, found, pdf_tools.add_field, pdf_tools.unique_name, pdf_tools.clean_name))
    win._dock_form.setVisible(True); win._form_panel.refresh()
    win._status(Tf("{0} campos creados: revísalos en el panel Formulario. Ctrl+Z los quita todos.", n))


def reset_form_dialog(win):
    """Documento → Formulario → Vaciar: todos los campos vuelven a su valor inicial."""
    v = win._viewer
    if not (v and v.doc): return
    if not pdf_tools.form_fields(v.doc):
        QMessageBox.information(win, T("Vaciar formulario"), T("Este documento no tiene campos de formulario.")); return
    if not v.allows(pymupdf.PDF_PERM_FORM | pymupdf.PDF_PERM_ANNOTATE):
        QMessageBox.information(win, T("Documento protegido"), T("El autor no permite rellenar este formulario.")); return
    if QMessageBox.question(win, T("Vaciar formulario"), T("Se borrará lo escrito en todos los campos (vuelven a su "
                            "valor inicial). Se puede deshacer.\n\n¿Vaciar el formulario?")) != QMessageBox.StandardButton.Yes:
        return
    n = v.apply_doc_change(pdf_tools.reset_form)
    win._form_panel.refresh()
    win._status(Tf("Formulario vaciado ({0} campo(s)).", n))


class FormPanel(QWidget):
    """Lista los campos del formulario del PDF y permite rellenarlos, crearlos y editarlos (con deshacer)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QToolButton, QMenu
        self.viewer = None
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 6, 6, 6)
        bar = QHBoxLayout()
        self.bt_add = QToolButton(); self.bt_add.setText(T("Añadir campo"))
        self.bt_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        m = QMenu(self.bt_add)
        for k, name in FIELD_KIND_NAMES.items():
            m.addAction(T(name), lambda _=False, k=k: add_form_field(self.window(), k))
        m.addSeparator()
        m.addAction(T("Detectar campos automáticamente…"), lambda _=False: detect_fields_dialog(self.window()))
        self.bt_add.setMenu(m)
        self.bt_reset = QPushButton(T("Vaciar")); self.bt_reset.setToolTip(T("Borrar lo escrito en todos los campos"))
        self.bt_reset.clicked.connect(lambda: reset_form_dialog(self.window()))
        bar.addWidget(self.bt_add); bar.addWidget(self.bt_reset); bar.addStretch(1); lay.addLayout(bar)
        self.info = QLabel(); self.info.setWordWrap(True); lay.addWidget(self.info)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); lay.addWidget(self.scroll, 1)
        self.count = 0

    def set_viewer(self, viewer):
        self.viewer = viewer
        self.refresh()

    def refresh(self):
        v = self.viewer
        has_doc = bool(v and v.doc)
        fields = pdf_tools.form_fields(v.doc) if has_doc else []
        body = QWidget(); form = QFormLayout(body)
        editable = has_doc and v.allows(pymupdf.PDF_PERM_FORM | pymupdf.PDF_PERM_ANNOTATE)
        designable = has_doc and not v.readonly and v.allows(pymupdf.PDF_PERM_MODIFY)
        for f in fields:
            w = self._editor(f)
            w.setEnabled(editable and not f["readonly"])
            lbl = QLabel(Tf("{0}  (p. {1})", f['label'], f['page'] + 1)); lbl.setWordWrap(True); lbl.setToolTip(f["name"])
            row = QHBoxLayout(); row.addWidget(w, 1); row.addWidget(self._menu_button(f, designable))
            form.addRow(lbl, row)
        self.scroll.setWidget(body)
        self.bt_add.setEnabled(designable); self.bt_reset.setEnabled(editable and bool(fields))
        self.info.setText((T("Este documento no tiene campos de formulario. Usa «Añadir campo» para crearlos.") if not fields else
                           Tf("{0} campo(s). Los cambios se pueden deshacer y se guardan con el documento.", len(fields)))
                          + ("" if editable or not fields else T("\nEl autor no permite rellenar este formulario.")))
        self.count = len(fields)

    def _editor(self, f):
        set_ = lambda val, f=f: QTimer.singleShot(0, lambda: self.viewer.edit_form(f["page"], f["xref"], val))
        if f["kind"] == "check" or f["kind"] == "radio":
            w = QCheckBox(); w.setChecked(f["value"]); w.toggled.connect(set_)
        elif f["kind"] == "combo":
            w = QComboBox(); w.addItems(f["choices"]); w.setCurrentText(str(f["value"] or ""))
            w.currentTextChanged.connect(set_)
        else:
            w = QLineEdit(str(f["value"] or "")); w.editingFinished.connect(lambda w=w: set_(w.text()))
        return w

    def _menu_button(self, f, designable):
        from PyQt6.QtWidgets import QToolButton, QMenu
        b = QToolButton(); b.setText("⋯"); b.setToolTip(T("Más acciones del campo"))
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        m = QMenu(b)
        m.addAction(T("Ir al campo"), lambda: self.go_to(f))
        for text, fn in ((T("Propiedades…"), self.edit_props), (T("Mover o cambiar tamaño…"), self.move),
                         (T("Eliminar campo"), self.delete)):
            m.addAction(text, lambda _=False, fn=fn: fn(f)).setEnabled(designable)
        b.setMenu(m)
        return b

    def go_to(self, f):
        v = self.viewer
        v.highlight_search(f["page"], [pymupdf.Rect(pdf_tools.field_props(v.doc, f["page"], f["xref"])["rect"])])

    def edit_props(self, f):
        v, win = self.viewer, self.window()
        if not _can_edit_form(win): return
        old = pdf_tools.field_props(v.doc, f["page"], f["xref"])
        dlg = FieldDialog(win, old["kind"], old, pdf_tools.radio_groups(v.doc))
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        props = dlg.props()
        v.apply_doc_change(lambda d: pdf_tools.update_field(d, f["page"], f["xref"], props))
        self.refresh()

    def move(self, f):
        win = self.window()
        if not _can_edit_form(win): return
        kind = pdf_tools.field_props(self.viewer.doc, f["page"], f["xref"])["kind"]

        def done(page, box):
            if page != f["page"]:
                QMessageBox.information(win, T("Mover campo"), T("El campo solo se puede mover dentro de su página.")); return
            self.viewer.apply_doc_change(lambda d: pdf_tools.update_field(d, page, f["xref"], {}, box))
            self.refresh(); win._status(T("Campo movido. Se puede deshacer (Ctrl+Z)."))
        self.go_to(f)
        pick_field_box(win, kind, done)

    def delete(self, f):
        win = self.window()
        if not _can_edit_form(win): return
        self.viewer.apply_doc_change(lambda d: pdf_tools.delete_field(d, f["page"], f["xref"]))
        self.refresh(); win._status(Tf("Campo «{0}» eliminado. Se puede deshacer (Ctrl+Z).", f["name"]))


# ── comentarios ───────────────────────────────────────────────────────────────
class CommentsPanel(QWidget):
    """Lista de todas las anotaciones del documento (como el panel Comentarios de Acrobat), con filtros por tipo,
    estado, autor y texto, y resumen en PDF de lo que se muestra."""
    KINDS = (("all", "Todo"), ("comment", "Solo comentarios"), ("marks", "Solo marcas"))

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QListWidget, QGridLayout
        from models.annotation import REVIEW_STATES
        self.viewer = None
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 6, 6, 6)
        g = QGridLayout(); g.setContentsMargins(0, 0, 0, 0); g.setHorizontalSpacing(4)
        self.f_kind = QComboBox(); [self.f_kind.addItem(T(t), k) for k, t in self.KINDS]
        self.f_status = QComboBox(); self.f_status.addItem(T("Cualquier estado"), None)
        for k, (t, _) in REVIEW_STATES.items(): self.f_status.addItem(T(t), k)
        self.f_author = QComboBox(); self.f_author.addItem(T("Cualquier autor"), None)
        self.f_text = QLineEdit(); self.f_text.setPlaceholderText(T("Buscar en los comentarios…")); self.f_text.setClearButtonEnabled(True)
        g.addWidget(self.f_kind, 0, 0); g.addWidget(self.f_status, 0, 1)
        g.addWidget(self.f_author, 1, 0); g.addWidget(self.f_text, 1, 1)
        lay.addLayout(g)
        for w in (self.f_kind, self.f_status, self.f_author): w.currentIndexChanged.connect(self._apply)
        self.f_text.textChanged.connect(self._apply)
        row = QHBoxLayout(); self.info = QLabel(); row.addWidget(self.info, 1)
        self.b_sum = QPushButton(T("Resumen…")); self.b_sum.setToolTip(T("Crea un PDF con los comentarios que se muestran, página por página"))
        self.b_sum.clicked.connect(self.summary); row.addWidget(self.b_sum)
        lay.addLayout(row)
        self.lst = QListWidget(); self.lst.setWordWrap(True); lay.addWidget(self.lst, 1)
        self.lst.itemClicked.connect(self._go)
        self._all = []
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(300)
        self._timer.timeout.connect(self.refresh)

    def set_viewer(self, viewer):
        self.viewer = viewer
        self.refresh()

    def schedule(self): self._timer.start()

    def refresh(self):
        """Vuelve a leer las anotaciones de todas las páginas (los filtros se conservan)."""
        self._all = [(cv.page_num, a) for cv in (self.viewer.canvases if self.viewer else []) for a in cv.anns]
        authors = sorted({a.author for _, a in self._all if a.author}, key=str.lower)
        cur = self.f_author.currentData()
        self.f_author.blockSignals(True)
        while self.f_author.count() > 1: self.f_author.removeItem(1)
        for au in authors: self.f_author.addItem(au, au)
        i = self.f_author.findData(cur); self.f_author.setCurrentIndex(i if i >= 0 else 0)
        self.f_author.blockSignals(False)
        self._apply()

    def visible(self) -> list:
        """[(página, Ann)] que pasan los filtros."""
        kind, status, author = self.f_kind.currentData(), self.f_status.currentData(), self.f_author.currentData()
        q = self.f_text.text().strip().lower()
        out = []
        for pno, a in self._all:
            if kind == "comment" and a.kind != "comment": continue
            if kind == "marks" and a.kind == "comment": continue
            if status is not None and (a.kind != "comment" or a.status != status): continue
            if author is not None and a.author != author: continue
            if q and q not in " ".join([a.text or ""] + [r.get("text", "") for r in a.replies]).lower(): continue
            out.append((pno, a))
        return out

    @staticmethod
    def _describe(a) -> dict:
        from models.annotation import KIND_NAMES, REVIEW_STATES
        return {"kind": T(KIND_NAMES.get(a.kind, a.kind)), "author": a.author, "date": a.date,
                "status": T(REVIEW_STATES[a.status][0]) if a.kind == "comment" and a.status in REVIEW_STATES and a.status else "",
                "text": (a.text or "").strip(), "replies": a.replies}

    def _apply(self, *_):
        from PyQt6.QtWidgets import QListWidgetItem
        self.lst.clear()
        shown = self.visible()
        for pno, a in shown:
            d = self._describe(a)
            head = Tf("Pág. {0} · {1}", pno + 1, d["kind"])
            if a.kind == "comment" and a.author: head += f" · {a.author} {a.date}"
            if d["status"]: head += f" · {d['status']}"
            if a.kind == "comment" and a.replies: head += " · " + Tf("{0} respuesta(s)", len(a.replies))
            txt = d["text"].replace("\n", " ")
            it = QListWidgetItem(head + (f"\n{txt[:120]}" if txt else ""))
            it.setData(Qt.ItemDataRole.UserRole, (pno, a.id)); self.lst.addItem(it)
        n, total = len(shown), len(self._all)
        if not total: self.info.setText(T("Sin comentarios ni marcas."))
        elif n == total: self.info.setText(Tf("{0} comentario(s) y marca(s)", n))
        else: self.info.setText(Tf("Se muestran {0} de {1}", n, total))
        self.b_sum.setEnabled(bool(n))

    def _go(self, it):
        page, aid = it.data(Qt.ItemDataRole.UserRole)
        v = self.viewer; v.jump(page)
        cv = v.canvases[page]
        a = next((x for x in cv.anns if x.id == aid), None)
        if a: cv._setsel(a); cv._redraw()

    def summary(self):
        """Resumen en PDF de lo que se muestra (respeta los filtros)."""
        import datetime
        from core import comment_summary, i18n
        v, win = self.viewer, self.window()
        shown = self.visible()
        if not (v and v.doc and shown): return
        dlg = QDialog(win); dlg.setWindowTitle(T("Resumen de comentarios")); lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(Tf("Se incluirán los {0} elementos que muestra ahora el panel (con sus filtros).", len(shown))))
        cb = QCheckBox(T("Incluir cada página en miniatura, con sus marcas")); cb.setChecked(True); lay.addWidget(cb)
        lay.addWidget(_buttons(dlg, T("Crear…")))
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        base = os.path.splitext(v.path or "documento.pdf")[0]
        path, _ = QFileDialog.getSaveFileName(win, T("Resumen de comentarios"), base + "_" + T("comentarios") + ".pdf", T("PDF Files (*.pdf)"))
        if not path: return
        items = [dict(self._describe(a), page=pno) for pno, a in shown]
        thumbs = v.export_copy() if cb.isChecked() else None
        name = os.path.basename(v.path or "")
        date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

        def job():
            return comment_summary.build(items, path, name, date, i18n.lang(), thumbs)
        _, err = run_with_progress(win, T("Resumen de comentarios"), T("Creando el resumen…"), job)
        if thumbs is not None: thumbs.close()
        if err:
            QMessageBox.critical(win, T("Resumen de comentarios"), Tf("No se pudo crear el resumen:\n{0}", err)); return
        if QMessageBox.question(win, T("Resumen de comentarios"), Tf("Resumen creado:\n{0}", path) + "\n\n" + T("¿Abrirlo?")) == QMessageBox.StandardButton.Yes:
            win._open_path(path) if hasattr(win, "_open_path") else os.startfile(path)


# ── menú Documento: tachado, limpieza, marca de agua, numeración, propiedades ─
def _can_modify(win) -> bool:
    v = win._viewer
    if not (v and v.doc): return False
    if not v.allows(pymupdf.PDF_PERM_MODIFY):
        QMessageBox.information(win, T("Documento protegido"), T("El autor de este documento no permite modificarlo."))
        return False
    return True


def _pages_field(v):
    ed = QLineEdit(); ed.setPlaceholderText(Tf("todas ({0}) · o ej. 1-3, 8", len(v.doc)))
    return ed


def _pages(win, ed, v):
    try:
        return parse_ranges(ed.text(), len(v.doc)) if ed.text().strip() else list(range(len(v.doc)))
    except ValueError as e:
        QMessageBox.warning(win, T("Páginas"), str(e)); return None


def mark_text_for_redaction(win):
    """Como «Buscar texto y tachar» de Acrobat: marca todas las apariciones para revisarlas antes de aplicar."""
    if not _can_modify(win): return
    from core.search import find_in_page
    from models.annotation import Ann
    v = win._viewer
    dlg = QDialog(win); dlg.setWindowTitle(T("Marcar texto para tachado")); form = QFormLayout(dlg)
    ed = QLineEdit(); ed.setPlaceholderText(T("Texto a tachar (nombre, cédula, cuenta…)"))
    cb_case = QCheckBox(T("Mayúsculas y minúsculas")); cb_word = QCheckBox(T("Solo palabras completas")); cb_word.setChecked(True)
    form.addRow(T("Buscar:"), ed); form.addRow(cb_case); form.addRow(cb_word)
    note = QLabel(T("Se marcan en rojo para que las revises; nada se borra hasta «Aplicar tachado definitivo»."))
    note.setWordWrap(True); form.addRow(note); form.addRow(_buttons(dlg, T("Marcar")))
    if dlg.exec() != QDialog.DialogCode.Accepted or not ed.text().strip(): return
    term, n = ed.text().strip(), 0
    for cv in v.canvases:
        pg = v.doc[cv.page_num]
        rects = find_in_page(pg, term, cb_case.isChecked(), cb_word.isChecked())
        if not rects: continue
        cv._snap()
        for r in rects:
            q = cv._ps(r * pg.rotation_matrix)
            cv.anns.append(Ann("redact", x1=q.left(), y1=q.top(), x2=q.right(), y2=q.bottom(), stroke="#c62828"))
        cv._redraw(); cv._commit(); n += len(rects)
    win._status(Tf("{0} aparición(es) de «{1}» marcadas para tachado. Revísalas y usa Documento → Aplicar tachado definitivo.", n, term)
                if n else Tf("No se encontró «{0}».", term))


def apply_redactions(win):
    if not _can_modify(win): return
    v = win._viewer
    regions = {}
    for cv in v.canvases:
        rects = [pymupdf.Rect(min(d["x1"], d["x2"]), min(d["y1"], d["y2"]), max(d["x1"], d["x2"]), max(d["y1"], d["y2"]))
                 for d in cv.anns_to_page() if d["kind"] == "redact"]
        if rects: regions[cv.page_num] = rects
    if not regions:
        QMessageBox.information(win, T("Tachado definitivo"), T("No hay zonas marcadas. Usa la herramienta de tachado (E), "
                                "el clic derecho sobre texto seleccionado o «Marcar texto para tachado…».")); return
    total = sum(len(r) for r in regions.values())
    dlg = QDialog(win); dlg.setWindowTitle(T("Aplicar tachado definitivo")); lay = QVBoxLayout(dlg)
    lbl = QLabel(Tf("Se eliminarán de verdad el texto, las imágenes y los dibujos bajo <b>{0} zona(s)</b> en <b>{1} página(s)</b>, y se cubrirán de negro.<br>Puedes deshacerlo hasta guardar; una vez guardado, el contenido no se puede recuperar.", total, len(regions)))
    lbl.setWordWrap(True); lay.addWidget(lbl)
    cb_img = QCheckBox(T("Borrar también los píxeles de las imágenes afectadas")); cb_img.setChecked(True)
    cb_scrub = QCheckBox(T("Eliminar además la información oculta (metadatos, adjuntos, scripts)"))
    lay.addWidget(cb_img); lay.addWidget(cb_scrub); lay.addWidget(_buttons(dlg, T("Tachar")))
    if dlg.exec() != QDialog.DialogCode.Accepted: return

    def change(doc):
        n = pdf_tools.redact(doc, regions, cb_img.isChecked())
        if cb_scrub.isChecked(): pdf_tools.scrub(doc)
        return n
    for cv in v.canvases:                         # quitar las marcas (antes: así el primer Ctrl+Z devuelve el contenido)
        if any(a.kind == "redact" for a in cv.anns):
            cv._snap(); cv.anns = [a for a in cv.anns if a.kind != "redact"]; cv._redraw(); cv._commit()
    n = v.apply_doc_change(change)
    win._status(Tf("Tachado aplicado en {0} zona(s). Guarda para hacerlo permanente.", n))


def scrub_dialog(win):
    if not _can_modify(win): return
    if QMessageBox.question(win, T("Eliminar información oculta"),
                            T("Se quitarán metadatos (autor, título, programa), adjuntos, scripts y miniaturas incrustadas."
                            "\n\n¿Continuar?")) != QMessageBox.StandardButton.Yes: return
    win._viewer.apply_doc_change(pdf_tools.scrub)
    win._status(T("Información oculta eliminada. Guarda para hacerlo permanente."))


def watermark_dialog(win):
    if not _can_modify(win): return
    v = win._viewer
    from utils.eyedropper import CPBtn
    from PyQt6.QtGui import QColor
    dlg = QDialog(win); dlg.setWindowTitle(T("Marca de agua")); form = QFormLayout(dlg)
    ed = QLineEdit("CONFIDENCIAL"); sp = QSpinBox(); sp.setRange(10, 200); sp.setValue(60); sp.setSuffix(" pt")
    col = CPBtn(QColor("#c62828"), label="Color")
    op = QSpinBox(); op.setRange(5, 100); op.setValue(25); op.setSuffix(" %")
    cb_diag = QCheckBox(T("Diagonal")); cb_diag.setChecked(True); cb_behind = QCheckBox(T("Detrás del contenido"))
    pages = _pages_field(v)
    for lbl, w in (("Texto:", ed), ("Tamaño:", sp), ("Color:", col), ("Opacidad:", op), ("", cb_diag), ("", cb_behind),
                   ("Páginas:", pages)):
        form.addRow(T(lbl) if lbl else "", w)
    form.addRow(_buttons(dlg, T("Aplicar")))
    if dlg.exec() != QDialog.DialogCode.Accepted or not ed.text().strip(): return
    pp = _pages(win, pages, v)
    if pp is None: return
    v.apply_doc_change(lambda d: pdf_tools.watermark(d, pp, ed.text().strip(), sp.value(), col.color.name(),
                                                      op.value() / 100, cb_diag.isChecked(), cb_behind.isChecked()))
    win._status(Tf("Marca de agua aplicada a {0} página(s). Se puede deshacer (Ctrl+Z).", len(pp)))


NUM_FORMATS = ["Página {n} de {total}", "{n}", "{n} / {total}", "- {n} -", "DOC-{n:06d}", "{name} · {date}",
               "Confidencial — {date}"]


def background_dialog(win):
    """Documento → Páginas → Fondo de página: un color o una imagen detrás del contenido."""
    if not _can_modify(win): return
    v = win._viewer
    from utils.eyedropper import CPBtn
    from PyQt6.QtGui import QColor
    dlg = QDialog(win); dlg.setWindowTitle(T("Fondo de página")); form = QFormLayout(dlg)
    r_col = QRadioButton(T("Color")); r_img = QRadioButton(T("Imagen (se estira a toda la página)")); r_col.setChecked(True)
    col = CPBtn(QColor("#fff8e1"), label="Color")
    op = QSpinBox(); op.setRange(5, 100); op.setValue(100); op.setSuffix(" %")
    img = {"path": ""}
    b_img = QPushButton(T("Elegir imagen…"))
    def pick():
        p, _ = QFileDialog.getOpenFileName(dlg, T("Imagen de fondo"), "", T("Imágenes (*.png *.jpg *.jpeg *.bmp *.webp *.tiff)"))
        if p: img["path"] = p; b_img.setText(os.path.basename(p)); r_img.setChecked(True)
    b_img.clicked.connect(pick)
    note = QLabel(T("El fondo va detrás del contenido: se ve en las zonas transparentes. En un PDF escaneado "
                    "(cada página es una imagen) no se verá.")); note.setWordWrap(True); note.setObjectName("muted")
    pages = _pages_field(v)
    for lbl, w in (("", r_col), ("Color:", col), ("Opacidad:", op), ("", r_img), ("", b_img), ("", note), ("Páginas:", pages)):
        form.addRow(T(lbl) if lbl else "", w)
    form.addRow(_buttons(dlg, T("Aplicar")))
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    if r_img.isChecked() and not img["path"]: return
    pp = _pages(win, pages, v)
    if pp is None: return
    if r_img.isChecked():
        path = img["path"]; v.apply_doc_change(lambda d: pdf_tools.background(d, pp, image=path))
    else:
        c, o = col.color.name(), op.value() / 100
        v.apply_doc_change(lambda d: pdf_tools.background(d, pp, color=c, opacity=o))
    win._status(Tf("Fondo aplicado a {0} página(s). Se puede deshacer (Ctrl+Z).", len(pp)))


def numbering_dialog(win):
    if not _can_modify(win): return
    v = win._viewer
    dlg = QDialog(win); dlg.setWindowTitle(T("Encabezado, pie y numeración")); form = QFormLayout(dlg)
    cb_fmt = QComboBox(); cb_fmt.setEditable(True); cb_fmt.addItems([T(x) for x in NUM_FORMATS])
    cb_pos = QComboBox(); [cb_pos.addItem(T(t), k) for k, t in pdf_tools.POSITIONS.items()]; cb_pos.setCurrentIndex(1)
    sp = QSpinBox(); sp.setRange(5, 36); sp.setValue(9); sp.setSuffix(" pt")
    st = QSpinBox(); st.setRange(0, 999999); st.setValue(1)
    from utils.eyedropper import CPBtn
    from PyQt6.QtGui import QColor
    col = CPBtn(QColor("#000000"), label="Color")
    pages = _pages_field(v)
    help_ = QLabel(T("Escribe cualquier texto (encabezado o pie). Puedes usar: {n} = número · {total} = total · "
                     "{n:06d} = número con 6 cifras (Bates) · {date} = fecha de hoy · {name} = nombre del archivo"))
    help_.setObjectName("muted"); help_.setWordWrap(True)
    for lbl, w in (("Texto:", cb_fmt), ("", help_), ("Posición:", cb_pos), ("Tamaño:", sp), ("Color:", col),
                   ("Empezar en:", st), ("Páginas:", pages)):
        form.addRow(T(lbl) if lbl else "", w)
    form.addRow(_buttons(dlg, T("Aplicar")))
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    pp = _pages(win, pages, v)
    if pp is None: return
    fmt = cb_fmt.currentText()
    try:
        fmt.format(n=1, total=1, date="", name="")
    except (KeyError, ValueError, IndexError) as e:
        QMessageBox.warning(win, T("Formato"), Tf("El formato no es válido: {0}", e)); return
    c = col.color.name()
    v.apply_doc_change(lambda d: pdf_tools.number_pages(d, pp, fmt, cb_pos.currentData(), sp.value(), st.value(), c))
    win._status(Tf("Numeración aplicada a {0} página(s). Se puede deshacer (Ctrl+Z).", len(pp)))


def edit_properties(win):
    if not _can_modify(win): return
    v = win._viewer
    m = dict(v.doc.metadata or {})
    dlg = QDialog(win); dlg.setWindowTitle(T("Propiedades del documento")); dlg.setMinimumWidth(460); form = QFormLayout(dlg)
    fields = {}
    for key, label in (("title", "Título"), ("author", "Autor"), ("subject", "Asunto"), ("keywords", "Palabras clave")):
        fields[key] = QLineEdit(m.get(key) or ""); form.addRow(label + ":", fields[key])
    form.addRow(_buttons(dlg, T("Guardar cambios")))
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    new = {k: v_ for k, v_ in m.items() if k in ("title", "author", "subject", "keywords", "creator", "producer",
                                                "creationDate", "modDate")}
    new.update({k: e.text().strip() for k, e in fields.items()})
    v.apply_doc_change(lambda d: d.set_metadata(new))
    win._status(T("Propiedades actualizadas. Guarda para conservarlas."))


# ── recortar páginas ─────────────────────────────────────────────────────────
class PageCropDialog(QDialog):
    """Márgenes a quitar (en las unidades de la regla) con vista previa de la página actual."""

    def __init__(self, win, v):
        from ui.ruler import Ruler, UNITS
        from PyQt6.QtWidgets import QDoubleSpinBox
        super().__init__(win)
        self.setWindowTitle(T("Recortar páginas")); self.v = v
        self.k, unit_name, _ = UNITS[Ruler.unit]               # puntos por unidad
        self.page = v.doc[v.current]
        lay = QHBoxLayout(self)
        self.prev = QLabel(); self.prev.setFixedSize(260, 340); self.prev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prev.setStyleSheet("background:#808080;")
        lay.addWidget(self.prev)
        col = QVBoxLayout(); form = QFormLayout(); lay.addLayout(col)
        self.sp = {}
        for key, label in (("top", T("Superior:")), ("bottom", T("Inferior:")), ("left", T("Izquierdo:")), ("right", T("Derecho:"))):
            sp = QDoubleSpinBox(); sp.setDecimals(1 if Ruler.unit == "mm" else 2); sp.setRange(0, 5000)
            sp.setSingleStep(1 if Ruler.unit == "mm" else 0.1); sp.setSuffix(" " + unit_name)
            sp.valueChanged.connect(self._preview); form.addRow(label, sp); self.sp[key] = sp
        col.addLayout(form)
        b_auto = QPushButton(T("Quitar márgenes en blanco")); b_auto.setObjectName("flat")
        b_auto.setToolTip(T("Calcula los márgenes vacíos de la página actual"))
        b_auto.clicked.connect(self._auto); col.addWidget(b_auto)
        self.ck_auto_each = QCheckBox(T("Calcularlos en cada página (contenido distinto en cada una)"))
        self.ck_reset = QCheckBox(T("Quitar el recorte (volver al tamaño original)"))
        self.ck_reset.toggled.connect(lambda on: [w.setEnabled(not on) for w in (*self.sp.values(), b_auto, self.ck_auto_each)])
        col.addWidget(self.ck_auto_each); col.addWidget(self.ck_reset)
        form2 = QFormLayout()
        self.cb_pages = QComboBox()
        self.cb_pages.addItem(Tf("Página actual ({0})", v.current + 1), "current")
        self.cb_pages.addItem(Tf("Todas ({0})", len(v.doc)), "all")
        self.cb_pages.addItem(T("Rango…"), "range")
        self.ed_range = QLineEdit(); self.ed_range.setPlaceholderText(T("ej. 1-5, 8")); self.ed_range.setEnabled(False)
        self.cb_pages.currentIndexChanged.connect(lambda: self.ed_range.setEnabled(self.cb_pages.currentData() == "range"))
        form2.addRow(T("Páginas:"), self.cb_pages); form2.addRow("", self.ed_range)
        col.addLayout(form2); col.addStretch(); col.addWidget(_buttons(self, T("Recortar")))
        self._pix = None; self._preview()

    def margins(self):
        k = self.k
        return tuple(self.sp[n].value() * k for n in ("left", "top", "right", "bottom"))

    def _auto(self):
        m = pdf_tools.content_margins(self.page)
        for n, val in zip(("left", "top", "right", "bottom"), m):
            self.sp[n].blockSignals(True); self.sp[n].setValue(round(val / self.k, 2)); self.sp[n].blockSignals(False)
        self._preview()

    def _preview(self):
        from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor
        pg = self.page
        if self._pix is None:
            z = min(250 / pg.rect.width, 330 / pg.rect.height)
            pm = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), annots=False)
            self._z = z
            self._pix = QPixmap.fromImage(QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format.Format_RGB888).copy())
        out = QPixmap(self._pix); p = QPainter(out); z = self._z
        l, t, r, b = (m * z for m in self.margins()); W, H = out.width(), out.height()
        shade = QColor(0, 0, 0, 110)
        p.fillRect(0, 0, W, int(t), shade); p.fillRect(0, int(H - b), W, int(b) + 1, shade)
        p.fillRect(0, int(t), int(l), int(H - t - b), shade); p.fillRect(int(W - r), int(t), int(r) + 1, int(H - t - b), shade)
        p.setPen(QColor("#e0218a")); p.drawRect(int(l), int(t), int(W - l - r) - 1, int(H - t - b) - 1); p.end()
        self.prev.setPixmap(out)

    def target_pages(self):
        mode, v = self.cb_pages.currentData(), self.v
        if mode == "current": return [v.current]
        if mode == "all": return list(range(len(v.doc)))
        return parse_ranges(self.ed_range.text(), len(v.doc))


def crop_pages_dialog(win):
    """Documento → Recortar páginas: quita márgenes (también en blanco automáticamente) o restaura el tamaño."""
    if not _can_modify(win): return
    v = win._viewer
    dlg = PageCropDialog(win, v)
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    try:
        pages = dlg.target_pages()
        crops = {}
        for i in pages:
            pg = v.doc[i]
            if dlg.ck_reset.isChecked(): crops[i] = tuple(pg.mediabox)
            else:
                m = pdf_tools.content_margins(pg) if dlg.ck_auto_each.isChecked() else dlg.margins()
                crops[i] = tuple(pdf_tools.crop_rect(pg, *m))
    except ValueError as e:
        QMessageBox.warning(win, T("Recortar páginas"), T(str(e))); return
    v.crop_pages(crops)
    win._status(Tf("Recortadas {0} página(s). Se puede deshacer (Ctrl+Z).", len(crops)) if not dlg.ck_reset.isChecked()
                else Tf("Recorte quitado en {0} página(s).", len(crops)))


def flatten_dialog(win):
    """Documento → Aplanar: comentarios, sellos, firmas visuales, dibujos y formularios pasan a ser contenido fijo."""
    if not _can_modify(win): return
    if QMessageBox.question(win, T("Aplanar"), T(
            "Los comentarios, marcas, sellos, firmas visuales, dibujos y campos de formulario pasarán a ser parte de "
            "la página: se verán igual en cualquier lector, pero ya no se podrán editar ni mover.\n\n"
            "Las zonas marcadas para tachado definitivo no se tocan. Se puede deshacer hasta guardar.\n\n¿Aplanar?")) != QMessageBox.StandardButton.Yes: return
    n = win._viewer.flatten()
    win._status(Tf("Aplanados {0} objeto(s). Se puede deshacer (Ctrl+Z).", n) if n else T("No hay nada que aplanar."))
