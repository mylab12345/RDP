"""Look & feel: QSS themes, color palette, icon loading."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication

RESOURCES = Path(__file__).parent.parent / "resources"
ICONS = RESOURCES / "icons"

PALETTE = {
    "dark": {
        "bg": "#11151c",
        "bg2": "#171c26",
        "panel": "#1b2130",
        "panel2": "#222a3b",
        "border": "#2c3547",
        "fg": "#d8dee9",
        "fg_dim": "#7b8698",
        "accent": "#88c0d0",
        "accent_text": "#0d1220",
        "good": "#a3be8c",
        "warn": "#ebcb8b",
        "bad": "#bf616a",
        "info": "#81a1c1",
        "term_bg": "#11151c",
        "term_fg": "#d8dee9",
        "sel": "#2f4b67",
    },
    "light": {
        "bg": "#f5f6f8",
        "bg2": "#ffffff",
        "panel": "#eceff4",
        "panel2": "#e2e7ee",
        "border": "#c9d1dc",
        "fg": "#1b1f24",
        "fg_dim": "#5f6b7c",
        "accent": "#2563a8",
        "accent_text": "#ffffff",
        "good": "#357200",
        "warn": "#8f6700",
        "bad": "#a31515",
        "info": "#0b5cc4",
        "term_bg": "#ffffff",
        "term_fg": "#1b1f24",
        "sel": "#b3d4fc",
    },
}

_icon_cache: dict[str, QIcon] = {}

GLYPH_FALLBACK = {
    "terminal": ">_",
    "windows": "▣",
    "console": "▢",
    "server": "▤",
    "key": "⚿",
    "plug": "⇄",
    "folder": "▣",
    "gear": "⚙",
    "transfer": "⇩",
    "shield": "⛨",
    "plus": "＋",
    "connect": "↻",
    "search": "⌕",
    "edit": "✎",
    "trash": "🗑",
    "logo": "◐",
}


def icon(name: str) -> QIcon:
    """Load an SVG icon; falls back to a text glyph when SVG is unavailable."""
    if name in _icon_cache:
        return _icon_cache[name]
    path = ICONS / f"{name}.svg"
    ic = QIcon(str(path))
    if ic.isNull() or len(ic.availableSizes()) == 0:
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QLabel

        glyph = GLYPH_FALLBACK.get(name, "•")
        label = QLabel(glyph)
        pix = QPixmap(24, 24)
        pix.fill(QColor(0, 0, 0, 0))
        label.render(pix)
        ic = QIcon(pix)
    _icon_cache[name] = ic
    return ic


def palette(theme: str = "dark") -> dict[str, str]:
    return PALETTE.get(theme, PALETTE["dark"])


_QSS = """
* {{ font-family: "Segoe UI", "Inter", "DejaVu Sans", sans-serif; }}
QMainWindow, QDialog {{ background: {bg}; }}
QWidget {{ color: {fg}; font-size: 13px; }}
QToolTip {{ background: {panel2}; color: {fg}; border: 1px solid {border}; padding: 4px; }}

QMenuBar {{ background: {bg2}; border-bottom: 1px solid {border}; }}
QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {panel2}; }}
QMenu {{ background: {panel}; border: 1px solid {border}; padding: 6px; }}
QMenu::item {{ padding: 5px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background: {panel2}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 5px 8px; }}

QToolBar {{ background: {bg2}; border: none; border-bottom: 1px solid {border}; spacing: 4px; padding: 4px 8px; }}
QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 6px 10px; color: {fg}; }}
QToolButton:hover {{ background: {panel2}; }}
QToolButton:pressed {{ background: {border}; }}

QPushButton {{ background: {panel2}; border: 1px solid {border}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:pressed {{ background: {border}; }}
QPushButton:disabled {{ color: {fg_dim}; }}
QPushButton#primary {{ background: {accent}; color: {accent_text}; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ opacity: 0.9; }}

QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QComboBox QAbstractItemView {{
    background: {bg2}; border: 1px solid {border}; border-radius: 6px; padding: 5px 8px; selection-background-color: {accent}; selection-color: {accent_text};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 6px solid {fg_dim}; margin-right: 6px; }}
QComboBox QAbstractItemView {{ background: {panel}; border: 1px solid {border}; }}

QTabWidget::pane {{ border: 1px solid {border}; border-radius: 4px; top: -1px; }}
QTabBar::tab {{ background: {bg2}; color: {fg_dim}; padding: 7px 14px; border: 1px solid {border}; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {panel}; color: {fg}; border-bottom: 2px solid {accent}; }}
QTabBar::tab:hover:!selected {{ background: {panel2}; }}

QTreeView, QListView, QTableView {{ background: {bg2}; alternate-background-color: {bg}; border: 1px solid {border}; border-radius: 6px; }}
QTreeView::item, QListView::item, QTableView::item {{ padding: 5px 4px; border-radius: 4px; }}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{ background: {sel}; color: {fg}; }}
QHeaderView::section {{ background: {panel}; border: none; border-bottom: 1px solid {border}; padding: 6px; font-weight: 600; }}

QSplitter::handle {{ background: {border}; width: 2px; height: 2px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {panel2}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {border}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {panel2}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QStatusBar {{ background: {bg2}; border-top: 1px solid {border}; color: {fg_dim}; }}
QFrame#hairline {{ color: {border}; }}
QLabel#muted {{ color: {fg_dim}; }}
QLabel#h1 {{ font-size: 17px; font-weight: 700; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}

QProgressBar {{ background: {panel}; border: 1px solid {border}; border-radius: 5px; text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}

QGroupBox {{ border: 1px solid {border}; border-radius: 6px; margin-top: 10px; padding-top: 14px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {fg_dim}; }}
"""


def apply_theme(app: QApplication, theme: str = "dark") -> None:
    pal = palette(theme)
    app.setStyleSheet(_QSS.format(**pal))
    # QWidget palette (dialogs, tooltips, selection colors)
    from PySide6.QtGui import QPalette

    qpal = QPalette()
    qpal.setColor(QPalette.ColorRole.Window, QColor(pal["bg"]))
    qpal.setColor(QPalette.ColorRole.Base, QColor(pal["bg2"]))
    qpal.setColor(QPalette.ColorRole.AlternateBase, QColor(pal["bg"]))
    qpal.setColor(QPalette.ColorRole.Text, QColor(pal["fg"]))
    qpal.setColor(QPalette.ColorRole.WindowText, QColor(pal["fg"]))
    qpal.setColor(QPalette.ColorRole.Button, QColor(pal["panel"]))
    qpal.setColor(QPalette.ColorRole.ButtonText, QColor(pal["fg"]))
    qpal.setColor(QPalette.ColorRole.Highlight, QColor(pal["accent"]))
    qpal.setColor(QPalette.ColorRole.HighlightedText, QColor(pal["accent_text"]))
    qpal.setColor(QPalette.ColorRole.ToolTipBase, QColor(pal["panel2"]))
    qpal.setColor(QPalette.ColorRole.ToolTipText, QColor(pal["fg"]))
    qpal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(pal["fg_dim"]))
    app.setPalette(qpal)
