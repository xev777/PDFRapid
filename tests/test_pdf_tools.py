# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import pymupdf
from core import pdf_tools
from core.pdf_io import save_pdf


def _png(path, w=400, h=300):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
    pix.clear_with(180)
    pix.save(str(path))
    return str(path)


def test_proteger(tmp_path):
    d = pymupdf.open(); d.new_page().insert_text((50, 50), "hola")
    p = str(tmp_path / "p.pdf")
    save_pdf(d, p, pdf_tools.make_crypt("abc", "dueno", {"print"}))
    r = pymupdf.open(p)
    assert r.needs_pass and r.authenticate("abc") and not r.permissions & pymupdf.PDF_PERM_COPY
    assert pdf_tools.is_owner_password(p, "dueno") and not pdf_tools.is_owner_password(p, "abc")


def test_comprimir_reduce_imagenes(tmp_path):
    big = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 2400, 3200), False)
    for y in range(0, 3200, 40):                       # contenido variado (si no, comprime a casi nada)
        big.set_rect(pymupdf.IRect(0, y, 2400, y + 20), ((y * 7) % 255, 90, 160))
    img = str(tmp_path / "big.png"); big.save(img)
    d = pdf_tools.images_to_pdf([img])
    antes = len(d.tobytes())
    pdf_tools.compress(d, "max")
    despues = len(d.tobytes(**pdf_tools.SAVE_OPTS))
    assert despues < antes / 2


def test_imagenes_a_pdf_y_pdf_a_imagenes(tmp_path):
    d = pdf_tools.images_to_pdf([_png(tmp_path / "a.png"), _png(tmp_path / "b.png", 300, 500)])
    assert len(d) == 2 and d[0].rect.width > d[0].rect.height and d[1].rect.width < d[1].rect.height
    files = pdf_tools.export_images(d, [0, 1], str(tmp_path), "doc", "jpg", 72)
    assert [f.endswith(("doc_p1.jpg", "doc_p2.jpg")) for f in files] == [True, True]


def test_formulario(tmp_path):
    d = pymupdf.open(); page = d.new_page()
    for kind, name, rect in ((pymupdf.PDF_WIDGET_TYPE_TEXT, "nombre", (50, 50, 250, 70)),
                             (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, "acepto", (50, 90, 64, 104))):
        w = pymupdf.Widget(); w.field_type = kind; w.field_name = name; w.rect = pymupdf.Rect(rect)
        page.add_widget(w)
    f = {x["name"]: x for x in pdf_tools.form_fields(d)}
    assert f["nombre"]["kind"] == "text" and f["acepto"]["value"] is False
    pdf_tools.set_field(d, 0, f["nombre"]["xref"], "Fernando")
    pdf_tools.set_field(d, 0, f["acepto"]["xref"], True)
    p = str(tmp_path / "f.pdf"); d.save(p)
    f2 = {x["name"]: x for x in pdf_tools.form_fields(pymupdf.open(p))}
    assert f2["nombre"]["value"] == "Fernando" and f2["acepto"]["value"] is True


def test_tachado_definitivo_y_limpieza(tmp_path):
    d = pymupdf.open(); p = d.new_page()
    p.insert_text((72, 100), "Cedula 1712345678 secreta"); p.insert_text((72, 140), "texto publico")
    d.set_metadata({"author": "Fernando", "title": "Privado"})
    r = p.search_for("1712345678")[0]
    assert pdf_tools.redact(d, {0: [r]}) == 1
    txt = d[0].get_text()
    assert "1712345678" not in txt and "publico" in txt          # el dato desaparece de verdad
    pdf_tools.scrub(d)
    assert not (d.metadata.get("author") or d.metadata.get("title"))


def test_marca_de_agua_y_numeracion():
    d = pymupdf.open()
    for _ in range(3): d.new_page()
    d[1].set_rotation(90)
    pdf_tools.watermark(d, [0, 1, 2], "CONFIDENCIAL")
    pdf_tools.number_pages(d, [0, 1, 2], "Pág. {n} de {total}", "br")
    pdf_tools.number_pages(d, [0, 1, 2], "EXP-{n:05d}", "tl", start=7)
    for i in range(3):
        t = d[i].get_text()
        assert "CONFIDENCIAL" in t and f"Pág. {i + 1} de 3" in t and f"EXP-{7 + i:05d}" in t
