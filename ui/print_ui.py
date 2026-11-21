# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Imprimir: una sola ventana con impresora, copias, páginas, tamaño (ajustar, real, reducir, escala), póster, varias
páginas por hoja, folleto, doble cara, orientación, comentarios y una vista previa en vivo de cada hoja.
Las hojas se componen en un PDF aparte (core/imposition.py); la vista previa y la impresión usan la misma
colocación (`place`), así lo que se ve es lo que sale."""
import pymupdf
from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QPainter, QImage, QPageLayout, QPixmap, QColor, QPen
from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintDialog, QPageSetupDialog
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QComboBox, QLineEdit, QCheckBox,
                             QDoubleSpinBox, QSpinBox, QRadioButton, QButtonGroup, QLabel, QMessageBox, QPushButton,
                             QStackedWidget, QWidget, QSlider, QToolButton, QApplication)
from core import imposition
from core.i18n import T, Tf
from core.logger import log
from core.pages import parse_ranges
from core.portable import qsettings

MAX_DPI = 300                      # más resolución no se nota en papel y multiplica la memoria
SIZE_MODES = ("fit", "shrink", "actual", "custom")     # una página por hoja
COMPOSED = ("nup", "booklet", "poster")                # la hoja ya trae su orientación


def place(area_w, area_h, pw, ph, fit="fit", scale=1.0, auto_rotate=False):
    """Dónde va una página de pw×ph en un área imprimible de area_w×area_h (mismas unidades).
    Devuelve (rect, girada 90°, escala). `fit`: fit = ajustar, shrink = reducir solo si no cabe,
    actual = 100 %, custom = `scale`. Con `auto_rotate`, una página apaisada se gira en papel vertical y viceversa."""
    rot = auto_rotate and abs(pw - ph) > 1 and (pw > ph) != (area_w > area_h)
    w, h = (ph, pw) if rot else (pw, ph)
    k = min(area_w / w, area_h / h)
    s = {"fit": k, "shrink": min(1.0, k), "actual": 1.0, "custom": scale}.get(fit, k)
    return QRectF((area_w - w * s) / 2, (area_h - h * s) / 2, w * s, h * s), rot, s


def _draw(pa: QPainter, area: QRectF, img: QImage, pw, ph, unit, opts):
    """Dibuja la hoja `img` (pw×ph puntos) en `area` (unidades del dispositivo; `unit` = unidades por punto)."""
    mode = opts.get("mode", "fit")
    fit = mode if mode in SIZE_MODES else "fit"
    r, rot, _ = place(area.width() / unit, area.height() / unit, pw, ph, fit, opts.get("scale", 1.0),
                      opts.get("orient", "auto") == "auto" and mode in SIZE_MODES)
    r = QRectF(area.x() + r.x() * unit, area.y() + r.y() * unit, r.width() * unit, r.height() * unit)
    if opts.get("gray"): img = img.convertToFormat(QImage.Format.Format_Grayscale8)
    pa.save()
    pa.setClipRect(area)
    if rot:
        pa.translate(r.center()); pa.rotate(90)
        pa.drawImage(QRectF(-r.height() / 2, -r.width() / 2, r.height(), r.width()), img)
    else:
        pa.drawImage(r, img)
    pa.restore()


def _image(page, zoom):
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()


def compose(src_copy, opts: dict, sheet_size):
    """PDF con las hojas tal como se imprimirán. `src_copy` se modifica (aplanado y sin giros)."""
    imposition.prepare(src_copy, opts["annots"])
    pages, mode = opts["pages"], opts["mode"]
    if mode == "nup": return imposition.n_up(src_copy, pages, opts["n"], sheet_size, border=opts["border"])
    if mode == "booklet": return imposition.booklet(src_copy, pages, sheet_size)
    if mode == "poster": return imposition.poster(src_copy, pages, sheet_size, opts["poster_scale"], marks=opts["marks"])[0]
    out = pymupdf.open()
    for p in pages: out.insert_pdf(src_copy, from_page=p, to_page=p)
    return out


def configure(pr: QPrinter, opts: dict, doc=None):
    """Aplica a la impresora copias, color, doble cara y orientación."""
    if opts.get("printer"): pr.setPrinterName(opts["printer"])
    pr.setCopyCount(max(1, opts.get("copies", 1)))
    pr.setColorMode(QPrinter.ColorMode.GrayScale if opts.get("gray") else QPrinter.ColorMode.Color)
    pr.setDuplex({"long": QPrinter.DuplexMode.DuplexLongSide, "short": QPrinter.DuplexMode.DuplexShortSide}
                 .get(opts.get("duplex"), QPrinter.DuplexMode.DuplexNone))
    o = opts.get("orient", "auto")
    if o == "auto" and opts.get("mode") in COMPOSED and doc is not None and len(doc):
        r = doc[0].rect; o = "landscape" if r.width > r.height else "portrait"
    pr.setPageOrientation(QPageLayout.Orientation.Landscape if o == "landscape" else QPageLayout.Orientation.Portrait)


def paint(pr: QPrinter, doc, opts=False):
    """Dibuja cada hoja de `doc` en la impresora (respeta el intervalo elegido en el diálogo del sistema).
    `opts`: diccionario de opciones, o True/False (compatibilidad: tamaño real / ajustar)."""
    if not isinstance(opts, dict): opts = {"mode": "actual" if opts else "fit", "orient": "portrait"}
    pa = QPainter(pr)
    try:
        area = QRectF(pr.pageRect(QPrinter.Unit.DevicePixel))
        area.moveTo(0, 0)
        unit = pr.resolution() / 72
        zoom = min(pr.resolution(), MAX_DPI) / 72
        first, last = pr.fromPage(), pr.toPage()
        idx = [i for i in range(len(doc)) if not first or first - 1 <= i <= last - 1]
        for n, i in enumerate(idx):
            if n: pr.newPage()
            try:
                pg = doc[i]
                _draw(pa, area, _image(pg, zoom), pg.rect.width, pg.rect.height, unit, opts)
            except Exception:
                log.exception(f"imprimir hoja {i}")
    finally:
        pa.end()


class PrintDialog(QDialog):
    """Ventana de impresión con vista previa. `src` = copia del documento con anotaciones (None: sin vista previa)."""

    def __init__(self, parent, n_pages: int, current: int, src=None):
        super().__init__(parent)
        self.n, self.current = n_pages, current
        self._src_bytes = src.tobytes() if src is not None else None
        self._doc = None; self._key = None; self._sheet = 0
        self.st = qsettings("PDFManager")
        self.pr = QPrinter(QPrinter.PrinterMode.HighResolution)
        self.setWindowTitle(T("Imprimir")); self.setMinimumSize(900, 640); self.resize(980, 700)
        root = QVBoxLayout(self)

        # ── impresora, copias, grises ──
        top = QGridLayout()
        self.cb_printer = QComboBox()
        names = QPrinterInfo.availablePrinterNames()
        self.cb_printer.addItems(names)
        want = self.st.value("print/printer", "") or QPrinterInfo.defaultPrinterName()
        if want in names: self.cb_printer.setCurrentText(want)
        b_prefs = QPushButton(T("Preferencias…")); b_prefs.setToolTip(T("Opciones propias de la impresora (calidad, papel, bandeja)"))
        b_prefs.clicked.connect(self._printer_prefs)
        self.sp_copies = QSpinBox(); self.sp_copies.setRange(1, 999)
        self.cb_gray = QCheckBox(T("Escala de grises (blanco y negro)"))
        self.cb_gray.setChecked(self.st.value("print/gray", False, type=bool))
        top.addWidget(QLabel(T("Impresora:")), 0, 0); top.addWidget(self.cb_printer, 0, 1); top.addWidget(b_prefs, 0, 2)
        top.addWidget(QLabel(T("Copias:")), 1, 0); top.addWidget(self.sp_copies, 1, 1, Qt.AlignmentFlag.AlignLeft)
        top.addWidget(self.cb_gray, 1, 2)
        top.setColumnStretch(1, 1)
        root.addLayout(top)

        body = QHBoxLayout(); root.addLayout(body, 1)
        left = QVBoxLayout(); body.addLayout(left, 3)

        # ── páginas ──
        g = QGroupBox(T("Páginas")); gl = QVBoxLayout(g)
        row = QHBoxLayout()
        self.rb_all, self.rb_cur, self.rb_range = (QRadioButton(T("Todas")), QRadioButton(Tf("Actual ({0})", current + 1)),
                                                   QRadioButton(T("Páginas:")))
        self.rb_all.setChecked(True)
        grp = QButtonGroup(self)
        for b in (self.rb_all, self.rb_cur, self.rb_range): grp.addButton(b); row.addWidget(b)
        self.ed_range = QLineEdit(); self.ed_range.setPlaceholderText(Tf("ej. 1-3, 8 (de {0})", n_pages))
        self.ed_range.textEdited.connect(lambda: self.rb_range.setChecked(True))
        row.addWidget(self.ed_range, 1); gl.addLayout(row)
        self.b_more = QToolButton(); self.b_more.setText(T("Más opciones")); self.b_more.setCheckable(True)
        self.b_more.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon); self.b_more.setAutoRaise(True)
        self.b_more.setArrowType(Qt.ArrowType.RightArrow)
        more = QWidget(); ml = QHBoxLayout(more); ml.setContentsMargins(18, 0, 0, 0)
        self.cb_subset = QComboBox()
        for key, name in (("all", T("Todas las del intervalo")), ("odd", T("Solo impares")), ("even", T("Solo pares"))):
            self.cb_subset.addItem(name, key)
        self.cb_reverse = QCheckBox(T("Orden inverso"))
        ml.addWidget(self.cb_subset); ml.addWidget(self.cb_reverse); ml.addStretch(1); more.hide()
        self.b_more.toggled.connect(lambda on: (more.setVisible(on), self.b_more.setArrowType(
            Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)))
        gl.addWidget(self.b_more); gl.addWidget(more)
        left.addWidget(g)

        # ── tamaño y forma ──
        g = QGroupBox(T("Tamaño y forma")); gl = QVBoxLayout(g)
        tabs = QHBoxLayout(); self.grp_kind = QButtonGroup(self)
        self.stack = QStackedWidget()
        for i, (key, name, tip) in enumerate((
                ("size", T("Tamaño"), T("Una página por hoja: ajustar, tamaño real o escala")),
                ("poster", T("Póster"), T("Una página repartida en varias hojas para pegarlas")),
                ("nup", T("Varias por hoja"), T("Varias páginas reducidas en cada hoja para ahorrar papel")),
                ("booklet", T("Folleto"), T("Hojas dobladas por la mitad, como una revista")))):
            b = QPushButton(name); b.setCheckable(True); b.setToolTip(tip); b.setProperty("kind", key)
            self.grp_kind.addButton(b, i); tabs.addWidget(b)
        self.grp_kind.button(0).setChecked(True)
        from ui.styles import C
        g.setStyleSheet(f"QPushButton:checked {{ background-color:{C['accent']}; color:white; border-color:{C['accent']}; }}")
        gl.addLayout(tabs); gl.addWidget(self.stack)
        # tamaño
        w = QWidget(); wl = QGridLayout(w); wl.setContentsMargins(0, 4, 0, 0)
        self.grp_fit = QButtonGroup(self)
        for i, (key, name) in enumerate((("fit", T("Ajustar a la hoja")), ("actual", T("Tamaño real")),
                                         ("shrink", T("Reducir solo las páginas grandes")), ("custom", T("Escala:")))):
            b = QRadioButton(name); b.setProperty("fit", key); self.grp_fit.addButton(b, i)
            wl.addWidget(b, i // 2, (i % 2) * 2)
        self.grp_fit.button(0).setChecked(True)
        self.sp_scale = QSpinBox(); self.sp_scale.setRange(10, 400); self.sp_scale.setValue(100); self.sp_scale.setSuffix(" %")
        self.sp_scale.valueChanged.connect(lambda: self.grp_fit.button(3).setChecked(True))
        wl.addWidget(self.sp_scale, 1, 3)
        self.stack.addWidget(w)
        # póster
        w = QWidget(); wl = QGridLayout(w); wl.setContentsMargins(0, 4, 0, 0)
        self.sp_poster = QDoubleSpinBox(); self.sp_poster.setRange(110, 1000); self.sp_poster.setValue(200)
        self.sp_poster.setSuffix(" %"); self.sp_poster.setSingleStep(50); self.sp_poster.setDecimals(0)
        self.cb_marks = QCheckBox(T("Etiquetas para unir las hojas")); self.cb_marks.setChecked(True)
        wl.addWidget(QLabel(T("Ampliación:")), 0, 0); wl.addWidget(self.sp_poster, 0, 1); wl.addWidget(self.cb_marks, 0, 2)
        hint = QLabel(T("Las hojas se solapan 6 mm para pegarlas.")); hint.setObjectName("muted")
        wl.addWidget(hint, 1, 0, 1, 3)
        self.stack.addWidget(w)
        # varias por hoja
        w = QWidget(); wl = QHBoxLayout(w); wl.setContentsMargins(0, 4, 0, 0)
        self.cb_n = QComboBox()
        for n in imposition.GRIDS: self.cb_n.addItem(str(n), n)
        self.cb_n.setCurrentIndex(1)
        self.cb_border = QCheckBox(T("Borde alrededor de cada página")); self.cb_border.setChecked(True)
        wl.addWidget(QLabel(T("Páginas por hoja:"))); wl.addWidget(self.cb_n); wl.addWidget(self.cb_border); wl.addStretch(1)
        self.stack.addWidget(w)
        # folleto
        w = QWidget(); wl = QVBoxLayout(w); wl.setContentsMargins(0, 4, 0, 0)
        hint = QLabel(T("Imprime a doble cara, volteando por el borde corto, y dobla las hojas por la mitad. "
                        "Al elegir Folleto se activa la doble cara por el borde corto."))
        hint.setWordWrap(True); wl.addWidget(hint)
        self.stack.addWidget(w)
        self.stack.setMinimumHeight(max(self.stack.widget(i).sizeHint().height() for i in range(self.stack.count())) + 8)
        self.grp_kind.idClicked.connect(self._kind_changed)
        left.addWidget(g)

        # ── doble cara y orientación ──
        g = QGroupBox(T("Doble cara y orientación")); gl = QGridLayout(g)
        self.cb_duplex = QCheckBox(T("Imprimir a doble cara"))
        self.rb_long, self.rb_short = QRadioButton(T("Voltear por el borde largo")), QRadioButton(T("Voltear por el borde corto"))
        self.rb_long.setChecked(True)
        gd = QButtonGroup(self); gd.addButton(self.rb_long); gd.addButton(self.rb_short)
        self.cb_duplex.toggled.connect(lambda on: (self.rb_long.setEnabled(on), self.rb_short.setEnabled(on)))
        self.cb_duplex.setChecked(self.st.value("print/duplex", False, type=bool)); self.cb_duplex.toggled.emit(self.cb_duplex.isChecked())
        gl.addWidget(self.cb_duplex, 0, 0, 1, 3); gl.addWidget(self.rb_long, 1, 0); gl.addWidget(self.rb_short, 1, 1)
        self.grp_orient = QButtonGroup(self)
        gl.addWidget(QLabel(T("Orientación:")), 2, 0, 1, 3)
        for i, (key, name) in enumerate((("auto", T("Automática")), ("portrait", T("Vertical")), ("landscape", T("Horizontal")))):
            b = QRadioButton(name); b.setProperty("orient", key); self.grp_orient.addButton(b, i); gl.addWidget(b, 3, i)
        self.grp_orient.button(0).setChecked(True)
        left.addWidget(g)

        # ── comentarios ──
        g = QGroupBox(T("Comentarios y formularios")); gl = QHBoxLayout(g)
        self.cb_annots = QComboBox()
        self.cb_annots.addItem(T("Documento con comentarios, marcas y formularios"), True)
        self.cb_annots.addItem(T("Solo el documento"), False)
        gl.addWidget(self.cb_annots)
        left.addWidget(g); left.addStretch(1)

        # ── vista previa ──
        right = QVBoxLayout(); body.addLayout(right, 2)
        self.lb_scale = QLabel(); self.lb_size = QLabel()
        for lb in (self.lb_scale, self.lb_size): lb.setAlignment(Qt.AlignmentFlag.AlignCenter); right.addWidget(lb)
        self.preview = QLabel(); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setMinimumSize(300, 380)
        right.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        self.b_prev, self.b_next = QToolButton(), QToolButton()
        self.b_prev.setArrowType(Qt.ArrowType.LeftArrow); self.b_next.setArrowType(Qt.ArrowType.RightArrow)
        self.b_prev.setToolTip(T("Hoja anterior")); self.b_next.setToolTip(T("Hoja siguiente"))
        self.slider = QSlider(Qt.Orientation.Horizontal); self.slider.setMinimum(1)
        nav.addWidget(self.b_prev); nav.addWidget(self.slider, 1); nav.addWidget(self.b_next)
        right.addLayout(nav)
        self.lb_sheet = QLabel(); self.lb_sheet.setAlignment(Qt.AlignmentFlag.AlignCenter); right.addWidget(self.lb_sheet)
        self.b_prev.clicked.connect(lambda: self.slider.setValue(self.slider.value() - 1))
        self.b_next.clicked.connect(lambda: self.slider.setValue(self.slider.value() + 1))
        self.slider.valueChanged.connect(self._show_sheet)

        # ── botones ──
        bottom = QHBoxLayout()
        b_setup = QPushButton(T("Configurar página…")); b_setup.setToolTip(T("Tamaño de papel y márgenes"))
        b_setup.clicked.connect(self._page_setup)
        self.b_print = QPushButton(T("Imprimir")); self.b_print.setDefault(True)
        b_cancel = QPushButton(T("Cancelar"))
        self.b_print.clicked.connect(self.accept); b_cancel.clicked.connect(self.reject)
        bottom.addWidget(b_setup); bottom.addStretch(1); bottom.addWidget(self.b_print); bottom.addWidget(b_cancel)
        root.addLayout(bottom)

        # cambios → vista previa (agrupados para no recomponer en cada pulsación)
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(200)
        self._timer.timeout.connect(self.refresh)
        for sig in (grp.buttonClicked, self.ed_range.textChanged, self.cb_subset.currentIndexChanged, self.cb_reverse.toggled,
                    self.grp_kind.idClicked, self.grp_fit.idClicked, self.sp_scale.valueChanged, self.sp_poster.valueChanged,
                    self.cb_marks.toggled, self.cb_n.currentIndexChanged, self.cb_border.toggled, self.cb_duplex.toggled,
                    self.grp_orient.idClicked, self.cb_annots.currentIndexChanged, self.cb_gray.toggled,
                    self.cb_printer.currentIndexChanged):
            sig.connect(lambda *_: self._timer.start())
        self.refresh()

    # ── opciones ──
    def kind(self):
        return self.grp_kind.checkedButton().property("kind")

    def pages(self):
        if self.rb_cur.isChecked(): pp = [self.current]
        elif self.rb_range.isChecked() and self.ed_range.text().strip(): pp = parse_ranges(self.ed_range.text(), self.n)
        else: pp = list(range(self.n))
        sub = self.cb_subset.currentData()
        if sub == "odd": pp = [p for p in pp if p % 2 == 0]           # páginas 1, 3, 5… (índice par)
        elif sub == "even": pp = [p for p in pp if p % 2 == 1]
        return pp[::-1] if self.cb_reverse.isChecked() else pp

    def options(self) -> dict:
        k = self.kind()
        mode = self.grp_fit.checkedButton().property("fit") if k == "size" else k
        return {"pages": self.pages(), "annots": self.cb_annots.currentData(), "mode": mode,
                "scale": self.sp_scale.value() / 100, "n": self.cb_n.currentData(), "border": self.cb_border.isChecked(),
                "poster_scale": self.sp_poster.value() / 100, "marks": self.cb_marks.isChecked(),
                "orient": self.grp_orient.checkedButton().property("orient"), "gray": self.cb_gray.isChecked(),
                "duplex": ("short" if self.rb_short.isChecked() else "long") if self.cb_duplex.isChecked() else "none",
                "copies": self.sp_copies.value(), "printer": self.cb_printer.currentText()}

    def _kind_changed(self, i):
        self.stack.setCurrentIndex(i)
        if self.kind() == "booklet":
            self.cb_duplex.setChecked(True); self.rb_short.setChecked(True)

    def _printer_prefs(self):
        self.pr.setPrinterName(self.cb_printer.currentText())
        dlg = QPrintDialog(self.pr, self); dlg.setWindowTitle(T("Preferencias de la impresora"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            i = self.cb_printer.findText(self.pr.printerName())
            if i >= 0: self.cb_printer.setCurrentIndex(i)
            self.sp_copies.setValue(max(1, self.pr.copyCount()))
            self._key = None; self.refresh()

    def _page_setup(self):
        self.pr.setPrinterName(self.cb_printer.currentText())
        if QPageSetupDialog(self.pr, self).exec() == QDialog.DialogCode.Accepted:
            self._key = None; self.refresh()

    # ── vista previa ──
    def _paper(self):
        """Tamaño del papel vertical en puntos (las hojas compuestas se giran solas)."""
        r = self.pr.pageLayout().fullRect(QPageLayout.Unit.Point)
        w, h = r.width(), r.height()
        return (min(w, h), max(w, h))

    def refresh(self):
        if self.cb_printer.currentText(): self.pr.setPrinterName(self.cb_printer.currentText())
        try:
            o = self.options()
        except ValueError as e:
            self.lb_sheet.setText(str(e)); self.preview.clear(); return
        if self._src_bytes is None: return
        sheet = self._paper()
        key = (tuple(o["pages"]), o["annots"], o["mode"] if o["mode"] in COMPOSED else "one", o["n"], o["border"],
               o["poster_scale"], o["marks"], sheet)
        if key != self._key:
            if self._doc is not None: self._doc.close()
            src = pymupdf.open("pdf", self._src_bytes)
            try:
                self._doc = compose(src, o, sheet) if o["pages"] else pymupdf.open()
            finally:
                src.close()
            self._key = key
        configure(self.pr, o, self._doc)
        n = len(self._doc)
        self.slider.blockSignals(True); self.slider.setMaximum(max(1, n))
        self.slider.setValue(min(max(1, self.slider.value()), max(1, n))); self.slider.blockSignals(False)
        for b in (self.b_prev, self.b_next, self.slider): b.setEnabled(n > 1)
        self.b_print.setEnabled(n > 0)
        self._show_sheet(self.slider.value())

    def _show_sheet(self, v):
        n = len(self._doc) if self._doc is not None else 0
        self.lb_sheet.setText(Tf("Hoja {0} de {1}", v, n) if n else T("No hay páginas que imprimir."))
        if not n: self.preview.clear(); self.lb_scale.clear(); self.lb_size.clear(); return
        o = self.options()
        lay = self.pr.pageLayout()
        full, paint_r = lay.fullRect(QPageLayout.Unit.Point), lay.paintRect(QPageLayout.Unit.Point)
        box = self.preview.size()
        k = min((box.width() - 12) / full.width(), (box.height() - 12) / full.height())
        pm = QPixmap(int(full.width() * k) + 2, int(full.height() * k) + 2); pm.fill(QColor("white"))
        pa = QPainter(pm); pa.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pg = self._doc[v - 1]
        area = QRectF(paint_r.x() * k, paint_r.y() * k, paint_r.width() * k, paint_r.height() * k)
        _draw(pa, area, _image(pg, min(2.0, 2 * k)), pg.rect.width, pg.rect.height, k, o)
        pa.setPen(QPen(QColor("#555"), 1)); pa.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
        pa.end()
        self.preview.setPixmap(pm)
        mode = o["mode"]
        if mode in SIZE_MODES:
            _, _, s = place(paint_r.width(), paint_r.height(), pg.rect.width, pg.rect.height, mode, o["scale"],
                            o["orient"] == "auto")
            self.lb_scale.setText(Tf("Escala: {0} %", round(s * 100)))
        else:
            self.lb_scale.setText("")
        mm = 25.4 / 72
        self.lb_size.setText(Tf("Papel: {0} × {1} mm", round(full.width() * mm), round(full.height() * mm)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._doc is not None and len(self._doc): self._show_sheet(self.slider.value())

    # ── imprimir ──
    def accept(self):
        try:
            if not self.pages(): raise ValueError(T("No hay páginas que imprimir."))
        except ValueError as e:
            QMessageBox.warning(self, T("Páginas"), str(e)); return
        self.refresh()
        o = self.options()
        self.st.setValue("print/printer", o["printer"]); self.st.setValue("print/gray", o["gray"])
        self.st.setValue("print/duplex", o["duplex"] != "none")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            paint(self.pr, self._doc, o)
        finally:
            QApplication.restoreOverrideCursor()
        super().accept()

    def done(self, r):
        if self._doc is not None: self._doc.close(); self._doc = None
        super().done(r)
        self.deleteLater()            # destrucción ordenada: el recolector de Python la hacía a destiempo y cerraba el proceso


def print_viewer(viewer):
    """Archivo → Imprimir: una ventana con opciones y vista previa; Imprimir envía a la impresora elegida."""
    src = viewer.export_copy()
    try:
        dlg = PrintDialog(viewer, len(viewer.doc), max(0, viewer.current), src)
    finally:
        src.close()
    import os
    if getattr(viewer, "path", None): dlg.pr.setDocName(os.path.basename(viewer.path))
    dlg.exec()
