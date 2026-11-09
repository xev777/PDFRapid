# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Sistema de logging de la aplicación"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def _make_logger():
    """Crea y configura el logger de Pdfgm (INFO, archivo rotativo de 1 MB × 3)."""
    from core.portable import PORTABLE, data_dir
    log_path = os.path.join(data_dir() if PORTABLE else os.path.expanduser("~"), "pdfrapid.log")
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(module)s.%(funcName)s: %(message)s")
    logger = logging.getLogger("Pdfgm")
    logger.setLevel(logging.DEBUG if os.environ.get("PDFGM_DEBUG") else logging.INFO)
    logger.propagate = False         # pdf2docx configura el logger raíz: evitar mensajes duplicados
    if not logger.handlers:
        handlers = [RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")]
        if sys.stdout:
            handlers.append(logging.StreamHandler(sys.stdout))
        for h in handlers:
            h.setFormatter(fmt)
            logger.addHandler(h)
    return logger


# Instancia global del logger
log = _make_logger()
