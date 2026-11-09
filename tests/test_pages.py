# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import pymupdf
import pytest
from core import pages


def test_parse_ranges():
    assert pages.parse_ranges("1-3, 5, 8-", 9) == [0, 1, 2, 4, 7, 8]
    assert pages.parse_ranges("-2; 2", 5) == [0, 1]
    assert pages.parse_ranges("3-1", 5) == [2, 1, 0]
    for bad in ("", "0", "4-7", "a"):
        with pytest.raises(ValueError):
            pages.parse_ranges(bad, 5)


def test_dividir_y_combinar():
    d = pymupdf.open()
    for i in range(5):
        d.new_page().insert_text((50, 50), f"p{i + 1}")
    assert pages.groups_every(2, 5) == [[0, 1], [2, 3], [4]]
    assert pages.groups_ranges("1-2, 4-5", 5) == [[0, 1], [3, 4]]
    parts = [pages.extract(d, g) for g in pages.groups_every(2, 5)]
    assert [len(p) for p in parts] == [2, 2, 1]
    todo = pages.combine(parts)
    assert [todo[i].get_text().strip() for i in range(5)] == ["p1", "p2", "p3", "p4", "p5"]


def test_busqueda_avanzada(tmp_path):
    from core.search import search_file, parse_terms
    d = pymupdf.open(); p = d.new_page()
    p.insert_text((72, 72), "Contrato 123-456 firmado por Juan"); p.add_text_annot((50, 50), "revisar pago")
    d.new_page().insert_text((72, 72), "Anexo de pago"); d.set_toc([[1, "Pago final", 2]])
    f = str(tmp_path / "s.pdf"); d.save(f)
    assert parse_terms('pago "firmado por"', "any") == ["pago", "firmado por"]
    kinds = sorted(h[4] for h in search_file(f, "pago", comments=True, bookmarks=True)["hits"])
    assert kinds == ["comentario", "marcador", "texto"]
    assert search_file(f, r"\d{3}-\d{3}", "regex")["hits"][0][1] == "123-456"
    assert search_file(f, "contrato anexo", "all")["hits"] and not search_file(f, "contrato zzz", "all")["hits"]
    assert len(search_file(f, "zzz; anexo", "any")["hits"]) == 1


def test_comparar_documentos():
    from core.compare import compare_docs
    a, b = pymupdf.open(), pymupdf.open()
    a.new_page().insert_text((72, 72), "El plazo es de 30 dias habiles")
    b.new_page().insert_text((72, 72), "El plazo es de 45 dias calendario")
    a.new_page().insert_text((72, 72), "Pagina igual"); b.new_page().insert_text((72, 72), "Pagina igual")
    b.new_page().insert_text((72, 72), "Anexo nuevo")
    res = compare_docs(a, b)
    assert [r["status"] for r in res] == ["cambios", "igual", "solo B"]
    assert ("30", "45") in res[0]["changes"] and ("habiles", "calendario") in res[0]["changes"]
    assert len(res[0]["removed"]) == 2 and len(res[0]["added"]) == 2
