# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import pymupdf
from models.annotation import Ann


def _abrir(qapp, tmp_path, n):
    from ui.main_window import MainWindow
    p = str(tmp_path / "grande.pdf")
    d = pymupdf.open()
    for i in range(n):
        d.new_page().insert_text((72, 72), f"Pagina {i+1}")
    d.save(p)
    w = MainWindow()
    w.resize(1000, 800)
    w.show()
    w._open_path(p)
    qapp.processEvents()
    return w


def test_solo_renderiza_paginas_visibles(qapp, tmp_path):
    w = _abrir(qapp, tmp_path, 200)
    cvs = w._viewer.canvases
    cargadas = [i for i, cv in enumerate(cvs) if cv._base is not None]
    assert 0 in cargadas and len(cargadas) < 10
    w._viewer.go_to(199)
    qapp.processEvents()
    assert cvs[199]._base is not None
    assert cvs[0]._base is None                      # liberada al alejarse
    assert cvs[0].height() == cvs[199].height()      # conserva su tamaño


def test_zoom_y_deshacer_conservan_posicion(qapp, tmp_path):
    w = _abrir(qapp, tmp_path, 3)
    cv = w._viewer.canvases[0]
    cv._snap(); cv.anns.append(Ann("rect", x1=50, y1=60, x2=150, y2=120)); cv._commit()
    cv._snap(); cv.anns[0].x1 += 30; cv._commit()            # mover
    w._viewer.zoom_to(w._viewer.zoom * 2)
    w._undo()
    x1_pdf = cv.anns_to_page()[0]["x1"]
    w._viewer.zoom_to(w._viewer.zoom / 2)
    assert abs(cv.anns[0].x1 - 50) < 0.01 and abs(cv.anns_to_page()[0]["x1"] - x1_pdf) < 0.01


def test_limite_de_memoria_en_deshacer(qapp, tmp_path):
    w = _abrir(qapp, tmp_path, 2)
    v = w._viewer
    v.MAX_DOC_UNDO_BYTES = 1000
    for _ in range(5):
        v._push(("doc", b"x" * 600))
    assert sum(1 for e in v._undo if e[0] == "doc") == 1


def test_documento_enorme_no_renderiza_todo_al_abrir(qapp, tmp_path):
    w = _abrir(qapp, tmp_path, 1500)
    qapp.processEvents()
    assert sum(cv._base is not None for cv in w._viewer.canvases) <= 12
    assert len(w.thumbs._done) <= 60


def test_paginas_no_se_aplastan_en_documentos_largos(qapp, tmp_path):
    w = _abrir(qapp, tmp_path, 600)          # > 524 287 px, el tope de los QLayout
    for cv in (w._viewer.canvases[0], w._viewer.canvases[-1]):
        assert cv.parentWidget().height() >= cv.height()
    w._viewer.zoom_to(w._viewer.zoom * 2)
    cv = w._viewer.canvases[-1]
    assert cv.parentWidget().height() >= cv.height()
