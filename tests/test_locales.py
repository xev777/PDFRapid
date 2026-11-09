# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
import json


def test_idiomas_con_las_mismas_claves():
    es = json.load(open("locales/es.json", encoding="utf-8"))
    en = json.load(open("locales/eng.json", encoding="utf-8"))
    assert set(es) == set(en)
