# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Búsqueda avanzada en carpeta, con el aspecto de la de Acrobat: resumen arriba, un resultado por
instancia con el término en negrita, rutas contraídas y orden por relevancia/nombre/fecha/ubicación.
Para auditoría: varios términos, archivos sin coincidencias o sin texto y exportación a Excel."""
from core.portable import qsettings
from core.i18n import T, Tf
import csv
import html
import os
import re
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QRectF
from PyQt6.QtGui import QTextDocument, QAbstractTextDocumentLayout, QPalette
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
                             QCheckBox, QComboBox, QTreeWidget, QTreeWidgetItem, QFileDialog, QApplication,
                             QGroupBox, QMessageBox, QStackedWidget, QWidget, QStyledItemDelegate, QStyle)
from core.search import pdf_files, search_file, MODES
from ui.icons import get_icon
from ui.styles import C

ROLE_DATA = Qt.ItemDataRole.UserRole          # (ruta, página, término) para abrir
ROLE_HTML = Qt.ItemDataRole.UserRole + 1      # texto con el término en negrita
ROLE_META = Qt.ItemDataRole.UserRole + 2      # (ruta, instancias, fecha) para ordenar
SORTS = ["Relevancia (más instancias)", "Nombre de archivo", "Fecha de modificación", "Ubicación"]


class _Html(QStyledItemDelegate):
    """Pinta el texto del resultado como HTML (para la negrita del término)."""
    def _doc(self, opt, idx):
        d = QTextDocument(); d.setDefaultFont(opt.font); d.setDocumentMargin(2)
        d.setHtml(idx.data(ROLE_HTML) or html.escape(idx.data(Qt.ItemDataRole.DisplayRole) or ""))
        return d

    def paint(self, p, opt, idx):
        self.initStyleOption(opt, idx)
        doc = self._doc(opt, idx)
        tr = opt.widget.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)
        tr.setRight(opt.rect.right())              # el área de texto antes de vaciarlo (si no, queda angosta)
        opt.text = ""
        opt.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, p, opt.widget)
        p.save(); p.translate(tr.topLeft()); p.setClipRect(QRectF(0, 0, tr.width(), tr.height()))
        ctx = QAbstractTextDocumentLayout.PaintContext()
        sel = opt.state & QStyle.StateFlag.State_Selected
        ctx.palette.setColor(QPalette.ColorRole.Text, opt.palette.color(
            QPalette.ColorRole.HighlightedText if sel else QPalette.ColorRole.Text))
        doc.documentLayout().draw(p, ctx); p.restore()

    def sizeHint(self, opt, idx):
        self.initStyleOption(opt, idx)
        return QSize(int(self._doc(opt, idx).idealWidth()), max(22, int(self._doc(opt, idx).size().height())))


def _bold(text, term, case):
    """Texto escapado con cada aparición de `term` en negrita."""
    esc = html.escape(text)
    pat = re.escape(html.escape(term))
    return re.sub(f"({pat})", r"<b>\1</b>", esc, flags=0 if case else re.IGNORECASE)


def _short(path):
    """D:\\Docs\\…\\archivo.pdf (como «Contraer rutas de acceso» de Acrobat)."""
    parts = os.path.normpath(path).split(os.sep)
    return path if len(parts) <= 3 else os.sep.join([parts[0], parts[1][:1] + "…", parts[-1]])


class _Worker(QThread):
    result = pyqtSignal(str, object)       # archivo, {"hits", "total", "no_text"} o None (protegido/dañado)
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(int)

    def __init__(self, files, query, opts):
        super().__init__()
        self.files, self.query, self.opts, self.stop = files, query, opts, False

    def run(self):
        n = 0
        for n, f in enumerate(self.files, 1):
            if self.stop: break
            self.progress.emit(n, len(self.files), os.path.basename(f))
            self.result.emit(f, search_file(f, self.query, stop=lambda: self.stop, **self.opts))
        self.done.emit(n)


class FolderSearchDialog(QDialog):
    """Ventana no modal: se puede seguir usando PDFRapid y abrir resultados mientras busca."""
    open_result = pyqtSignal(str, int, str, bool, bool)   # archivo, página, texto, mayúsculas, palabra
    find_in_current = pyqtSignal()

    def __init__(self, parent, folder):
        super().__init__(parent)
        self.setWindowTitle(T("Buscar")); self.resize(760, 680); self.setModal(False)
        self.setSizeGripEnabled(True)
        self._s = qsettings("PDFManager")
        self.folder, self.worker = self._s.value("fsearch/folder", folder) or folder, None
        self._rows = []        # para exportar: (estado, archivo, carpeta, página, término, veces, dónde, texto)
        root = QVBoxLayout(self); root.setContentsMargins(16, 14, 16, 14)
        self.stack = QStackedWidget(); root.addWidget(self.stack)
        self.stack.addWidget(self._build_form()); self.stack.addWidget(self._build_results())
        self._reset(); self._load_opts(); self._mode_hint(); self.ed.setFocus()

    # ── página 1: formulario ────────────────────────────────────────────────
    def _build_form(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        g = QGroupBox(T("QUÉ BUSCAR")); gl = QGridLayout(g); gl.setHorizontalSpacing(8)
        self.ed = QLineEdit(); self.ed.returnPressed.connect(self._start)
        self.cb_mode = QComboBox(); [self.cb_mode.addItem(T(t), k) for k, t in MODES.items()]
        self.cb_mode.currentIndexChanged.connect(self._mode_hint)
        gl.addWidget(self.ed, 0, 0, 1, 2); gl.addWidget(QLabel(T("Modo")), 1, 0); gl.addWidget(self.cb_mode, 1, 1)
        lay.addWidget(g)
        g = QGroupBox(T("DÓNDE")); gl = QGridLayout(g); gl.setHorizontalSpacing(8)
        self.ed_folder = QLineEdit(self.folder); self.ed_folder.setReadOnly(True)
        b = QPushButton(T("Elegir…")); b.setIcon(get_icon("open")); b.clicked.connect(self._pick)
        self.cb_sub = QCheckBox(T("Incluir subcarpetas"))
        self.ed_name = QLineEdit(); self.ed_name.setPlaceholderText(T("todos los PDF · o ej. *contrato*, 2026-*"))
        gl.addWidget(QLabel(T("Carpeta")), 0, 0); gl.addWidget(self.ed_folder, 0, 1); gl.addWidget(b, 0, 2)
        gl.addWidget(self.cb_sub, 1, 1)
        gl.addWidget(QLabel(T("Archivos")), 2, 0); gl.addWidget(self.ed_name, 2, 1, 1, 2)
        lay.addWidget(g)
        g = QGroupBox(T("OPCIONES")); gl = QGridLayout(g)
        self.cb_case = QCheckBox(T("Mayúsculas y minúsculas")); self.cb_word = QCheckBox(T("Solo palabras completas"))
        self.cb_com = QCheckBox(T("Incluir comentarios")); self.cb_bm = QCheckBox(T("Incluir marcadores"))
        self.cb_missing = QCheckBox(T("Listar archivos sin coincidencias"))
        self.cb_missing.setToolTip(T("Útil para auditoría: qué documentos NO contienen lo buscado"))
        for i, cb in enumerate((self.cb_case, self.cb_word, self.cb_com, self.cb_bm, self.cb_missing)):
            gl.addWidget(cb, i // 2, i % 2)
        lay.addWidget(g)
        row = QHBoxLayout(); row.addStretch()
        self.btn = QPushButton(T("Buscar")); self.btn.setDefault(True); self.btn.setIcon(get_icon("search", color="#ffffff"))
        self.btn.clicked.connect(self._start); row.addWidget(self.btn); lay.addLayout(row)
        lay.addStretch()
        return w

    # ── página 2: resultados (como Acrobat) ─────────────────────────────────
    def _build_results(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(8)
        self.lbl_query = QLabel(); self.lbl_query.setWordWrap(True)
        self.lbl_query.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_result = QLabel(); self.lbl_result.setWordWrap(True)
        lay.addWidget(self.lbl_query); lay.addWidget(self.lbl_result)
        row = QHBoxLayout()
        bn = QPushButton(T("Nueva búsqueda")); bn.setIcon(get_icon("search")); bn.clicked.connect(self._new)
        self.btn_stop = QPushButton(T("Detener")); self.btn_stop.clicked.connect(lambda: self.worker and setattr(self.worker, "stop", True))
        bc = QPushButton(T("En el documento abierto")); bc.setObjectName("flat"); bc.setToolTip(T("Buscar en el PDF abierto en PDFRapid")); bc.clicked.connect(self.find_in_current.emit)
        row.addWidget(bn); row.addWidget(self.btn_stop); row.addStretch(); row.addWidget(bc); lay.addLayout(row)
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True); self.tree.setItemDelegate(_Html(self.tree))
        self.tree.setUniformRowHeights(True)
        self.tree.itemClicked.connect(self._open)        # un solo disparador: abrir dos veces seguidas causaba un cierre
        lay.addWidget(self.tree, 1)
        # dos filas: así la ventana puede estrecharse sin que se corten los textos
        row = QHBoxLayout()
        row.addWidget(QLabel(T("Ordenar por"))); self.cb_sort = QComboBox(); self.cb_sort.addItems([T(s) for s in SORTS])
        self.cb_sort.currentIndexChanged.connect(self._sort); row.addWidget(self.cb_sort, 1)
        self.cb_short = QCheckBox(T("Contraer rutas")); self.cb_short.setChecked(True)
        self.cb_short.setToolTip(T("Contraer rutas de acceso a archivos")); self.cb_short.toggled.connect(self._relabel)
        row.addWidget(self.cb_short); lay.addLayout(row)
        row = QHBoxLayout(); row.addStretch()
        b1 = QPushButton(T("Copiar")); b1.clicked.connect(self._copy)
        b2 = QPushButton(T("Exportar a Excel…")); b2.setIcon(get_icon("save")); b2.clicked.connect(self._export)
        row.addWidget(b1); row.addWidget(b2); lay.addLayout(row)
        return w

    # ── opciones recordadas ──
    _KEYS = (("case", "cb_case"), ("word", "cb_word"), ("com", "cb_com"), ("bm", "cb_bm"), ("missing", "cb_missing"))

    def _load_opts(self):
        s = self._s
        self.cb_sub.setChecked(s.value("fsearch/sub", True, bool)); self.ed_name.setText(s.value("fsearch/name", ""))
        self.cb_mode.setCurrentIndex(max(self.cb_mode.findData(s.value("fsearch/mode", "phrase")), 0))
        for k, attr in self._KEYS: getattr(self, attr).setChecked(s.value(f"fsearch/{k}", k == "missing", bool))

    def _save_opts(self):
        s = self._s
        s.setValue("fsearch/folder", self.folder); s.setValue("fsearch/sub", self.cb_sub.isChecked())
        s.setValue("fsearch/name", self.ed_name.text()); s.setValue("fsearch/mode", self.cb_mode.currentData())
        for k, attr in self._KEYS: s.setValue(f"fsearch/{k}", getattr(self, attr).isChecked())

    def _mode_hint(self):
        self.ed.setPlaceholderText({
            "phrase": "Palabra o frase exacta…",
            "all": "Varias palabras: el archivo debe contenerlas todas (separa con espacios o «;»)",
            "any": "Lista de términos (separa con «;» o espacios; \"frases entre comillas\")",
            "regex": r"Expresión regular, ej. \d{3}-\d{3}  ·  [\w.]+@[\w.]+",
        }[self.cb_mode.currentData()])
        self.cb_word.setEnabled(self.cb_mode.currentData() != "regex")

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, T("Carpeta donde buscar"), self.folder)
        if d: self.folder = d; self.ed_folder.setText(d)

    def _new(self):
        if self.worker and self.worker.isRunning(): self.worker.stop = True
        self.stack.setCurrentIndex(0); self.ed.setFocus(); self.ed.selectAll()

    # ── búsqueda ──
    def _start(self):
        query = self.ed.text().strip()
        if not query: return
        mode = self.cb_mode.currentData()
        if mode == "regex":
            try: re.compile(query)
            except re.error as e:
                QMessageBox.warning(self, T("Expresión regular"), Tf("No es válida: {0}", e)); return
        files = pdf_files(self.folder, self.cb_sub.isChecked(), self.ed_name.text())
        if not files:
            QMessageBox.information(self, T("Buscar"), T("No hay archivos PDF que cumplan el filtro en esa carpeta.")); return
        self._save_opts(); self._reset()
        self.lbl_query.setText(Tf("Buscar: <b>{0}</b> en <b>{1}</b>  <span style='color:{2}'>({3})</span>", html.escape(query), html.escape(self.folder), C['muted'], self.cb_mode.currentText().lower()))
        self.stack.setCurrentIndex(1)
        opts = dict(mode=mode, case=self.cb_case.isChecked(), whole=self.cb_word.isChecked() and mode != "regex",
                    comments=self.cb_com.isChecked(), bookmarks=self.cb_bm.isChecked())
        self.worker = _Worker(files, query, opts)
        self.worker.result.connect(self._add)
        self.worker.progress.connect(lambda i, n, f: self._summary(Tf("buscando {0} de {1}: {2}", i, n, f)))
        self.worker.done.connect(self._done)
        self.btn_stop.setEnabled(True); self.worker.start()

    def _reset(self):
        self.tree.clear(); self._rows = []
        self._hit_files = self._hits = 0; self._missing, self._no_text, self._skipped = [], [], []

    def _summary(self, extra=""):
        self.lbl_result.setText(Tf("Resultado: <b>{0} documento(s) con {1} instancia(s)</b>", self._hit_files, self._hits)
                                + (Tf("  <span style='color:{0}'>· {1}</span>", C['muted'], html.escape(extra)) if extra else ""))

    def _add(self, path, res):
        name, folder = os.path.basename(path), os.path.dirname(path)
        if res is None:
            self._skipped.append(path); self._rows.append(("Protegido o dañado", name, folder, "", "", "", "", "")); return
        hits, total = res["hits"], res.get("total", len(res["hits"]))
        if not hits:
            if res["no_text"]: self._no_text.append(path); state = "Sin texto (escaneado)"
            else: self._missing.append(path); state = "Sin coincidencias"
            self._rows.append((state, name, folder, "", "", "", "", "")); return
        case = self.cb_case.isChecked()
        top = QTreeWidgetItem(self.tree); top.setIcon(0, get_icon("pdf_doc")); top.setToolTip(0, path)
        top.setData(0, ROLE_DATA, (path, hits[0][0], hits[0][1]))
        top.setData(0, ROLE_META, (path, total, os.path.getmtime(path) if os.path.exists(path) else 0))
        for page, term, _n, ctx, kind in hits:
            tag = "" if kind == "texto" else f"<i>[{kind}]</i> "
            it = QTreeWidgetItem(top, [ctx])
            it.setData(0, ROLE_HTML, f"<span style='color:{C['muted']}'>p. {page + 1}</span> &nbsp;{tag}{_bold(ctx, term, case)}")
            it.setData(0, ROLE_DATA, (path, page, term))
            self._rows.append(("Coincidencia", name, folder, page + 1, term, 1, kind, ctx))
        if total > len(hits):
            QTreeWidgetItem(top, [Tf("… y {0} instancias más en este documento (no se listan)", total - len(hits))])
        self._label_file(top)
        self._hit_files += 1; self._hits += total; self._summary()

    def _label_file(self, top):
        path, total, _ = top.data(0, ROLE_META)
        shown = _short(path) if self.cb_short.isChecked() else path
        top.setData(0, ROLE_HTML, f"{html.escape(shown)} <span style='color:{C['muted']}'>({total})</span>")

    def _relabel(self):
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.data(0, ROLE_META): self._label_file(it)
        self.tree.viewport().update()

    def _sort(self):
        files = [self.tree.takeTopLevelItem(0) for _ in range(self.tree.topLevelItemCount())]
        groups = [it for it in files if not it.data(0, ROLE_META)]
        docs = [it for it in files if it.data(0, ROLE_META)]
        key = [lambda m: -m[1], lambda m: os.path.basename(m[0]).lower(), lambda m: -m[2], lambda m: m[0].lower()][self.cb_sort.currentIndex()]
        docs.sort(key=lambda it: key(it.data(0, ROLE_META)))
        for it in docs + groups: self.tree.addTopLevelItem(it)

    def _group(self, title, paths, color):
        if not paths: return
        top = QTreeWidgetItem(self.tree)
        top.setData(0, ROLE_HTML, f"<span style='color:{color}'><b>{html.escape(title)}</b> ({len(paths)})</span>")
        for p in paths:
            it = QTreeWidgetItem(top, [p]); it.setToolTip(0, p); it.setData(0, ROLE_DATA, (p, 0, ""))

    def _done(self, n):
        self.btn_stop.setEnabled(False)
        self._sort()
        if self.cb_missing.isChecked(): self._group(T("Sin coincidencias"), self._missing, C['muted'])
        self._group(T("Sin texto: escaneados, no se pudieron revisar (usa OCR)"), self._no_text, C['warn'])
        self._group(T("Protegidos con contraseña o dañados: omitidos"), self._skipped, C['danger'])
        extra = [f"{n} revisados", f"{len(self._missing)} sin coincidencias", f"{len(self._no_text)} sin texto",
                 f"{len(self._skipped)} omitidos"]
        self._summary(" · ".join(e for e in extra if not e.startswith("0 ")))
        if self.tree.topLevelItemCount(): self.tree.topLevelItem(0).setExpanded(True)

    def _open(self, it, _col=0):
        data = it.data(0, ROLE_DATA)
        if data:
            path, page, term = data
            self.open_result.emit(path, page, term, self.cb_case.isChecked(),
                                  self.cb_word.isChecked() and self.cb_mode.currentData() != "regex")

    # ── exportar ──
    def _copy(self):
        lines = ["\t".join(map(str, r)) for r in self._rows]
        QApplication.clipboard().setText("\n".join(lines))
        self._summary(Tf("copiadas {0} filas (se pueden pegar en Excel)", len(lines)))

    def _export(self):
        if not self._rows: return
        path, _ = QFileDialog.getSaveFileName(self, T("Exportar resultados"), os.path.join(self.folder, "resultados_busqueda.csv"),
                                              T("CSV para Excel (*.csv)"))
        if not path: return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:      # BOM y «;»: Excel en español lo abre bien
            w = csv.writer(f, delimiter=";")
            w.writerow([f"Búsqueda: {self.ed.text()}", f"Modo: {self.cb_mode.currentText()}", f"Carpeta: {self.folder}"])
            w.writerow(["Estado", "Archivo", "Carpeta", "Página", "Término", "Veces", "Dónde", "Texto"])
            w.writerows(self._rows)
        self._summary(f"exportado: {path}")

    def closeEvent(self, ev):
        if self.worker and self.worker.isRunning():
            self.worker.stop = True; self.worker.wait(3000)
        super().closeEvent(ev)
