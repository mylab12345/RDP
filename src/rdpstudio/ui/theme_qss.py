"""Global stylesheets (MobaXterm look), extracted verbatim from theme.py.

Format templates — ``apply_theme()`` in ``theme.py`` fills them.
"""

from __future__ import annotations

_QSS = """
/* ================= KB-Remote — MobaXterm look =================
   Flat light-gray Windows chrome, white work surfaces, 1 px borders,
   2–3 px radii, Windows-blue selection. Segoe UI 9 pt. */

* {{
    font-family: {ui_sans};
    outline: none;
}}
QMainWindow, QDialog {{
    background: {bg};
}}
QWidget {{
    color: {fg};
    font-size: 12px;
}}
QToolTip {{
    background: {bg2};
    color: {fg};
    border: 1px solid {border_strong};
    border-radius: 0px;
    padding: 4px 7px;
    font-size: 12px;
}}

/* ================= Menu bar — classic Windows ================= */
QMenuBar {{
    background: {bg};
    border-bottom: 1px solid {border};
    padding: 0px 2px;
    spacing: 0px;
    font-size: 12px;
    min-height: 22px;
}}
QMenuBar::item {{
    padding: 3px 8px;
    border-radius: 0px;
    color: {fg};
    margin: 0px;
}}
QMenuBar::item:selected {{
    background: {sel_hover};
    color: {fg};
    border: 1px solid {accent_subtle};
    padding: 2px 7px;
}}
QMenuBar::item:pressed {{
    background: {accent_subtle};
    color: {fg};
}}

QMenu {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 0px;
    padding: 2px 0px;
}}
QMenu::item {{
    padding: 5px 24px 5px 30px;
    border-radius: 0px;
    color: {fg};
    font-size: 12px;
    margin: 0px;
}}
QMenu::item:selected {{
    background: {accent_subtle};
    color: {fg};
}}
QMenu::item:selected:active {{
    background: {accent_subtle};
    color: {fg};
}}
QMenu::item:disabled {{
    color: {fg_muted};
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 3px 2px 3px 30px;
}}
QMenu::icon {{
    left: 6px;
}}
QMenu::indicator {{
    left: 7px;
    width: 13px;
    height: 13px;
    border-radius: 2px;
    border: 1px solid {border_strong};
    background: {bg2};
}}
QMenu::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: url({check_url});
}}
QMenu::right-arrow {{
    image: url({chev_right_url});
    width: 12px; height: 12px;
    right: 6px;
}}

/* ================= Toolbar — MobaXterm big buttons ================= */
QToolBar {{
    background: {bg};
    border: none;
    border-bottom: 1px solid {border};
    spacing: 1px;
    padding: 2px 4px;
    min-height: 34px;
}}
QToolBar#moxaToolbar {{
    spacing: 1px;
    padding: 3px 6px 2px 6px;
    min-height: 58px;
}}
QToolBar#moxaToolbar QToolButton {{
    padding: 3px 7px 2px 7px;
    min-width: 48px;
    min-height: 44px;
    font-size: 11px;
    font-weight: 400;
    border-radius: 2px;
    color: {fg};
}}
QToolBar::separator {{
    width: 1px;
    background: {border_strong};
    margin: 6px 4px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 3px 6px;
    color: {fg};
    font-weight: 400;
    font-size: 12px;
}}
QToolButton:hover {{
    background: {sel_hover};
    color: {fg};
    border-color: {accent_subtle};
}}
QToolButton:pressed {{
    background: {accent_subtle};
    border-color: {accent};
}}
QToolButton:checked {{
    background: {accent_subtle};
    color: {fg};
    border-color: {accent}99;
}}
QToolButton:focus {{
    border: 1px dotted {fg_dim};
}}
QToolButton:disabled {{
    color: {fg_muted};
}}
QToolButton::menu-indicator {{
    image: none;
}}

/* ================= Buttons — flat Windows push buttons ================= */
QPushButton {{
    background: {panel2};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 3px 14px;
    color: {fg};
    font-weight: 400;
    font-size: 12px;
    min-height: 17px;
    min-width: 56px;
}}
QPushButton:hover {{
    background: {sel_hover};
    border-color: {accent};
}}
QPushButton:pressed {{
    background: {accent_subtle};
    border-color: {accent_active};
}}
QPushButton:focus {{
    border: 1px solid {accent};
}}
QPushButton:default {{
    border: 1px solid {accent};
}}
QPushButton:disabled {{
    color: {fg_muted};
    background: {bg3};
    border-color: {border};
}}
QPushButton#primary, QPushButton#accent {{
    background: {accent};
    color: {accent_text};
    border: 1px solid {accent_active};
    font-weight: 400;
    border-radius: 2px;
}}
QPushButton#primary:hover, QPushButton#accent:hover {{
    background: {accent_hover};
    border-color: {accent};
}}
QPushButton#primary:pressed, QPushButton#accent:pressed {{
    background: {accent_active};
    border-color: {accent_active};
}}
QPushButton#primary:disabled, QPushButton#accent:disabled {{
    background: {bg3};
    color: {fg_muted};
    border-color: {border};
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {fg};
    border-radius: 2px;
    min-width: 0px;
}}
QPushButton#ghost:hover {{
    background: {sel_hover};
    border-color: {accent_subtle};
}}
QPushButton#ghost:pressed {{
    background: {accent_subtle};
}}
QPushButton#subtle {{
    background: {panel2};
    border: 1px solid {border_strong};
    color: {fg};
    border-radius: 2px;
    min-width: 0px;
}}
QPushButton#subtle:hover {{
    background: {sel_hover};
    border-color: {accent};
}}
QPushButton#danger {{
    background: {panel2};
    border: 1px solid {border_strong};
    color: {bad};
    border-radius: 2px;
    font-weight: 400;
}}
QPushButton#danger:hover {{
    background: {bad};
    border-color: {bad_active};
    color: {bad_text};
}}
QPushButton#danger:pressed {{
    background: {bad_active};
    border-color: {bad_active};
    color: {bad_text};
}}
QPushButton#danger:disabled {{
    color: {fg_muted};
    background: {bg3};
    border-color: {border};
}}

/* Quick connect — joined input + button group (toolbar) */
QWidget#quickConnect {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 2px;
}}
QWidget#quickConnect:hover {{
    border-color: {accent};
}}
QWidget#quickConnect QLineEdit {{
    background: transparent;
    border: none;
    padding: 3px 8px;
    font-size: 12px;
    color: {fg};
    min-height: 18px;
}}
QWidget#quickConnect QPushButton {{
    border: none;
    border-left: 1px solid {accent_active};
    border-radius: 0px;
    padding: 3px 10px;
    font-size: 12px;
    min-height: 18px;
    min-width: 0px;
}}

/* ================= Inputs — white sunken fields ================= */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 3px 6px;
    selection-background-color: {accent};
    selection-color: {accent_text};
    color: {fg};
    min-height: 18px;
    font-size: 12px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {accent};
    background: {bg2};
}}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{
    border-color: {accent};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background: {bg};
    color: {fg_muted};
    border-color: {border};
}}
QLineEdit#search {{
    border-radius: 2px;
    padding: 3px 6px 3px 6px;
    background: {bg2};
    border: 1px solid {border_strong};
    font-size: 12px;
}}
QLineEdit#search:focus {{
    border-color: {accent};
}}
QLineEdit#search:hover {{
    border-color: {accent};
}}
QLineEdit#invalid, QSpinBox#invalid, QComboBox#invalid {{
    border-color: {bad};
}}

QComboBox {{
    padding-right: 20px;
    background: {bg2};
    selection-background-color: {bg2};
    selection-color: {fg};
}}
QComboBox:on {{
    background: {bg2};
    border-color: {accent};
}}
QComboBox:editable {{
    background: {bg2};
}}
QComboBox:!editable, QComboBox::drop-down:editable,
QComboBox:!editable:on, QComboBox::drop-down:editable:on {{
    background: {bg2};
}}
QComboBox::drop-down {{
    border: none;
    border-left: 1px solid transparent;
    width: 20px;
    border-radius: 0px;
}}
QComboBox::drop-down:hover {{
    background: {sel_hover};
}}
QComboBox::down-arrow {{
    image: url({chev_down_dim_url});
    width: 12px; height: 12px;
}}
QComboBox QAbstractItemView {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 0px;
    padding: 0px;
    selection-background-color: {accent};
    selection-color: {accent_text};
    outline: none;
    font-family: {ui_sans};
}}
QComboBox QAbstractItemView::item {{
    padding: 3px 8px;
    border-radius: 0px;
    margin: 0px;
    min-height: 18px;
    border: none;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {sel_hover};
    color: {fg};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {accent};
    color: {accent_text};
    font-weight: 400;
}}

/* ================= Tabs — classic MobaXterm document tabs ================= */
QTabWidget::pane {{
    border: 1px solid {border_strong};
    border-top: 1px solid {border_strong};
    background: {bg2};
    border-radius: 0px;
    top: -1px;
}}
QTabBar {{
    background: transparent;
    qproperty-drawBase: 0;
    /* Transparent by default so the :focus recolor below causes no shift. */
    border: 1px solid transparent;
}}
QTabBar:focus {{
    border-color: {accent};
}}
QTabBar::tab {{
    background: {bg3};
    color: {fg_dim};
    padding: 4px 10px 4px 8px;
    border: 1px solid {border_strong};
    border-bottom: none;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
    margin-right: -1px;
    margin-top: 3px;
    font-weight: 400;
    font-size: 12px;
    min-height: 18px;
    max-width: 200px;
}}
QTabBar::tab:selected {{
    background: {bg2};
    color: {fg};
    border-color: {border_strong};
    border-top: 2px solid {accent};
    margin-top: 0px;
    padding-bottom: 5px;
}}
QTabBar::tab:hover:!selected {{
    background: {sel_hover};
    color: {fg};
}}
QTabBar::tab:first {{
    margin-left: 2px;
}}
QTabBar::close-button {{
    subcontrol-position: right;
    width: 14px; height: 14px;
    border-radius: 2px;
    margin-left: 4px;
    margin-right: 0px;
    background: transparent;
}}
QTabBar::close-button:hover {{
    background: {bad};
}}
QTabBar::close-button:pressed {{
    background: {bad_active};
}}
QTabBar QToolButton {{
    background: {bg3};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 1px;
    margin-top: 3px;
}}
QTabBar QToolButton:hover {{
    background: {sel_hover};
    border-color: {accent};
}}
QTabBar::scroller {{
    width: 32px;
}}

/* Vertical tab strip (sidebar left rail: Sessions / Tools / Macros) */
QTabBar#sideRail::tab {{
    background: {bg3};
    color: {fg_dim};
    border: 1px solid {border_strong};
    border-right: none;
    border-top-left-radius: 3px;
    border-bottom-left-radius: 3px;
    border-top-right-radius: 0px;
    border-bottom-right-radius: 0px;
    padding: 12px 4px 12px 3px;
    margin: 0px 0px 2px 3px;
    min-height: 60px;
    min-width: 14px;
    font-size: 11px;
}}
QTabBar#sideRail::tab:selected {{
    background: {bg2};
    color: {fg};
    border-left: 2px solid {accent};
    border-top: 1px solid {border_strong};
    margin-left: 0px;
    padding-right: 5px;
}}
QTabBar#sideRail::tab:hover:!selected {{
    background: {sel_hover};
    color: {fg};
}}

/* ================= Trees & Lists — Explorer style ================= */
QTreeView, QListView, QTableView {{
    background: {bg2};
    alternate-background-color: {bg};
    border: 1px solid {border_strong};
    border-radius: 0px;
    padding: 0px;
    outline: none;
    font-size: 12px;
    show-decoration-selected: 1;
}}
QTreeView::item, QListView::item, QTableView::item {{
    padding: 2px 4px;
    border-radius: 0px;
    margin: 0px;
    color: {fg};
    border: 1px solid transparent;
    min-height: 20px;
}}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{
    background: {sel_hover};
    border-color: {accent_subtle};
}}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background: {accent_subtle};
    color: {fg};
    border: 1px solid {accent}99;
    font-weight: 400;
}}
QTreeView::item:selected:active, QListView::item:selected:active {{
    background: {accent_subtle};
    color: {fg};
}}
QTreeView::item:selected:!active, QListView::item:selected:!active {{
    background: {bg3};
    border-color: {border_strong};
}}
/* Keyboard focus: recolor the existing 1 px frame — no geometry shift. */
QTreeView:focus, QListView:focus, QTableView:focus {{
    border: 1px solid {accent};
}}
QTreeView::branch {{
    background: transparent;
}}
QTreeView::branch:selected {{
    background: {accent_subtle};
}}
QTreeView::branch:hover {{
    background: {sel_hover};
}}
QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {{
    image: url({chev_right_url});
    border-image: none;
}}
QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {{
    image: url({chev_down_url});
    border-image: none;
}}
QHeaderView::section {{
    background: {bg2};
    border: none;
    border-bottom: 1px solid {border};
    border-right: 1px solid {border};
    padding: 4px 8px;
    font-weight: 400;
    color: {fg};
    font-size: 12px;
}}
QHeaderView::section:hover {{
    background: {sel_hover};
}}
QTableView QTableCornerButton::section {{
    background: {bg2};
    border: 1px solid {border};
}}
QTableView {{
    gridline-color: {border_subtle};
}}

/* ================= Splitter ================= */
QSplitter::handle {{
    background: {bg};
    width: 4px;
    height: 4px;
}}
QSplitter::handle:hover {{
    background: {accent_subtle};
}}
QSplitter::handle:pressed {{
    background: {accent};
}}
QSplitter::handle:vertical {{
    height: 4px;
}}

/* ================= Scrollbars — classic Windows, slim ================= */
QScrollBar:vertical {{
    background: {bg};
    width: 12px;
    margin: 0px;
    border-left: 1px solid {border_subtle};
}}
QScrollBar::handle:vertical {{
    background: {panel3};
    border-radius: 0px;
    min-height: 28px;
    margin: 1px 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {border_strong};
}}
QScrollBar::handle:vertical:pressed {{
    background: {fg_muted};
}}
QScrollBar:horizontal {{
    background: {bg};
    height: 12px;
    margin: 0px;
    border-top: 1px solid {border_subtle};
}}
QScrollBar::handle:horizontal {{
    background: {panel3};
    min-width: 28px;
    margin: 2px 1px;
    border-radius: 0px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {border_strong};
}}
QScrollBar::handle:horizontal:pressed {{
    background: {fg_muted};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0;
    background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ================= Status bar ================= */
QStatusBar {{
    background: {bg};
    border-top: 1px solid {border};
    color: {fg};
    padding: 0px 6px;
    font-size: 11.5px;
    min-height: 20px;
}}
QStatusBar::item {{
    border: none;
    border-right: 1px solid {border};
}}

/* ================= Groups — classic etched group boxes ================= */
QGroupBox {{
    border: 1px solid {border_strong};
    border-radius: 3px;
    margin-top: 10px;
    padding: 12px 10px 8px 10px;
    background: transparent;
    font-weight: 400;
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    top: 0px;
    padding: 0px 4px;
    background: {bg};
    color: {accent};
    border: none;
    font-size: 12px;
    font-weight: 400;
}}
QDialog QGroupBox::title {{
    background: {bg};
}}
QFormLayout QLabel {{
    padding-top: 0px;
}}

/* ================= Progress — Windows green bar ================= */
QProgressBar {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 0px;
    text-align: center;
    height: 14px;
    color: {fg};
    font-size: 10.5px;
}}
QProgressBar::chunk {{
    background: {good};
    border-radius: 0px;
    margin: 1px;
}}

/* ================= Checkboxes & Radios ================= */
QCheckBox, QRadioButton {{
    spacing: 6px;
    color: {fg};
    font-size: 12px;
    padding: 1px 0px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 13px; height: 13px;
    border-radius: 2px;
    border: 1px solid {fg_dim};
    background: {bg2};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: url({check_url});
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {accent};
    background: {sel_hover};
}}
QCheckBox::indicator:indeterminate {{
    background: {accent};
    border-color: {accent};
}}
QRadioButton::indicator {{
    border-radius: 7px;
}}
QRadioButton::indicator:checked {{
    background: {bg2};
    border-color: {accent};
    image: url({dot_url});
}}
QCheckBox::indicator:checked:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
}}
QRadioButton::indicator:checked:hover {{
    background: {bg2};
    border-color: {accent_hover};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    border-color: {border};
    background: {bg};
}}

/* ================= Labels ================= */
QLabel#muted {{
    color: {fg_dim};
}}
QLabel#h1 {{
    font-size: 15px;
    font-weight: 400;
    font-family: {ui_display};
    color: {accent};
}}
QLabel#h2 {{
    font-size: 12px;
    font-weight: 700;
    color: {fg};
}}
QLabel#caption {{
    font-size: 11px;
    color: {fg_dim};
}}
QLabel#dashTitle {{
    font-size: 20px;
    font-weight: 400;
    color: {accent};
    font-family: {ui_display};
}}
QLabel#dashVersion {{
    font-size: 11px;
    color: {fg_dim};
}}
QLabel#cardTitle {{
    font-size: 12px;
    font-weight: 400;
    color: {fg};
}}
QLabel#cardSub {{
    font-size: 11px;
    color: {fg_dim};
}}
QLabel#protoChip {{
    font-size: 10px;
    font-weight: 700;
    color: {fg_dim};
    background: {bg3};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 0px 5px;
}}
QLabel#tabCount {{
    font-size: 10px;
    font-weight: 700;
    color: {fg};
    background: {bg3};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 0px 5px;
}}
QLabel#sideTitle {{
    font-size: 12px;
    font-weight: 700;
    color: {fg};
}}
QLabel#sideCount {{
    background: {bg3};
    color: {fg_dim};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 0px 5px;
    font-size: 11px;
    font-weight: 400;
}}
QTreeView#sessionTree {{
    border: 1px solid {border_strong};
    background: {bg2};
    outline: none;
}}
QTreeView#sessionTree::item {{
    min-height: 20px;
    border-radius: 0px;
    margin: 0px;
    padding: 1px 3px;
    border: 1px solid transparent;
}}
QTreeView#sessionTree::item:hover {{
    background: {sel_hover};
    border-color: {accent_subtle};
}}
QTreeView#sessionTree::item:selected {{
    background: {accent_subtle};
    color: {fg};
    border: 1px solid transparent;
    border-left: 2px solid {accent};
}}
QTreeView#sessionTree::item:selected:!active {{
    background: {bg3};
    border-color: {border_strong};
}}
QTreeView#sessionTree::branch {{
    background: transparent;
}}
QLabel#pvTitle {{
    font-size: 12.5px;
    font-weight: 700;
    color: {fg};
}}
QFrame#palettePreview {{
    background: {bg};
    border: 1px solid {border_strong};
    border-radius: 0px;
}}
QSplitter#paletteSplit::handle {{
    background: transparent;
    width: 6px;
}}
QLabel#pvSub {{
    font-size: 11px;
    color: {fg_dim};
}}
QLabel#pvChip {{
    font-size: 10px;
    font-weight: 700;
    color: {fg_dim};
    background: {bg3};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 1px 5px;
}}
QLabel#pvKbd, QLabel#kbd {{
    font-size: 11px;
    font-weight: 400;
    color: {fg};
    background: {bg2};
    border: 1px solid {border_strong};
    border-bottom: 2px solid {border_strong};
    border-radius: 2px;
    padding: 0px 5px;
    font-family: {ui_mono};
}}
QPushButton#tabClose {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 1px;
    min-width: 0px;
}}
QPushButton#tabClose:hover {{
    background: {bad};
    border-color: {bad_active};
}}
QPushButton#tabClose:pressed {{
    background: {bad_active};
}}
QFrame#hairline {{
    background: {border};
    max-height: 1px;
    border: none;
}}

/* ================= Dialogs ================= */
QDialog {{
    background: {bg};
    border-radius: 0px;
}}

/* ================= Surfaces ================= */
QWidget#card {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 3px;
}}
QWidget#card_hover {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 3px;
}}
QWidget#card_hover:hover {{
    border-color: {accent};
    background: {sel_hover};
}}
QWidget#header {{
    background: {bg};
    border-bottom: 1px solid {border};
    border-radius: 0px;
}}
QWidget#sidebar {{
    background: {bg};
    border-right: 1px solid {border};
}}
QWidget#sidebarPanel {{
    background: {bg};
}}
QWidget#workArea {{
    background: {bg};
}}
QWidget#dashboard {{
    background: {bg2};
    border: 1px solid {border_strong};
}}

/* ================= Command bar (MobaXterm terminal command line) ===== */
QWidget#commandBar {{
    background: {bg};
    border-top: 1px solid {border};
    padding: 0px;
}}
QLabel#commandPrompt {{
    color: {fg};
    font-size: 12px;
    font-weight: 400;
    padding-left: 2px;
}}
QLineEdit#commandLine {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 2px 6px;
    font-size: 12px;
    font-family: {ui_mono};
    min-height: 16px;
}}
QLineEdit#commandLine:focus {{
    border-color: {accent};
    background: {bg2};
}}
QLineEdit#commandLine:hover {{
    border-color: {accent};
}}

/* ================= Status session chip ================= */
QLabel#statusSession {{
    color: {fg};
    font-family: {ui_sans};
    font-size: 11.5px;
    background: transparent;
    border: none;
    padding: 0px 6px;
}}

/* ================= Scroll area ================= */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QTabWidget::tab-bar {{
    alignment: left;
}}

/* ================= SpinBox buttons — Windows up/down ================= */
QSpinBox::up-button, QSpinBox::down-button {{
    background: {bg2};
    border: none;
    border-left: 1px solid {border};
    border-radius: 0px;
    width: 16px;
    margin: 0px;
}}
QSpinBox::up-button {{
    border-bottom: 1px solid {border};
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {sel_hover};
}}
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
    background: {accent_subtle};
}}
QSpinBox::up-arrow {{
    image: url({chev_up_url});
    width: 10px; height: 10px;
}}
QSpinBox::down-arrow {{
    image: url({chev_down_dim_url});
    width: 10px; height: 10px;
}}

/* ================= Sliders ================= */
QSlider::groove:horizontal {{
    height: 4px;
    background: {bg3};
    border: 1px solid {border_strong};
    border-radius: 0px;
}}
QSlider::handle:horizontal {{
    background: {accent};
    border: 1px solid {accent_active};
    width: 10px;
    margin: -6px 0;
    border-radius: 2px;
}}
QSlider::handle:horizontal:hover {{
    background: {accent_hover};
}}

/* ================= Dock / misc ================= */
QDockWidget::title {{
    background: {bg3};
    padding: 4px 6px;
    border: 1px solid {border};
}}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {border};
}}
"""

_QSS_COMPACT = """
/* ================= Compact density (Settings → UI) ================= */
QWidget {{ font-size: 11.5px; }}
QMenuBar {{ min-height: 20px; font-size: 11.5px; }}
QMenuBar::item {{ padding: 2px 7px; }}
QMenu::item {{ padding: 3px 20px 3px 28px; }}
QToolBar {{ min-height: 28px; padding: 1px 4px; }}
QToolBar#moxaToolbar {{ min-height: 44px; padding: 2px 4px; }}
QToolBar#moxaToolbar QToolButton {{ min-height: 34px; min-width: 40px; padding: 2px 5px; font-size: 10.5px; }}
QToolButton {{ padding: 2px 5px; min-height: 20px; font-size: 11.5px; }}
QPushButton {{ padding: 2px 10px; min-height: 15px; font-size: 11.5px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    padding: 2px 5px; min-height: 15px; font-size: 11.5px;
}}
QTabBar::tab {{ padding: 3px 8px; min-height: 16px; }}
QTreeView::item, QListView::item, QTableView::item {{ padding: 1px 3px; min-height: 18px; }}
QTreeView#sessionTree::item {{ min-height: 18px; padding: 0px 3px; }}
QStatusBar {{ min-height: 18px; font-size: 11px; }}
QGroupBox {{ margin-top: 9px; padding: 9px 8px 6px 8px; }}
QCheckBox, QRadioButton {{ font-size: 11.5px; }}
"""
