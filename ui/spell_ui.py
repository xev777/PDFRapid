# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Revisión ortográfica mientras escribes: subraya en rojo ondulado las palabras desconocidas y, con clic derecho
sobre una, ofrece sugerencias, «Añadir al diccionario» e «Ignorar». Usa el corrector de Windows (core/spell.py)."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from core import spell
from core.i18n import T, lang


class _Highlighter(QSyntaxHighlighter):
    def __init__(self, doc, chk):
        super().__init__(doc)
        self.chk = chk
        self.fmt = QTextCharFormat()
        self.fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        self.fmt.setUnderlineColor(QColor("#d32f2f"))

    def highlightBlock(self, text):
        try:
            for start, n in self.chk.errors(text): self.setFormat(start, n, self.fmt)
        except OSError:
            pass


def enabled() -> bool:
    from core.settings import AppSettings
    return AppSettings().get_bool("spellcheck", True)


def set_enabled(on: bool):
    from core.settings import AppSettings
    AppSettings().set_bool("spellcheck", bool(on))


def attach(editor):
    """Activa la revisión en un QTextEdit / QPlainTextEdit. No hace nada si está desactivada o no hay corrector."""
    if not enabled(): return None
    chk = spell.checker(lang())
    if chk is None: return None
    hl = _Highlighter(editor.document(), chk)
    editor._spell = hl
    editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    editor.customContextMenuRequested.connect(lambda pos: _menu(editor, chk, pos))
    return hl


def _word_at(editor, pos):
    cur = editor.cursorForPosition(pos)
    cur.select(QTextCursor.SelectionType.WordUnderCursor)
    return cur, cur.selectedText()


def _menu(editor, chk, pos):
    menu = editor.createStandardContextMenu(pos)
    cur, word = _word_at(editor, pos)
    if word and not editor.isReadOnly() and chk.errors(word):
        first = menu.actions()[0] if menu.actions() else None
        sugg = chk.suggest(word)
        acts = []
        for s in sugg:
            a = menu.addAction(s); f = a.font(); f.setBold(True); a.setFont(f)
            a.triggered.connect(lambda _=False, s=s, c=QTextCursor(cur): c.insertText(s)); acts.append(a)
        if not sugg:
            a = menu.addAction(T("(sin sugerencias)")); a.setEnabled(False); acts.append(a)
        add = menu.addAction(T("Añadir al diccionario"))
        add.triggered.connect(lambda _=False: (chk.add(word), editor._spell.rehighlight()))
        ign = menu.addAction(T("Ignorar"))
        ign.triggered.connect(lambda _=False: (chk.ignore(word), editor._spell.rehighlight()))
        acts += [add, ign]
        for a in acts: menu.removeAction(a)
        if first:
            menu.insertActions(first, acts); menu.insertSeparator(first)
        else:
            menu.addActions(acts)
    menu.exec(editor.viewport().mapToGlobal(pos))
    menu.deleteLater()
