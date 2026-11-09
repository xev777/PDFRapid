# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Apoyar el proyecto: el mensaje y el enlace solo se abren a petición."""


def test_dialogo_donar(qapp, monkeypatch):
    from ui import donate
    from core.constants import DONATE_URL
    abiertos = []
    monkeypatch.setattr(donate.QDesktopServices, "openUrl", lambda u: abiertos.append(u.toString()))
    dlg = donate.DonateDialog()
    assert "donación" in dlg.text.text() and not abiertos       # abrir el diálogo no abre la página
    dlg.b_donate.click()
    assert abiertos == [DONATE_URL] and DONATE_URL.startswith("https://")
