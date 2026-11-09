# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Sistema de traducción multi-idioma"""
import json
import os
from core.portable import qsettings
from core.logger import log

class Translator:
    _inst = None
    
    def __new__(cls):
        if not cls._inst:
            cls._inst = super().__new__(cls)
        return cls._inst
    
    def __init__(self):
        self._s = qsettings("Settings")
        self.current_lang = self._s.value("language", "es")
        self.translations = {}
        self.locales_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales")
        self.load_language(self.current_lang)
    
    def load_language(self, lang_code):
        self.current_lang = lang_code
        self.translations = {}
        lang_file = os.path.join(self.locales_dir, f"{lang_code}.json")
        
        if os.path.exists(lang_file):
            try:
                with open(lang_file, 'r', encoding='utf-8') as f:
                    self.translations = json.load(f)
                log.info(f"Idioma cargado: {lang_code}")
            except Exception as e:
                log.error(f"Error cargando {lang_file}: {e}")
        else:
            log.warning(f"Archivo de idioma no encontrado: {lang_file}. Usando claves EN como fallback.")
        
        self._s.setValue("language", lang_code)
    
    def tr(self, key, default=None):
        return self.translations.get(key, default or key)
    
    def get_available_languages(self):
        langs = {"en": "English"}
        if os.path.exists(self.locales_dir):
            for file in os.listdir(self.locales_dir):
                if file.endswith(".json"):
                    code = file[:-5]
                    try:
                        with open(os.path.join(self.locales_dir, file), 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            langs[code] = data.get("_name_", code.upper())
                    except Exception:
                        langs[code] = code.upper()
        return langs

# Instancia global
translator = Translator()