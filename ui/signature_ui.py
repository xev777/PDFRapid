# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Firma digital con certificado: diálogo para firmar y panel con las firmas del documento."""
from core.portable import qsettings
from core.i18n import T, Tf
import html
import os
import pymupdf
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QCheckBox, QComboBox,
                             QSpinBox, QFileDialog, QMessageBox, QLabel, QWidget, QVBoxLayout, QListWidget,
                             QListWidgetItem)
from core import signing, wincert
from ui.doc_tools import run_with_progress, _buttons
from ui.icons import get_icon
from ui.styles import C


class SignDialog(QDialog):
    def __init__(self, parent, n_pages):
        super().__init__(parent)
        self.setWindowTitle(T("Firmar con certificado digital")); self.setMinimumWidth(600)
        s = qsettings("PDFManager")
        form = QFormLayout(self)
        row = QHBoxLayout()
        self.ed_cert = QLineEdit(s.value("sign/cert", "")); self.ed_cert.setPlaceholderText(T("Archivo .p12 o .pfx de tu firma electrónica"))
        b = QPushButton(T("Elegir…")); b.setIcon(get_icon("open")); b.clicked.connect(self._pick)
        row.addWidget(self.ed_cert, 1); row.addWidget(b)
        self.ed_pw = QLineEdit(); self.ed_pw.setEchoMode(QLineEdit.EchoMode.Password)
        # origen del certificado: archivo .p12/.pfx o token USB / tarjeta inteligente (PKCS#11)
        self.cb_src = QComboBox()
        self.cb_src.addItem(T("Archivo .p12 / .pfx"), "file"); self.cb_src.addItem(T("Token USB o tarjeta inteligente"), "token")
        if wincert.available(): self.cb_src.addItem(T("Certificado instalado en Windows"), "windows")
        self.cb_src.setCurrentIndex(max(self.cb_src.findData(s.value("sign/source", "file")), 0))
        self.cb_lib = QComboBox(); self.cb_lib.setEditable(True)
        for path, name in signing.token_libraries(): self.cb_lib.addItem(f"{name} — {path}", path)
        saved_lib = s.value("sign/token_lib", "")
        if saved_lib and self.cb_lib.findData(saved_lib) < 0: self.cb_lib.addItem(saved_lib, saved_lib)
        if saved_lib: self.cb_lib.setCurrentIndex(self.cb_lib.findData(saved_lib))
        self.cb_lib.lineEdit().setPlaceholderText(T("Biblioteca PKCS#11 del token (.dll)"))
        self.cb_lib.setToolTip(T("La instala el controlador del token o de la tarjeta (p. ej. eTPKCS11.dll de SafeNet)."))
        lib_row = QHBoxLayout(); lib_row.addWidget(self.cb_lib, 1)
        bl = QPushButton(T("Elegir…")); bl.clicked.connect(self._pick_lib); lib_row.addWidget(bl)
        self.cb_tcert = QComboBox()
        bd = QPushButton(T("Detectar")); bd.setToolTip(T("Lee los certificados del token conectado (no pide el PIN)"))
        bd.clicked.connect(self._detect)
        tc_row = QHBoxLayout(); tc_row.addWidget(self.cb_tcert, 1); tc_row.addWidget(bd)
        self._saved_tcert = s.value("sign/token_cert", "")
        # certificado del almacén de Windows (muchos tokens lo registran ahí al conectarse)
        self.cb_wcert = QComboBox()
        bw = QPushButton(T("Actualizar")); bw.setToolTip(T("Vuelve a leer los certificados de Windows (p. ej. tras conectar el token)"))
        bw.clicked.connect(self._load_wcerts)
        wc_row = QHBoxLayout(); wc_row.addWidget(self.cb_wcert, 1); wc_row.addWidget(bw)
        self._saved_wcert = s.value("sign/win_cert", ""); self._wcerts_loaded = False
        # sello de tiempo (lo único que usa internet, y solo si se activa)
        self.cb_tsa = QCheckBox(T("Añadir sello de tiempo (usa internet)"))
        self.cb_tsa.setChecked(s.value("sign/tsa_on", "false") == "true")
        self.cb_tsa.setToolTip(T("Certifica la hora de la firma con un servidor de sellado (RFC 3161). Lo piden algunos trámites."))
        self.cb_ltv = QCheckBox(T("Firma de larga duración (LTV, usa internet)"))
        self.cb_ltv.setChecked(s.value("sign/ltv_on", "false") == "true")
        self.cb_ltv.setToolTip(T("Guarda en el PDF los certificados y los datos de revocación de la entidad (OCSP/CRL) y un "
                                 "sello de tiempo del documento, para que la firma pueda verificarse dentro de muchos años. "
                                 "Necesita el sello de tiempo."))
        self.cb_ltv.toggled.connect(lambda on: on and self.cb_tsa.setChecked(True))
        self.ed_tsa = QLineEdit(s.value("sign/tsa_url", ""))
        self.ed_tsa.setPlaceholderText(T("Servidor de sellado, p. ej. el de tu entidad de certificación"))
        self.ed_reason = QLineEdit(s.value("sign/reason", "Aprobación del documento"))
        self.ed_loc = QLineEdit(s.value("sign/location", ""))
        self.cb_vis = QCheckBox(T("Firma visible en la página")); self.cb_vis.setChecked(True)
        self.sp_page = QSpinBox(); self.sp_page.setRange(1, n_pages); self.sp_page.setValue(n_pages)
        self.cb_pos = QComboBox()
        self.cb_pos.addItem(T("Elegir en la página con el ratón…"), "pick")
        [self.cb_pos.addItem(T(t), k) for k, t in signing.POSITIONS.items()]
        self.cb_pos.setCurrentIndex(max(self.cb_pos.findData(s.value("sign/pos", "pick")), 0))
        self.cb_style = QComboBox(); [self.cb_style.addItem(T(t), k) for k, t in signing.STYLES.items()]
        self.cb_style.setCurrentIndex(max(self.cb_style.findData(s.value("sign/style", "qr")), 0))
        self.cb_size = QComboBox(); [self.cb_size.addItem(T(t), k) for k, t in signing.SIZES.items()]
        self.cb_size.setCurrentIndex(max(self.cb_size.findData(float(s.value("sign/size", 1.0))), 0))
        self.ed_url = QLineEdit(s.value("sign/qr_url", ""))
        self.ed_url.setPlaceholderText(T("Opcional: dirección web donde validar la firma"))
        self.ed_url.setToolTip(T("Se añade al código QR. Por ejemplo, el validador oficial de tu país."))
        form.addRow(T("Origen:"), self.cb_src)
        form.addRow(T("Certificado:"), row)
        form.addRow(T("Biblioteca:"), lib_row); form.addRow(T("Certificado del token:"), tc_row)
        form.addRow(T("Certificado:"), wc_row)
        self.lbl_pw = QLabel(T("Contraseña:")); form.addRow(self.lbl_pw, self.ed_pw)
        self._form, self._file_row, self._lib_row, self._tc_row, self._wc_row = form, row, lib_row, tc_row, wc_row
        form.addRow(T("Motivo:"), self.ed_reason); form.addRow(T("Lugar:"), self.ed_loc)
        form.addRow("", self.cb_vis); form.addRow(T("Apariencia:"), self.cb_style); form.addRow(T("Tamaño:"), self.cb_size); form.addRow(T("Validar en:"), self.ed_url)
        form.addRow(T("Posición:"), self.cb_pos); form.addRow(T("Página:"), self.sp_page)
        form.addRow("", self.cb_tsa); form.addRow(T("Sellado:"), self.ed_tsa); form.addRow("", self.cb_ltv)

        def sync():
            on = self.cb_vis.isChecked()
            for w in (self.cb_style, self.cb_pos, self.cb_size): w.setEnabled(on)
            self.ed_url.setEnabled(on and self.cb_style.currentData() == "qr")
            self.sp_page.setEnabled(on and self.cb_pos.currentData() != "pick")     # al elegir con el ratón, la página es esa
            tok, win = self.token, self.cb_src.currentData() == "windows"
            form.setRowVisible(self._file_row, not tok and not win)
            form.setRowVisible(self._lib_row, tok); form.setRowVisible(self._tc_row, tok)
            form.setRowVisible(self._wc_row, win); form.setRowVisible(self.ed_pw, not win)   # Windows pide el PIN él mismo
            if win and not self._wcerts_loaded: self._load_wcerts()
            self.lbl_pw.setText(T("PIN:") if tok else T("Contraseña:"))
            self.ed_tsa.setEnabled(self.cb_tsa.isChecked())
            if not self.cb_tsa.isChecked(): self.cb_ltv.setChecked(False)          # LTV necesita el sello de tiempo
        for sig in (self.cb_vis.toggled, self.cb_style.currentIndexChanged, self.cb_pos.currentIndexChanged,
                    self.cb_src.currentIndexChanged, self.cb_tsa.toggled): sig.connect(sync)
        sync()
        note = QLabel(T("Se crea una copia firmada (el original no cambia). Usa el certificado emitido por una entidad "
                      "acreditada para que la firma tenga validez legal."))
        note.setWordWrap(True); note.setObjectName("muted"); form.addRow(note)
        form.addRow(_buttons(self, T("Firmar…")))
        (self.ed_pw if self.ed_cert.text() else self.ed_cert).setFocus()

    @property
    def token(self) -> bool: return self.cb_src.currentData() == "token"

    def lib_path(self) -> str:
        return (self.cb_lib.currentData() if self.cb_lib.currentData() and self.cb_lib.currentText() == self.cb_lib.itemText(
            self.cb_lib.currentIndex()) else self.cb_lib.currentText()).strip()

    def _pick_lib(self):
        p, _ = QFileDialog.getOpenFileName(self, T("Biblioteca PKCS#11"), os.environ.get("WINDIR", ""), T("Bibliotecas (*.dll)"))
        if p: self.cb_lib.addItem(p, p); self.cb_lib.setCurrentIndex(self.cb_lib.count() - 1)

    def _detect(self):
        lib = self.lib_path()
        if not os.path.isfile(lib):
            QMessageBox.warning(self, T("Token"), T("Elige la biblioteca PKCS#11 de tu token (.dll).")); return
        try:
            certs = signing.list_token_certs(lib)
        except Exception as e:
            QMessageBox.warning(self, T("Token"), Tf("No se pudo leer el token: {0}", e)); return
        self.cb_tcert.clear()
        for c in certs:
            self.cb_tcert.addItem(f"{c['name'] or c['label']}  ·  {c['token']}", c)
        if not certs:
            QMessageBox.information(self, T("Token"), T("No se encontraron certificados. Comprueba que el token está conectado."))
        i = next((k for k, c in enumerate(certs) if c["id"] == self._saved_tcert), 0)
        self.cb_tcert.setCurrentIndex(i if certs else -1)
        self.ed_pw.setFocus()

    def _load_wcerts(self):
        self._wcerts_loaded = True
        try:
            certs = [c for c in wincert.list_certs() if c["signing"]]
        except Exception as e:
            QMessageBox.warning(self, T("Certificado"), Tf("No se pudieron leer los certificados de Windows: {0}", e)); return
        self.cb_wcert.clear()
        for c in certs:
            self.cb_wcert.addItem(Tf("{0}  ·  {1}  ·  vence {2}", c["name"], c["issuer"], f"{c['until']:%d/%m/%Y}"), c["thumb"])
        if not certs:
            self.cb_wcert.addItem(T("No hay certificados de firma instalados en Windows"), None)
        i = self.cb_wcert.findData(self._saved_wcert)
        self.cb_wcert.setCurrentIndex(max(i, 0))

    def make_signer(self):
        """(firmante, sesión a cerrar o None) según el origen elegido."""
        if self.cb_src.currentData() == "windows":
            return wincert.make_signer(self.cb_wcert.currentData()), None
        if self.token:
            c = self.cb_tcert.currentData()
            return signing.open_token_signer(self.lib_path(), c["slot"], self.ed_pw.text(), c["id"])
        return signing.load_signer(self.ed_cert.text(), self.ed_pw.text()), None

    def _pick(self):
        p, _ = QFileDialog.getOpenFileName(self, T("Certificado de firma"), os.path.dirname(self.ed_cert.text()),
                                           T("Certificados (*.p12 *.pfx)"))
        if p: self.ed_cert.setText(p); self.ed_pw.setFocus()

    def accept(self):
        if self.cb_src.currentData() == "windows":
            if not self.cb_wcert.currentData():
                QMessageBox.warning(self, T("Certificado"), T("Elige un certificado de firma instalado en Windows.")); return
        elif self.token:
            if not self.cb_tcert.currentData():
                QMessageBox.warning(self, T("Token"), T("Conecta el token y pulsa «Detectar» para elegir el certificado.")); return
        elif not os.path.isfile(self.ed_cert.text()):
            QMessageBox.warning(self, T("Certificado"), T("Elige el archivo .p12/.pfx de tu certificado.")); return
        if self.cb_tsa.isChecked() and not self.ed_tsa.text().strip().lower().startswith(("http://", "https://")):
            QMessageBox.warning(self, T("Sello de tiempo"), T("Escribe la dirección del servidor de sellado (http:// o https://).")); return
        try:                                           # comprobar contraseña o PIN antes de seguir
            _, sess = self.make_signer()
            if sess is not None: sess.close()
        except ValueError as e:
            QMessageBox.warning(self, T("Certificado"), str(e)); return
        except Exception as e:
            QMessageBox.warning(self, T("Certificado"), Tf("No se pudo usar el certificado: {0}", e)); return
        s = qsettings("PDFManager")           # se recuerdan certificado, motivo y lugar (nunca la contraseña)
        s.setValue("sign/cert", self.ed_cert.text()); s.setValue("sign/reason", self.ed_reason.text())
        s.setValue("sign/location", self.ed_loc.text()); s.setValue("sign/pos", self.cb_pos.currentData())
        s.setValue("sign/style", self.cb_style.currentData()); s.setValue("sign/qr_url", self.ed_url.text().strip())
        s.setValue("sign/size", self.cb_size.currentData())
        s.setValue("sign/source", self.cb_src.currentData()); s.setValue("sign/token_lib", self.lib_path())
        if self.cb_tcert.currentData(): s.setValue("sign/token_cert", self.cb_tcert.currentData()["id"])
        if self.cb_wcert.currentData(): s.setValue("sign/win_cert", self.cb_wcert.currentData())
        s.setValue("sign/tsa_on", "true" if self.cb_tsa.isChecked() else "false"); s.setValue("sign/tsa_url", self.ed_tsa.text().strip())
        s.setValue("sign/ltv_on", "true" if self.cb_ltv.isChecked() else "false")
        super().accept()


def sign_document(win):
    v = win._viewer
    if not (v and v.doc): return
    if not v.allows(pymupdf.PDF_PERM_ANNOTATE):
        QMessageBox.information(win, T("Documento protegido"), T("El autor de este documento no permite firmarlo.")); return
    if v.dirty or not v.path:
        if QMessageBox.question(win, T("Firmar"), T("Para firmar, primero hay que guardar los cambios. ¿Guardar ahora?")) \
                != QMessageBox.StandardButton.Yes or not win.save_pdf():
            return
    dlg = SignDialog(win, len(v.doc))
    if dlg.exec() != QDialog.DialogCode.Accepted: return
    if dlg.cb_vis.isChecked() and dlg.cb_pos.currentData() == "pick":
        pick_signature_box(win, dlg)
    else:
        _finish_sign(win, dlg, dlg.sp_page.value() - 1, None)


def pick_signature_box(win, dlg):
    """Elegir con el ratón dónde va la firma: arrastrar un recuadro (o un clic para el tamaño estándar). Esc cancela."""
    from PyQt6.QtGui import QShortcut, QKeySequence
    from ui.canvas import PageCanvas
    v = win._viewer
    size = signing.box_size(dlg.cb_style.currentData(), dlg.cb_size.currentData())
    esc = QShortcut(QKeySequence("Esc"), win)

    def restore():
        esc.setEnabled(False); esc.deleteLater()
        for cv in v.canvases:
            cv.setCursor(getattr(cv, "_tool_cursor", Qt.CursorShape.ArrowCursor)); cv._pick_ghost = None; cv.update()

    def done(page, box):
        restore()
        _finish_sign(win, dlg, page, signing.visible_to_pdf_box(v.doc[page], box))

    def cancel():
        PageCanvas.pick_box = None; restore(); win._status(T("Firma cancelada."))
    esc.activated.connect(cancel)
    PageCanvas.pick_box = (done, size)
    for cv in v.canvases: cv.setCursor(Qt.CursorShape.CrossCursor)
    win._status(T("Haz clic donde quieres la firma (el recuadro muestra su tamaño) o arrastra para otro tamaño. Esc cancela."))


def _finish_sign(win, dlg, page, box):
    v = win._viewer
    base = os.path.splitext(v.path)[0]
    out, _ = QFileDialog.getSaveFileName(win, T("Guardar documento firmado"), base + "_firmado.pdf", T("PDF Files (*.pdf)"))
    if not out: return
    if os.path.abspath(out) == os.path.abspath(v.path):
        QMessageBox.information(win, T("Firmar"), T("Elige otro nombre: el documento firmado se guarda como una copia.")); return
    pw = v.crypt["user_pw"] if v.crypt else None
    pos = dlg.cb_pos.currentData() if dlg.cb_pos.currentData() != "pick" else "br"
    tsa = dlg.ed_tsa.text().strip() if dlg.cb_tsa.isChecked() else ""

    def job():
        signer, sess = dlg.make_signer()
        try:
            return signing.sign_pdf(v.path, out, None, None, page, pos, dlg.cb_vis.isChecked(), dlg.ed_reason.text(),
                                    dlg.ed_loc.text(), pdf_password=pw, box=box, style=dlg.cb_style.currentData(),
                                    qr_url=dlg.ed_url.text().strip(), signer=signer, tsa_url=tsa,
                                    scale=dlg.cb_size.currentData(), ltv=dlg.cb_ltv.isChecked())
        finally:
            if sess is not None: sess.close()
    name, err = run_with_progress(win, T("Firmar"), T("Firmando el documento…") if not tsa
                                  else T("Firmando y descargando los datos de validación…") if dlg.cb_ltv.isChecked()
                                  else T("Firmando y pidiendo el sello de tiempo…"), job)
    if err:
        QMessageBox.critical(win, T("Firmar"), Tf("No se pudo firmar:\n{0}", err)); return
    win._open_path(out)
    win._status(Tf("Documento firmado por {0}: {1}", name, out))


class SignaturesPanel(QWidget):
    """Firmas digitales del documento abierto y su estado."""
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 6, 6, 6)
        self.setMinimumWidth(280)
        self.info = QLabel(); self.info.setWordWrap(True); lay.addWidget(self.info)
        self.lst = QListWidget(); self.lst.setWordWrap(True); lay.addWidget(self.lst, 1)
        note = QLabel(T("«Íntegra»: el contenido firmado no cambió. La confianza en la entidad emisora del certificado "
                      "no se verifica (PDFRapid funciona sin conexión)."))
        note.setWordWrap(True); note.setStyleSheet(f"color:{C['muted']};font-size:10px;"); lay.addWidget(note)
        self.count = 0

    def load(self, path, pdf_password=None):
        self.lst.clear(); self.count = 0
        if not path or not os.path.exists(path):
            self.info.setText(T("Sin documento.")); return
        try:
            sigs = signing.list_signatures(path, pdf_password)
        except Exception as e:
            self.info.setText(Tf("No se pudieron leer las firmas: {0}", e)); return
        self.count = len(sigs)
        for s in sigs:
            ok = s["integra"]
            fecha = s["fecha"].strftime("%d/%m/%Y %H:%M") if s["fecha"] else T("fecha desconocida")
            estado = (T("✔ Íntegra") if ok else T("✖ Alterada o no válida")) + ("" if s["cubre_todo"] or not ok else
                                                                                T(" · hubo cambios después de firmar"))
            if s.get("sello") and not s.get("documento"): estado += T(" · con sello de tiempo")
            if s.get("ltv"): estado += T(" · larga duración (LTV)")
            it = QListWidgetItem(f"{s['firmante'] or s['nombre']}\n{fecha}  ·  {estado}", self.lst)
            it.setForeground(Qt.GlobalColor.darkGreen if ok and s["cubre_todo"] else Qt.GlobalColor.darkYellow if ok
                             else Qt.GlobalColor.red)
            tip = [Tf("Firmante: {0}", s['firmante']), Tf("Emisor: {0}", s['emisor'])]
            if s["vence"]: tip.append(Tf("Certificado vence: {0}", f"{s['vence']:%d/%m/%Y}"))
            if s["motivo"]: tip.append(Tf("Motivo: {0}", s['motivo']))
            if s["lugar"]: tip.append(Tf("Lugar: {0}", s['lugar']))
            if s.get("ltv"): tip.append(T("Incluye los datos para verificarla en el futuro (certificados y revocación)."))
            if s["error"]: tip.append(Tf("Error: {0}", s['error']))
            it.setToolTip("\n".join(tip))
        self.info.setText(Tf("{0} firma(s) digital(es).", len(sigs)) if sigs else T("Este documento no tiene firmas digitales."))
