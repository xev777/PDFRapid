# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Estilos y paleta de colores de la aplicación"""

import os
from core.portable import data_dir, qsettings

# ══════════════════════════════════════════════════════════
# PALETAS (el tema se elige en Vista → Tema y se aplica al iniciar)
# ══════════════════════════════════════════════════════════
LIGHT = {
    "bg":         "#f7f8fa",
    "panel":      "#ffffff",
    "sidebar":    "#f3f4f6",
    "accent":     "#1565d8",
    "accent2":    "#0f52b5",
    "pressed":    "#0b3f8c",
    "danger":     "#d13438",
    "danger2":    "#b3282c",
    "success":    "#1e8e3e",
    "warn":       "#e8a33d",
    "text":       "#1f2328",
    "muted":      "#6b7280",
    "border":     "#dfe3e8",
    "hover":      "#eef2f7",
    "selected":   "#1565d8",
    "white":      "#ffffff",     # fondo de campos de texto y listas
    "canvas":     "#eceef1",     # fondo detrás de las páginas
    "group_hdr":  "#e7e9ec",
    "dialog_bg":  "#ffffff",
    "dialog_text":"#1f2328",
    "menu_bg":    "#ffffff",
    "menu_text":  "#1f2328",
    "drop_ok":    "#1e8e3e",
    "disabled_bg":  "#e4e6ea",
    "disabled_text":"#9aa0a8",
    "accent_soft":"#e8f0fe",
    "shadow":     "rgba(15,23,42,0.08)",
    "icon":       "#3c4149",
    "icon_active":"#ffffff",
    "icon_muted": "#8a90a0",
}

# Gris suave: oscuro pero sin negro, contraste moderado para no cansar la vista.
GRAY = {
    "bg":         "#3b3e44",
    "panel":      "#44474e",
    "sidebar":    "#40434a",
    "accent":     "#5a95e6",
    "accent2":    "#4a84d6",
    "pressed":    "#3d72c0",
    "danger":     "#d9686b",
    "danger2":    "#e57a7d",
    "success":    "#5fae6e",
    "warn":       "#d9a64e",
    "text":       "#e3e5e8",
    "muted":      "#a7acb4",
    "border":     "#565a62",
    "hover":      "#4c5058",
    "selected":   "#5a95e6",
    "white":      "#35383d",
    "canvas":     "#33363b",
    "group_hdr":  "#4a4d54",
    "dialog_bg":  "#44474e",
    "dialog_text":"#e3e5e8",
    "menu_bg":    "#44474e",
    "menu_text":  "#e3e5e8",
    "drop_ok":    "#5fae6e",
    "disabled_bg":  "#4a4d54",
    "disabled_text":"#7c8189",
    "accent_soft":"#3c4a5f",
    "shadow":     "rgba(0,0,0,0.25)",
    "icon":       "#d4d7dc",
    "icon_active":"#ffffff",
    "icon_muted": "#8d929a",
}

THEMES = {"light": ("Claro", LIGHT), "gray": ("Gris suave", GRAY)}


def current_theme() -> str:
    t = os.environ.get("PDFGM_THEME") or qsettings("PDFManager").value("theme", "light")
    return t if t in THEMES else "light"


C = dict(THEMES[current_theme()][1])

# ══════════════════════════════════════════════════════════
# HOJA DE ESTILOS GLOBAL
# ══════════════════════════════════════════════════════════
def _check_svg() -> str:
    """Marca ✓ para las casillas (QSS solo acepta imágenes desde archivo)."""
    d = data_dir()
    p = os.path.join(d, "check.svg")
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7" '
                    'fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return p.replace("\\", "/")


_CHECK = _check_svg()


def _arrow_svg(name: str, path: str) -> str:
    """Flechas de los campos numéricos y listas, en el color del tema (un archivo por tema)."""
    d = data_dir()
    p = os.path.join(d, f"{name}_{C['muted'].lstrip('#')}.svg")
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="{path}" fill="none" '
                    f'stroke="{C["muted"]}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return p.replace("\\", "/")


_UP, _DOWN = _arrow_svg("up", "M2 6.5l3-3 3 3"), _arrow_svg("down", "M2 3.5l3 3 3-3")
_ARROWS = f"""
QSpinBox, QDoubleSpinBox {{ padding-right:22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin:border; subcontrol-position:top right; width:20px;
    border:none; border-left:1px solid {C['border']}; border-top-right-radius:6px; background:transparent; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin:border; subcontrol-position:bottom right; width:20px;
    border:none; border-left:1px solid {C['border']}; border-bottom-right-radius:6px; background:transparent; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background:{C['hover']}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image:url({_UP}); width:10px; height:10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image:url({_DOWN}); width:10px; height:10px; }}
QSpinBox[buttonSymbols="2"] {{ padding-right:4px; }}
QComboBox::drop-down, QFontComboBox::drop-down {{ subcontrol-origin:padding; subcontrol-position:center right; width:22px; border:none; }}
QComboBox::down-arrow, QFontComboBox::down-arrow {{ image:url({_DOWN}); width:10px; height:10px; }}
"""

# ══════════════════════════════════════════════════════════
# DIÁLOGOS: tarjetas suaves, botón principal en color y el resto discretos
# ══════════════════════════════════════════════════════════
_DLG = f"""
QDialog {{ background-color:{C['dialog_bg']}; color:{C['dialog_text']}; }}
QDialog QWidget {{ color:{C['dialog_text']}; }}
QDialog QLabel {{ background:transparent; color:{C['dialog_text']}; }}
QDialog QLabel#muted {{ color:{C['muted']}; }}
QDialog QLabel#caption {{ color:{C['muted']}; font-size:10px; font-weight:700; letter-spacing:1px; }}
QDialog QFrame#sep {{ color:{C['border']}; max-width:1px; margin:4px 4px; }}
QDialog QGroupBox {{ background-color:{C['sidebar']}; border:1px solid {C['border']}; border-radius:10px;
                    margin-top:20px; padding:14px 12px 10px 12px; color:{C['muted']}; font-size:10px; font-weight:700; }}
QDialog QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top left; left:2px; padding:0 4px 4px 4px;
                           color:{C['muted']}; letter-spacing:1px; background:transparent; }}
QDialog QGroupBox QLabel, QDialog QGroupBox QCheckBox, QDialog QGroupBox QRadioButton {{ font-size:12px; font-weight:400; color:{C['dialog_text']}; }}
QDialog QPushButton {{ background-color:{C['panel']}; color:{C['text']}; border:1px solid {C['border']}; border-radius:6px;
                      padding:6px 16px; font-weight:500; min-height:22px; }}
QDialog QPushButton:hover {{ background-color:{C['hover']}; border-color:{C['accent']}; }}
QDialog QPushButton:default {{ background-color:{C['accent']}; border-color:{C['accent']}; color:white; font-weight:600; }}
QDialog QPushButton:default:hover {{ background-color:{C['accent2']}; border-color:{C['accent2']}; }}
QDialog QPushButton:disabled {{ background-color:transparent; border-color:{C['border']}; color:{C['disabled_text']}; }}
QDialog QPushButton#flat {{ background-color:transparent; color:{C['muted']}; }}
QDialog QPushButton#icon {{ background-color:transparent; border:1px solid transparent; padding:0; min-height:0; min-width:0; }}
QDialog QPushButton#icon:hover {{ background-color:{C['hover']}; border-color:{C['border']}; }}
QDialog QLineEdit, QDialog QTextEdit, QDialog QPlainTextEdit, QDialog QSpinBox, QDialog QDoubleSpinBox,
QDialog QComboBox, QDialog QFontComboBox {{ background-color:{C['white']}; color:{C['text']}; border:1px solid {C['border']};
                                           border-radius:6px; padding:5px 8px; min-height:20px;
                                           selection-background-color:{C['accent']}; selection-color:white; }}
QDialog QLineEdit:focus, QDialog QTextEdit:focus, QDialog QPlainTextEdit:focus, QDialog QSpinBox:focus,
QDialog QDoubleSpinBox:focus, QDialog QComboBox:focus, QDialog QFontComboBox:focus {{ border-color:{C['accent']}; }}
QDialog QTextEdit#content {{ font-size:13px; padding:8px; }}
{_ARROWS.replace(chr(10) + "Q", chr(10) + "QDialog Q")}
QDialog QComboBox QAbstractItemView {{ background-color:{C['white']}; color:{C['text']}; border:1px solid {C['border']};
                                      selection-background-color:{C['accent']}; outline:none; }}
QDialog QCheckBox, QDialog QRadioButton {{ background:transparent; color:{C['text']}; spacing:8px; }}
QDialog QCheckBox::indicator {{ width:16px; height:16px; border:1px solid {C['border']}; border-radius:4px; background-color:{C['white']}; }}
QDialog QCheckBox::indicator:checked {{ background-color:{C['accent']}; border-color:{C['accent']}; image:url({_CHECK}); }}
QDialog QListWidget, QDialog QTreeWidget {{ background-color:{C['white']}; color:{C['text']}; border:1px solid {C['border']}; border-radius:8px; }}
QDialog QTabWidget::pane {{ border:1px solid {C['border']}; border-radius:8px; background-color:{C['panel']}; top:-1px; }}
QDialog QTabBar::tab {{ background:transparent; color:{C['muted']}; border:none; padding:7px 16px; margin-right:2px; }}
QDialog QTabBar::tab:selected {{ color:{C['text']}; border-bottom:2px solid {C['accent']}; }}
QDialog QTabBar::tab:hover:!selected {{ color:{C['text']}; }}
QDialog QScrollArea {{ background:transparent; border:none; }}
"""

SS = f"""
* {{ font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif; font-size:12px; }}
QMainWindow,QWidget {{ background:{C['bg']}; color:{C['text']}; }}
QToolTip {{ background-color:{C['panel']}; color:{C['text']}; border:1px solid {C['border']}; padding:4px 8px; }}

/* ── Barra de menú ── */
QMenuBar {{ background:{C['panel']}; color:{C['text']}; border-bottom:1px solid {C['border']}; padding:2px 4px; }}
QMenuBar::item {{ padding:4px 10px; border-radius:4px; color:{C['text']}; }}
QMenuBar::item:selected {{ background-color:{C['hover']}; color:{C['text']}; }}
QMenuBar::item:pressed {{ background-color:{C['accent']}; color:white; }}

/* ── Menús contextuales y desplegables ──
   Las dos reglas (QMenu y QMenu QMenu) cubren menú raíz y submenús.
   IMPORTANTE: QMenu es una ventana emergente nativa — si se le da border-radius,
   Qt activa fondo translúcido para poder redondear las esquinas, y en Windows 11
   esa translucidez se compone contra el tema oscuro del sistema, mostrando el
   menú en negro sin importar el color del QSS. Por eso NO se usa border-radius
   en QMenu (solo en QMenu::item, que no es una ventana). */
QMenu {{
    background-color:{C['menu_bg']};
    color:{C['menu_text']};
    border:1px solid {C['border']};
    padding:6px 0px;
}}
QMenu::item {{
    background-color:transparent;
    color:{C['menu_text']};
    padding:7px 32px 7px 12px;
    margin:2px 6px;
    border-radius:4px;
}}
QMenu::item:selected {{
    background-color:{C['accent']};
    color:#ffffff;
}}
QMenu::item:disabled {{
    color:{C['muted']};
    background-color:transparent;
}}
QMenu::separator {{
    height:1px;
    background:{C['border']};
    margin:4px 12px;
}}
QMenu::icon {{
    padding-left:6px;
}}
/* Submenús (mismo estilo) */
QMenu QMenu {{
    background-color:{C['menu_bg']};
    color:{C['menu_text']};
    border:1px solid {C['border']};
}}

/* ── Toolbar ── */
QToolBar {{ background:{C['panel']}; border-bottom:1px solid {C['border']}; spacing:2px; padding:3px 6px; }}
QToolBar::separator {{ background:{C['border']}; width:1px; margin:4px 4px; }}
QToolBar QToolButton {{ background-color:transparent; border-style:solid; border-width:1px; border-color:transparent; color:{C['text']}; border-radius:4px; padding:4px 8px; font-size:12px; }}
QToolBar QToolButton:hover {{ background-color:{C['hover']}; border-color:{C['border']}; }}
QToolBar QToolButton:pressed, QToolBar QToolButton:checked {{ background-color:{C['accent']}; border-color:{C['accent']}; color:white; }}

/* ── Botones ──
   NOTA: se usa background-color (no el shorthand background) y un border-style
   sólido explícito en cada estado — con Fusion, un QPushButton que pasa de un
   estado sin relleno (transparent) a uno con relleno vía QSS puede quedar "hueco"
   (solo el borde se pinta) si no se declara border-style:solid explícitamente. */
QPushButton {{ background-color:{C['accent']}; border-style:solid; border-width:1px; border-color:{C['accent']}; border-radius:4px; color:white; padding:5px 12px; font-weight:600; font-size:12px; min-height:28px; }}
QPushButton:hover {{ background-color:{C['accent2']}; border-color:{C['accent2']}; }}
QPushButton:pressed {{ background-color:{C['pressed']}; border-color:{C['pressed']}; }}
QPushButton:disabled {{ background-color:{C['disabled_bg']}; border-color:{C['disabled_bg']}; color:{C['disabled_text']}; }}
QPushButton#flat {{ background-color:transparent; border-style:solid; border-width:1px; border-color:{C['border']}; color:{C['muted']}; }}
QPushButton#flat:hover {{ background-color:{C['hover']}; border-color:{C['border']}; color:{C['text']}; }}
QPushButton#flat:checked {{ background-color:{C['accent']}; border-color:{C['accent']}; color:white; }}
QPushButton#danger {{ background-color:{C['danger']}; border-style:solid; border-width:1px; border-color:{C['danger']}; color:white; }}
QPushButton#danger:hover {{ background-color:{C['danger2']}; border-color:{C['danger2']}; }}
QPushButton#warn {{ background-color:{C['warn']}; border-style:solid; border-width:1px; border-color:{C['warn']}; color:#111; }}
QPushButton#color_swatch {{ min-width:64px; min-height:26px; padding:2px 4px; font-size:10px; }}
QPushButton#tool {{ background-color:{C['sidebar']}; border-style:solid; border-width:1px; border-color:{C['sidebar']}; border-radius:6px; color:{C['text']}; font-size:11px; min-height:32px; padding:6px 10px; text-align:left; icon-size:18px 18px; }}
QPushButton#tool:hover {{ background-color:{C['hover']}; border-color:{C['border']}; }}
QPushButton#tool:checked {{ background-color:{C['accent']}; border-color:{C['accent']}; color:white; font-weight:600; }}
QLabel#tool_group_hdr {{ color:{C['muted']}; font-size:10px; font-weight:700; letter-spacing:1px; padding:8px 6px 2px 6px; }}

/* ── Scroll ── */
QScrollArea {{ background:{C['bg']}; border:none; }}
QScrollBar:vertical {{ background:{C['panel']}; width:10px; border-radius:5px; margin:0; }}
QScrollBar::handle:vertical {{ background:{C['border']}; border-radius:5px; min-height:24px; }}
QScrollBar::handle:vertical:hover {{ background:{C['accent']}; }}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar:horizontal {{ background:{C['panel']}; height:10px; border-radius:5px; margin:0; }}
QScrollBar::handle:horizontal {{ background:{C['border']}; border-radius:5px; min-width:24px; }}
QScrollBar::handle:horizontal:hover {{ background:{C['accent']}; }}
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal {{ width:0; }}

/* ── Inputs ── */
QLineEdit,QTextEdit,QPlainTextEdit {{ background:{C['white']}; color:{C['text']}; border:1px solid {C['border']}; border-radius:4px; padding:5px 8px; selection-background-color:{C['accent']}; }}
QLineEdit:focus,QTextEdit:focus {{ border-color:{C['accent']}; }}
QSpinBox,QDoubleSpinBox {{ background:{C['white']}; color:{C['text']}; border:1px solid {C['border']}; border-radius:4px; padding:2px 4px; }}
QSpinBox::up-button,QDoubleSpinBox::up-button {{ subcontrol-origin:border; subcontrol-position:top right; width:16px; border:1px solid {C['border']}; border-radius:2px; background:{C['panel']}; }}
QSpinBox::down-button,QDoubleSpinBox::down-button {{ subcontrol-origin:border; subcontrol-position:bottom right; width:16px; border:1px solid {C['border']}; border-radius:2px; background:{C['panel']}; }}
QSpinBox::up-button:hover,QDoubleSpinBox::up-button:hover {{ background:{C['hover']}; }}
QSpinBox::down-button:hover,QDoubleSpinBox::down-button:hover {{ background:{C['hover']}; }}
QComboBox {{ background:{C['white']}; color:{C['text']}; border:1px solid {C['border']}; border-radius:4px; padding:4px 8px; }}
QComboBox::drop-down {{ border:none; width:20px; }}
QComboBox QAbstractItemView {{ background:{C['white']}; color:{C['text']}; border:1px solid {C['border']}; selection-background-color:{C['accent']}; outline:none; }}
QFontComboBox {{ background:{C['white']}; color:{C['text']}; border:1px solid {C['border']}; border-radius:4px; padding:4px 6px; min-width:120px; }}

/* ── Checkbox ── */
QCheckBox {{ color:{C['text']}; spacing:6px; }}
QCheckBox::indicator {{ width:16px; height:16px; border:2px solid {C['border']}; border-radius:3px; background:{C['white']}; }}
QCheckBox::indicator:checked {{ background:{C['accent']}; border-color:{C['accent']}; }}

/* ── GroupBox ── */
QGroupBox {{ color:{C['text']}; border:1px solid {C['border']}; border-radius:6px; margin-top:12px; padding-top:10px; font-size:11px; font-weight:700; }}
QGroupBox::title {{ subcontrol-origin:margin; left:10px; padding:0 6px; }}

/* ── Tabs ── */
QTabWidget::pane {{ border:1px solid {C['border']}; border-radius:6px; background:{C['panel']}; }}
QTabBar::tab {{ background:{C['sidebar']}; color:{C['muted']}; border:1px solid {C['border']}; border-bottom:none; border-radius:5px 5px 0 0; padding:6px 14px; margin-right:2px; }}
QTabBar::tab:selected {{ background:{C['panel']}; color:{C['text']}; border-bottom:2px solid {C['accent']}; }}
QTabBar::tab:hover:!selected {{ background:{C['hover']}; color:{C['text']}; }}

/* ── Listas ── */
QListWidget {{ background:{C['white']}; border:1px solid {C['border']}; border-radius:6px; color:{C['text']}; outline:none; }}
QListWidget::item {{ padding:5px 8px; border-radius:4px; margin:1px; }}
QListWidget::item:selected {{ background:{C['accent']}; color:white; }}
QListWidget::item:hover {{ background:{C['hover']}; }}
QTreeWidget {{ background:{C['white']}; border:1px solid {C['border']}; color:{C['text']}; outline:none; }}
QTreeWidget::item {{ padding:3px 4px; border-radius:3px; }}
QTreeWidget::item:selected {{ background:{C['accent']}; color:white; }}
QTreeWidget::item:hover {{ background:{C['hover']}; }}
QTreeWidget::branch {{ background:{C['white']}; }}

/* ── StatusBar ── */
QStatusBar {{ background:{C['panel']}; color:{C['muted']}; border-top:1px solid {C['border']}; font-size:11px; }}

/* ── Diálogos — colores explícitos para todos los widgets internos ── */
{_DLG}
{_ARROWS}

/* ── Labels y GroupBox globales ── */
QLabel {{ color:{C['text']}; background:transparent; }}
QGroupBox QLabel {{ color:{C['text']}; }}

/* ── Dock ── */
QDockWidget {{ color:{C['text']}; }}
QDockWidget::title {{ background:{C['sidebar']}; padding:6px 10px; border-bottom:1px solid {C['border']}; font-weight:600; }}

/* ── Splitter ── */
QSplitter::handle:horizontal {{ background:{C['border']}; width:2px; }}
QSplitter::handle:vertical {{ background:{C['border']}; height:2px; }}

/* ── Widgets con objectName específico ── */
QTextEdit#inline {{ background:#ffffff; color:#111111; border:2px solid {C['accent']}; border-radius:3px; padding:3px; }}
QFrame#search_bar {{ background:{C['panel']}; border:1px solid {C['border']}; border-radius:6px; padding:4px; }}
QFrame#panel_frame {{ background:{C['panel']}; border:1px solid {C['border']}; border-radius:8px; }}
QLabel#panel_title {{ color:{C['accent']}; font-size:12px; font-weight:700; padding:4px 0; }}
QLabel#page_count {{ color:{C['muted']}; font-size:11px; }}
QPushButton#op, QPushButton#op_danger {{ background-color:{C['panel']}; border:1px solid {C['border']}; border-radius:4px; color:{C['text']}; font-weight:500; padding:4px 10px; min-height:26px; }}
QPushButton#op:hover {{ background-color:{C['hover']}; border-color:{C['accent']}; }}
QPushButton#op_danger {{ color:{C['danger']}; }}
QPushButton#op_danger:hover {{ background-color:{C['danger']}; border-color:{C['danger']}; color:white; }}
QPushButton#op:disabled, QPushButton#op_danger:disabled {{ background-color:transparent; border-color:{C['border']}; color:{C['disabled_text']}; }}
QToolButton#op_more {{ background-color:{C['panel']}; border:1px solid {C['border']}; border-radius:4px; color:{C['text']}; padding:3px 8px; min-height:22px; }}
QToolButton#op_more:hover {{ background-color:{C['hover']}; border-color:{C['accent']}; }}
QToolButton#op_more::menu-indicator {{ image:none; }}
QFrame#ops_panel {{ background:{C['panel']}; border:1px solid {C['border']}; border-radius:8px; }}
QLabel#ops_title {{ color:{C['muted']}; font-size:10px; font-weight:700; letter-spacing:1px; padding-top:4px; }}
QLabel#ops_hint {{ color:{C['muted']}; font-size:10px; }}

/* ── Pantalla de bienvenida (sin PDF abierto) ── */
QFrame#empty_state {{ background:transparent; }}
QLabel#empty_state_title {{ color:{C['text']}; font-size:17px; font-weight:700; }}
QLabel#empty_state_sub {{ color:{C['muted']}; font-size:12px; }}
QPushButton#empty_state_cta {{ background-color:{C['accent']}; border-style:solid; border-width:1px; border-color:{C['accent']}; border-radius:4px; color:white; font-weight:600; min-width:170px; min-height:38px; font-size:13px; padding:6px 18px; }}
QPushButton#empty_state_cta:hover {{ background-color:{C['accent2']}; border-color:{C['accent2']}; }}
"""

# ══════════════════════════════════════════════════════════
# HOJA DE ESTILOS PARA QMenu — se aplica también EN CADA INSTANCIA
# (menu.setStyleSheet(MENU_SS)) además de heredarla de la app, porque en
# este entorno los QMenu (ventanas emergentes) a veces no heredan
# correctamente el stylesheet global y caen al tema oscuro nativo de
# Windows. Fijarla directamente en el widget es la única forma confiable.
# ══════════════════════════════════════════════════════════
MENU_SS = f"""
QMenu {{
    background-color:{C['menu_bg']};
    color:{C['menu_text']};
    border:1px solid {C['border']};
    padding:6px 0px;
}}
QMenu::item {{
    background-color:transparent;
    color:{C['menu_text']};
    padding:7px 32px 7px 12px;
    margin:2px 6px;
    border-radius:4px;
}}
QMenu::item:selected {{
    background-color:{C['accent']};
    color:#ffffff;
}}
QMenu::item:disabled {{
    color:{C['muted']};
    background-color:transparent;
}}
QMenu::separator {{
    height:1px;
    background-color:{C['border']};
    margin:4px 12px;
}}
QMenu::icon {{
    padding-left:6px;
}}
"""

# ══════════════════════════════════════════════════════════
# HOJA DE ESTILOS PARA QDialog — igual que MENU_SS: se aplica directamente
# en cada instancia (dlg.setStyleSheet(DIALOG_SS)) porque los diálogos nuevos
# (QDialog de nivel superior) no siempre heredan el stylesheet de la app de
# forma confiable en este entorno y caían con fondo negro nativo.
# ══════════════════════════════════════════════════════════
DIALOG_SS = _DLG
