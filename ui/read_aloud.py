# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Leer en voz alta con las voces instaladas en Windows (Qt TextToSpeech), sin conexión: la página actual, desde
aquí hasta el final (pasa de página sola) o el texto seleccionado. Vista → Leer en voz alta."""
import re
import pymupdf
from PyQt6.QtCore import QObject
from core.i18n import T, Tf, lang
from core.settings import AppSettings


def page_text(page) -> str:
    """Texto de la página para leer: une las líneas de cada párrafo y quita los guiones de fin de línea."""
    t = page.get_text("text", flags=pymupdf.TEXT_DEHYPHENATE | pymupdf.TEXT_PRESERVE_WHITESPACE)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"(?<!\n)\n(?!\n)", " ", t)             # salto simple = mismo párrafo
    return t.strip()


class ReadAloud(QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.tts = None
        self.queue = []                 # páginas que faltan leer
        self.page = None                # página que se está leyendo
        self._stopping = False

    # ── motor ──
    def _engine(self):
        if self.tts is None:
            from PyQt6.QtTextToSpeech import QTextToSpeech
            self.tts = QTextToSpeech(self)
            self.tts.stateChanged.connect(self._on_state)
            self._apply_settings()
        return self.tts

    def _apply_settings(self):
        s = AppSettings(); t = self.tts
        voices = t.availableVoices()
        name = s.get_str("tts_voice", "")
        v = next((v for v in voices if v.name() == name), None) or \
            next((v for v in voices if v.locale().name().split("_")[0] == lang()), None)
        if v is not None: t.setVoice(v)
        try: t.setRate(max(-1.0, min(1.0, float(s.get_str("tts_rate", "0") or 0))))
        except ValueError: pass

    def available(self) -> bool:
        try:
            return bool(self._engine().availableVoices())
        except Exception:
            return False

    # ── acciones ──
    def _viewer(self):
        v = getattr(self.win, "_viewer", None)
        return v if v and v.doc else None

    def read(self, how: str):
        """how: page | to_end | selection."""
        v = self._viewer()
        if not v: return
        if not self.available():
            self.win._status(T("No hay voces instaladas en Windows (Configuración → Hora e idioma → Voz).")); return
        self.stop()
        if how == "selection":
            cv = v.canvases[v.current]
            text = (getattr(cv, "_tsel_text", "") or "").strip()
            if not text:
                self.win._status(T("Primero selecciona texto con la herramienta Seleccionar texto (S).")); return
            self.queue, self.page = [], None
            self._say(text); self.win._status(T("Leyendo el texto seleccionado…  (Vista → Leer en voz alta → Detener)"))
            return
        self.queue = list(range(v.current, len(v.doc))) if how == "to_end" else [v.current]
        self._next()

    def _next(self):
        v = self._viewer()
        while v and self.queue:
            self.page = self.queue.pop(0)
            text = page_text(v.doc[self.page])
            if text:
                if v.current != self.page: v.go_to(self.page)
                self._say(text)
                self.win._status(Tf("Leyendo la página {0}…  (Vista → Leer en voz alta → Pausar o Detener)", self.page + 1))
                return
        self.page = None

    def _say(self, text):
        self._stopping = False
        self._engine().say(text)

    def _on_state(self, state):
        from PyQt6.QtTextToSpeech import QTextToSpeech
        if state == QTextToSpeech.State.Ready and not self._stopping:
            if self.queue: self._next()
            else: self.page = None
        elif state == QTextToSpeech.State.Error:
            self.queue = []; self.win._status(Tf("No se pudo leer en voz alta: {0}", self.tts.errorString()))

    def pause_resume(self):
        if not self.tts: return
        from PyQt6.QtTextToSpeech import QTextToSpeech
        st = self.tts.state()
        if st == QTextToSpeech.State.Speaking: self.tts.pause(); self.win._status(T("Lectura en pausa."))
        elif st == QTextToSpeech.State.Paused: self.tts.resume()

    def stop(self):
        self.queue = []; self.page = None
        if self.tts:
            self._stopping = True
            self.tts.stop()

    def speaking(self) -> bool:
        if not self.tts: return False
        from PyQt6.QtTextToSpeech import QTextToSpeech
        return self.tts.state() in (QTextToSpeech.State.Speaking, QTextToSpeech.State.Paused)

    def settings_dialog(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QSlider
        t = self._engine()
        dlg = QDialog(self.win); dlg.setWindowTitle(T("Voz y velocidad")); form = QFormLayout(dlg)
        cb = QComboBox()
        for v in t.availableVoices(): cb.addItem(f"{v.name()}  ({v.locale().name()})", v.name())
        cb.setCurrentIndex(max(cb.findData(t.voice().name()), 0))
        sl = QSlider(Qt.Orientation.Horizontal); sl.setRange(-10, 10); sl.setValue(round(t.rate() * 10))
        form.addRow(T("Voz:"), cb); form.addRow(T("Velocidad (más lenta ← → más rápida):"), sl)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        s = AppSettings(); s.set_str("tts_voice", cb.currentData() or ""); s.set_str("tts_rate", str(sl.value() / 10))
        self._apply_settings()
