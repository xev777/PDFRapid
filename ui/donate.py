# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Apoyar el proyecto: explica por qué donar y, solo si la persona lo decide, abre la página de donación en el
navegador. Nunca aparece sola (sin ventanas emergentes automáticas)."""
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout
from core.constants import APP_NAME, DONATE_URL
from core.i18n import T, Tf
from ui.icons import get_icon

MESSAGE = ("Si este programa te ayuda en tu día a día, considera hacer una donación. Se ha invertido mucho tiempo y "
           "conocimiento para ofrecerte, sin costo, la experiencia que dan las aplicaciones de pago o por suscripción. "
           "Tu aporte permite seguir mejorándolo. ¡Gracias de antemano por tu generosidad!")


class DonateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(Tf("Apoyar {0}", APP_NAME)); self.setMinimumWidth(460)
        lay = QVBoxLayout(self); lay.setSpacing(12); lay.setContentsMargins(18, 16, 18, 14)
        head = QHBoxLayout()
        ico = QLabel(); ico.setPixmap(get_icon("heart").pixmap(40, 40)); head.addWidget(ico, 0, Qt.AlignmentFlag.AlignTop)
        title = QLabel(f"<h3 style='margin:0'>{Tf('Apoya {0}', APP_NAME)}</h3>"); head.addWidget(title, 1)
        lay.addLayout(head)
        self.text = QLabel(T(MESSAGE)); self.text.setWordWrap(True); lay.addWidget(self.text)
        note = QLabel(Tf("Se abrirá {0} en tu navegador. {1} seguirá siendo gratuito y completo, dones o no.",
                         DONATE_URL, APP_NAME))
        note.setWordWrap(True); note.setObjectName("muted"); lay.addWidget(note)
        bb = QDialogButtonBox()
        self.b_donate = bb.addButton(T("Donar"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.b_donate.setIcon(get_icon("heart")); self.b_donate.setDefault(True)
        bb.addButton(T("Ahora no"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._donate); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _donate(self):
        QDesktopServices.openUrl(QUrl(DONATE_URL))
        self.accept()


def show(parent):
    DonateDialog(parent).exec()
