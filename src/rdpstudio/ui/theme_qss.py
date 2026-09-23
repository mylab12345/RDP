"""Global stylesheets — "Ops console" design system.

Format templates — ``apply_theme()`` in ``theme.py`` fills them.

Design tokens (single source of truth for the presentation layer):
  radius  — 4 px (in-card items) · 6 px (controls) · 8 px (cards, menus)
            · 10 px (floating surfaces) · 999 px (pills)
  type    — 11 px captions · 12.5 px body/controls · 13 px titles ·
            16 px dialog h1 · 20–21 px dashboard display
  depth   — layered neutral surfaces, 1 px subtle borders, soft shadows
            on floating elements only
  focus   — 2 px accent outline on every interactive family
"""

from __future__ import annotations

_QSS = """
/* ================= KB-Remote — Ops console design system ============== */

* {{
    font-family: {ui_sans};
    outline: none;
}}
QMainWindow, QDialog {{
    background: {bg};
}}
QWidget {{
    color: {fg};
    font-size: 12.5px;
}}
QToolTip {{
    background: {bg2};
    color: {fg};
    border: 1px solid {border_strong};
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 12px;
}}

/* ================= Menus ============================================= */
QMenuBar {{
    background: {panel};
    border-bottom: 1px solid {border};
    padding: 0px 4px;
    spacing: 0px;
    font-size: 12.5px;
    min-height: 26px;
}}
QMenuBar::item {{
    padding: 4px 10px;
    border-radius: 6px;
    color: {fg_dim};
    margin: 2px 1px 2px 1px;
}}
QMenuBar::item:hover {{
    background: {bg3};
    color: {fg};
}}
QMenuBar::item:pressed {{
    background: {panel2};
    color: {fg};
}}
QMenuBar::item:selected {{
    background: {bg3};
    color: {fg};
}}

QMenu {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 5px 5px;
    margin: 4px 0px;
}}
QMenu::item {{
    padding: 5px 26px 5px 10px;
    border-radius: 6px;
    color: {fg};
    font-size: 12.5px;
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
    background: {border_subtle};
    margin: 5px 8px 5px 8px;
}}
QMenu::icon {{
    left: 6px;
    width: 16px;
    height: 16px;
}}
QMenu::indicator {{
    left: 7px;
    width: 14px;
    height: 14px;
    border-radius: 3px;
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
    right: 8px;
}}

/* ================= Toolbar — big icon + caption ======================= */
QToolBar {{
    background: {panel};
    border: none;
    border-bottom: 1px solid {border};
    spacing: 2px;
    padding: 3px 8px;
    min-height: 40px;
}}
QToolBar#moxaToolbar {{
    spacing: 2px;
    padding: 5px 8px 4px 8px;
    min-height: 56px;
}}
QToolBar#moxaToolbar QToolButton {{
    padding: 5px 10px 4px 10px;
    min-width: 56px;
    min-height: 46px;
    font-size: 11px;
    font-weight: 500;
    color: {fg_dim};
    border-radius: 6px;
}}
QToolBar#moxaToolbar QToolButton:hover {{
    background: {bg3};
    color: {fg};
}}
QToolBar#moxaToolbar QToolButton:pressed {{
    background: {panel2};
    color: {fg};
}}
QToolBar#moxaToolbar QToolButton:checked {{
    background: {accent_subtle};
    color: {accent};
}}
QToolBar::separator {{
    width: 1px;
    background: {border};
    margin: 8px 6px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 8px;
    color: {fg_dim};
    font-weight: 500;
    font-size: 12.5px;
}}
QToolButton:hover {{
    background: {bg3};
    color: {fg};
}}
QToolButton:pressed {{
    background: {panel2};
    color: {fg};
}}
QToolButton:checked {{
    background: {accent_subtle};
    color: {accent};
}}
QToolButton:focus {{
    outline: 2px solid {accent};
    outline-offset: -2px;
}}
QToolButton:disabled {{
    color: {fg_muted};
}}
QToolButton::menu-indicator {{
    image: none;
}}

/* ================= Buttons ============================================ */
QPushButton {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 6px;
    padding: 5px 14px;
    color: {fg};
    font-weight: 500;
    font-size: 12.5px;
    min-height: 20px;
    min-width: 56px;
}}
QPushButton:hover {{
    border-color: {accent};
    background: {panel};
}}
QPushButton:pressed {{
    background: {accent_subtle};
    border-color: {accent};
}}
QPushButton:focus {{
    outline: 2px solid {accent};
    outline-offset: -2px;
}}
QPushButton:default {{
    border: 1px solid {accent};
}}
QPushButton:disabled {{
    color: {fg_muted};
    background: {bg3};
    border-color: {border_subtle};
}}
QPushButton#primary, QPushButton#accent {{
    background: {accent};
    color: {accent_text};
    border: 1px solid {accent};
    font-weight: 600;
    border-radius: 6px;
}}
QPushButton#primary:hover, QPushButton#accent:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
}}
QPushButton#primary:pressed, QPushButton#accent:pressed {{
    background: {accent_active};
    border-color: {accent_active};
}}
QPushButton#primary:disabled, QPushButton#accent:disabled {{
    background: {bg3};
    color: {fg_muted};
    border-color: {border_subtle};
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {fg_dim};
    border-radius: 6px;
    min-width: 60px;
}}
/* Square, icon-only ghost buttons (side panel toolbar, tab-strip corner).
   The 60 px min-width above is for labelled ghost buttons — on these it
   inflated the Sessions panel's minimum width by ~230 px, which stopped the
   splitter from being dragged narrow. */
QPushButton#ghost[iconOnly="true"] {{
    min-width: 0px;
    min-height: 0px;
    padding: 0px;
}}
QPushButton#ghost:hover {{
    background: {bg3};
    color: {fg};
}}
QPushButton#ghost:pressed {{
    background: {panel2};
}}
/* Dock grips — the little ⠿ handle you drag to move the Sessions panel or
   the session tab strip to another edge (see ui/docking.py). */
QPushButton#dockGrip {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    min-width: 0px;
    min-height: 0px;
    padding: 0px;
}}
QPushButton#dockGrip:hover {{
    background: {accent_subtle};
    border-color: {border_strong};
}}
QPushButton#dockGrip:pressed {{
    background: {bg3};
    border-color: {accent};
}}
QPushButton#subtle {{
    background: {bg2};
    border: 1px solid {border_strong};
    color: {fg};
    border-radius: 6px;
    min-width: 0px;
}}
QPushButton#subtle:hover {{
    border-color: {accent};
    background: {panel};
}}
QPushButton#danger {{
    background: transparent;
    border: 1px solid {bad_border};
    color: {bad};
    border-radius: 6px;
    font-weight: 500;
}}
QPushButton#danger:hover {{
    background: {bad};
    border-color: {bad};
    color: {bad_text};
}}
QPushButton#danger:pressed {{
    background: {bad_active};
    border-color: {bad_active};
    color: {bad_text};
}}
QPushButton#danger:disabled {{
    color: {fg_muted};
    background: transparent;
    border-color: {border_subtle};
}}

/* Quick connect — joined input + button group (toolbar) */
QWidget#quickConnect {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 6px;
}}
QWidget#quickConnect:hover {{
    border-color: {accent};
}}
QWidget#quickConnect QLineEdit {{
    background: transparent;
    border: none;
    padding: 2px 10px;
    font-size: 12.5px;
    color: {fg};
    min-height: 20px;
}}
QWidget#quickConnect QLineEdit:focus {{
    border: none;
}}
QWidget#quickConnect QPushButton {{
    background: {accent};
    color: {accent_text};
    border: none;
    border-radius: 0px 5px 5px 0px;
    padding: 2px 12px;
    font-size: 12.5px;
    font-weight: 600;
    min-height: 20px;
    min-width: 0px;
}}
QWidget#quickConnect QPushButton:hover {{
    background: {accent_hover};
}}

/* ================= Inputs ============================================= */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 6px;
    padding: 5px 9px;
    selection-background-color: {accent};
    selection-color: {accent_text};
    color: {fg};
    min-height: 20px;
    font-size: 12.5px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {accent};
    background: {bg2};
}}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{
    border-color: {fg_muted};
}}
QLineEdit:focus:hover, QSpinBox:focus:hover, QComboBox:focus:hover {{
    border-color: {accent};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background: {bg3};
    color: {fg_muted};
    border-color: {border_subtle};
}}
QLineEdit#search, QLineEdit#sideQuick {{
    border-radius: 6px;
    padding: 4px 8px 4px 8px;
    background: {bg2};
    border: 1px solid {border_strong};
    font-size: 12.5px;
}}
QLineEdit#search:focus, QLineEdit#sideQuick:focus {{
    border-color: {accent};
}}
QLineEdit#search:hover, QLineEdit#sideQuick:hover {{
    border-color: {fg_muted};
}}
QLineEdit#invalid, QSpinBox#invalid, QComboBox#invalid {{
    border-color: {bad};
}}
QLineEdit#invalid:focus, QSpinBox#invalid:focus, QComboBox#invalid:focus {{
    border-color: {bad};
}}

QComboBox {{
    padding-right: 26px;
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
    border-left: 1px solid {border_subtle};
    width: 24px;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
}}
QComboBox::drop-down:hover {{
    background: {bg3};
}}
QComboBox::down-arrow {{
    image: url({chev_down_dim_url});
    width: 12px; height: 12px;
}}
QComboBox QAbstractItemView {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {accent_subtle};
    selection-color: {fg};
    outline: none;
    font-family: {ui_sans};
}}
QComboBox QAbstractItemView::item {{
    padding: 5px 10px;
    border-radius: 6px;
    margin: 0px;
    min-height: 20px;
    border: none;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {bg3};
    color: {fg};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {accent_subtle};
    color: {fg};
    font-weight: 500;
}}

/* ================= Tabs — modern document tabs ======================== */
QTabWidget::pane {{
    border: 1px solid {border_strong};
    border-top: 1px solid {border_strong};
    background: {bg2};
    border-radius: 0px 0px 6px 6px;
    top: -1px;
}}
QTabBar {{
    background: transparent;
    qproperty-drawBase: 0;
    /* Transparent by default so the :focus recolor below causes no shift. */
    border: 2px solid transparent;
}}
QTabBar:focus {{
    border-color: {accent};
    border-radius: 6px;
}}
QTabBar::tab {{
    background: transparent;
    color: {fg_dim};
    padding: 6px 12px 6px 10px;
    border: 1px solid transparent;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    margin-top: 3px;
    font-weight: 500;
    font-size: 12.5px;
    min-height: 20px;
    max-width: 200px;
}}
QTabBar::tab:selected {{
    background: {bg2};
    color: {fg};
    border-color: {border_strong};
    border-top: 2px solid {accent};
    font-weight: 600;
    margin-top: 1px;
    padding-bottom: 7px;
}}
QTabBar::tab:hover:!selected {{
    background: {bg3};
    color: {fg};
}}
QTabBar::tab:first {{
    margin-left: 2px;
}}
/* Session tab strip docked to a side edge (View ▸ Session Tabs, or drag the
   strip by its grip). Corners and the selected indicator move to the edge
   facing away from the work area, i.e. an N bar turned 90°. The ``dock``
   dynamic property is set on the QTabBar by the main window to the zone id
   ("left" / "right" / "top") — an attribute selector beats the plain
   :selected rules above regardless of order, and Qt draws the labels rotated
   for vertical shapes. min-width is what gives a rotated label room: without
   it Qt elides "root@prod-web-01" down to two characters. */
QTabBar[dock="left"]::tab, QTabBar[dock="right"]::tab {{
    border-radius: 0px;
    max-width: none;
    max-height: 150px;
    /* Rotated labels need their own room: Qt reserves the close-button slot
       out of this width, and ~120 px left "root@prod-web-01" elided at 13
       characters. */
    min-width: 160px;
    min-height: 26px;
    margin: 0px 0px 2px 0px;
    padding: 7px 10px 7px 8px;
}}
QTabBar[dock="left"]::tab {{
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
}}
QTabBar[dock="right"]::tab {{
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}
QTabBar[dock="left"]::tab:first, QTabBar[dock="right"]::tab:first {{
    margin-top: 2px;
    margin-left: 0px;
}}
QTabBar[dock="left"]::tab:selected {{
    border-color: {border_strong};
    border-left: 2px solid {accent};
}}
QTabBar[dock="right"]::tab:selected {{
    border-color: {border_strong};
    border-right: 2px solid {accent};
}}
QTabBar[dock="left"]::close-button, QTabBar[dock="right"]::close-button {{
    subcontrol-position: bottom right;
    margin: 0px 6px 6px 0px;
}}
QTabBar[dock="left"]::scroller, QTabBar[dock="right"]::scroller {{
    width: 22px;
    height: 30px;
}}

/* Vertical tab strip (sidebar left rail: chevron + Sessions / Tools) */
QPushButton#railCollapse {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    color: {accent};
    font-size: 12px;
    font-weight: 700;
    padding: 0px;
}}
QPushButton#railCollapse:hover {{
    background: {accent_subtle};
    border-color: {border};
}}
QPushButton#railCollapse:pressed {{
    background: {bg3};
}}
QTabBar#sideRail {{
    border: none;
}}
QTabBar#sideRail::tab {{
    background: transparent;
    color: {fg_dim};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 10px 4px 10px 3px;
    margin: 3px 4px 3px 2px;
    min-height: 64px;
    min-width: 16px;
    font-size: 11px;
}}
QTabBar#sideRail::tab:selected {{
    background: {accent_subtle};
    color: {accent};
    font-weight: 600;
    border-color: transparent;
}}
QTabBar#sideRail::tab:hover:!selected {{
    background: {bg3};
    color: {fg};
}}

/* ================= Trees & Lists — refined rows ======================= */
QTreeView, QListView, QTableView {{
    background: {bg2};
    alternate-background-color: {panel};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 2px;
    outline: none;
    font-size: 12.5px;
    show-decoration-selected: 1;
}}
QTreeView::item, QListView::item, QTableView::item {{
    padding: 3px 6px;
    border-radius: 6px;
    margin: 0px;
    color: {fg};
    border: 1px solid transparent;
    min-height: 22px;
}}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{
    background: {bg3};
    border-color: transparent;
}}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background: {accent_subtle};
    color: {fg};
    border: 1px solid transparent;
    font-weight: 500;
}}
QTreeView::item:selected:active, QListView::item:selected:active {{
    background: {accent_subtle};
    color: {fg};
}}
QTreeView::item:selected:!active, QListView::item:selected:!active {{
    background: {bg3};
    border-color: transparent;
    font-weight: 500;
}}
/* Keyboard focus: recolor the frame — no geometry shift. */
QTreeView:focus, QListView:focus, QTableView:focus {{
    border: 1px solid {accent};
}}
QTreeView::branch {{
    background: transparent;
}}
QTreeView::branch:selected {{
    background: transparent;
}}
QTreeView::branch:hover {{
    background: transparent;
}}
QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {{
    image: url({chev_right_url});
    border-image: none;
    subcontrol-origin: branch;
    subcontrol-position: center left;
}}
QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {{
    image: url({chev_down_url});
    border-image: none;
    subcontrol-origin: branch;
    subcontrol-position: center left;
}}
QHeaderView::section {{
    background: {panel};
    border: none;
    border-bottom: 1px solid {border};
    border-right: 1px solid {border_subtle};
    padding: 6px 10px;
    font-weight: 600;
    font-size: 11.5px;
    color: {fg_dim};
    letter-spacing: 0.3px;
}}
QHeaderView::section:hover {{
    background: {bg3};
}}
QTableView QTableCornerButton::section {{
    background: {panel};
    border: 1px solid {border};
}}
QTableView {{
    gridline-color: {border_subtle};
}}

/* ================= Splitter =========================================== */
QSplitter::handle {{
    background: transparent;
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

/* ================= Scrollbars — slim, modern ========================== */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {panel3};
    border-radius: 5px;
    min-height: 28px;
    margin: 0px 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {fg_muted};
}}
QScrollBar::handle:vertical:pressed {{
    background: {fg_dim};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {panel3};
    min-width: 28px;
    margin: 2px 0px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {fg_muted};
}}
QScrollBar::handle:horizontal:pressed {{
    background: {fg_dim};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0;
    background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ================= Status bar ========================================= */
QStatusBar {{
    background: {panel};
    border-top: 1px solid {border};
    color: {fg_dim};
    padding: 0px 8px;
    font-size: 11.5px;
    min-height: 24px;
}}
QStatusBar::item {{
    border: none;
    border-right: 1px solid {border};
}}
QStatusBar QLabel {{
    background: transparent;
    border: none;
}}

/* ================= Groups — card style ================================= */
QGroupBox {{
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    background: {bg2};
    font-weight: 400;
    font-size: 12.5px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    top: 0px;
    padding: 0px 6px;
    background: {bg2};
    color: {fg_dim};
    border: none;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QDialog QGroupBox::title {{
    background: {bg2};
}}
QFormLayout QLabel {{
    padding-top: 0px;
    color: {fg_dim};
    font-size: 12px;
    font-weight: 500;
}}

/* ================= Progress — accent bar =============================== */
QProgressBar {{
    background: {bg3};
    border: none;
    border-radius: 4px;
    text-align: center;
    height: 8px;
    color: {fg};
    font-size: 10.5px;
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: 4px;
}}

/* ================= Checkboxes & Radios ================================= */
QCheckBox, QRadioButton {{
    spacing: 7px;
    color: {fg};
    font-size: 12.5px;
    padding: 2px 0px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px;
    border-radius: 4px;
    border: 1px solid {border_strong};
    background: {bg2};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: url({check_url});
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {accent};
    background: {accent_subtle};
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
    border-color: {border_subtle};
    background: {bg3};
}}

/* ================= Labels ============================================== */
QLabel {{
    background: transparent;
}}
QLabel#muted {{
    color: {fg_dim};
    font-size: 12px;
}}
QLabel#h1 {{
    font-size: 16px;
    font-weight: 600;
    color: {fg};
}}
QLabel#h2 {{
    font-size: 13px;
    font-weight: 600;
    color: {fg};
}}
QLabel#caption {{
    font-size: 11px;
    color: {fg_muted};
}}
QLabel#dashTitle {{
    font-size: 21px;
    font-weight: 600;
    color: {fg};
    letter-spacing: -0.2px;
}}
QLabel#dashVersion {{
    font-size: 11px;
    color: {fg_muted};
    background: {bg3};
    border-radius: 999px;
    padding: 2px 9px;
    font-weight: 500;
}}
QLabel#cardTitle {{
    font-size: 12.5px;
    font-weight: 600;
    color: {fg};
}}
QLabel#cardSub {{
    font-size: 11px;
    color: {fg_muted};
}}
QLabel#protoChip {{
    font-size: 10px;
    font-weight: 600;
    color: {fg_dim};
    background: {bg3};
    border: 1px solid {border_subtle};
    border-radius: 999px;
    padding: 1px 8px;
    letter-spacing: 0.3px;
}}
QLabel#tabCount {{
    font-size: 10.5px;
    font-weight: 600;
    color: {fg_dim};
    background: {bg3};
    border: 1px solid {border_subtle};
    border-radius: 999px;
    padding: 0px 7px;
}}
QLabel#sideTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {fg};
}}
QLabel#sideCount {{
    background: {bg3};
    color: {fg_dim};
    border: 1px solid {border_subtle};
    border-radius: 999px;
    padding: 0px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QTreeView#sessionTree {{
    border: 1px solid {border_strong};
    background: {bg2};
    outline: none;
    border-radius: 8px;
}}
QTreeView#sessionTree::item {{
    min-height: 24px;
    border-radius: 6px;
    margin: 0px 2px;
    padding: 2px 6px;
    border: 1px solid transparent;
}}
QTreeView#sessionTree::item:hover {{
    background: {bg3};
    border-color: transparent;
}}
QTreeView#sessionTree::item:selected {{
    background: {accent_subtle};
    color: {fg};
    border: 1px solid transparent;
    font-weight: 500;
}}
QTreeView#sessionTree::item:selected:!active {{
    background: {accent_subtle};
    border-color: transparent;
    font-weight: 500;
}}
QTreeView#sessionTree::branch {{
    background: transparent;
}}
QLabel#pvTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {fg};
}}
QFrame#palettePreview {{
    background: {panel};
    border: none;
    border-left: 1px solid {border};
    border-radius: 0px;
}}
QSplitter#paletteSplit::handle {{
    background: transparent;
    width: 6px;
}}
QLabel#pvSub {{
    font-size: 11.5px;
    color: {fg_dim};
}}
QLabel#pvChip {{
    font-size: 10px;
    font-weight: 600;
    color: {fg_dim};
    background: {bg3};
    border: 1px solid {border_subtle};
    border-radius: 999px;
    padding: 1px 8px;
    letter-spacing: 0.3px;
}}
QLabel#pvKbd, QLabel#kbd {{
    font-size: 11px;
    font-weight: 500;
    color: {fg_dim};
    background: {bg2};
    border: 1px solid {border_strong};
    border-bottom: 2px solid {border_strong};
    border-radius: 5px;
    padding: 1px 7px;
    font-family: {ui_mono};
}}
QPushButton#tabClose {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 1px;
    min-width: 0px;
}}
QPushButton#tabClose:hover {{
    background: {bad_faint};
    border-color: transparent;
}}
QPushButton#tabClose:pressed {{
    background: {bad_soft2};
}}
QFrame#hairline {{
    background: {border};
    max-height: 1px;
    border: none;
}}

/* ================= Dialogs ============================================= */
QDialog {{
    background: {bg};
    border-radius: 0px;
}}

/* ================= Surfaces ============================================ */
QWidget#card {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 8px;
}}
QWidget#card_hover {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 8px;
}}
QWidget#card_hover:hover {{
    border-color: {accent};
    background: {panel};
}}
QWidget#header {{
    background: {panel};
    border-bottom: 1px solid {border};
    border-radius: 0px;
}}
QWidget#sidebar {{
    background: {panel};
    border-right: 1px solid {border};
}}
/* Sessions panel docked to the right edge (View ▸ Move Sessions Panel, or
   drag its grip): the divider moves to the panel's left side. */
QWidget#sidebar[side="right"] {{
    border-right: none;
    border-left: 1px solid {border};
}}
QWidget#sidebarPanel {{
    background: {panel};
}}
QWidget#workArea {{
    background: {bg};
}}
QWidget#dashboard {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 8px;
}}
/* Dashboard hero quick-connect */
QLineEdit#dashQuick {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    min-height: 24px;
}}
QLineEdit#dashQuick:focus {{
    border-color: {accent};
}}
QLineEdit#dashQuick:hover {{
    border-color: {fg_muted};
}}
QWidget#dashTile {{
    background: {bg};
    border: 1px solid {border};
    border-radius: 8px;
}}
QWidget#dashTile:hover {{
    border-color: {accent};
    background: {bg2};
}}
QLabel#dashTileIcon {{
    background: {bg2};
    border: 1px solid {border_subtle};
    border-radius: 8px;
}}

/* ================= Command bar (MobaXterm terminal command line) ====== */
QWidget#commandBar {{
    background: {panel};
    border-top: 1px solid {border};
    padding: 0px;
}}
QLabel#commandPrompt {{
    color: {fg_dim};
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.3px;
    padding-left: 4px;
}}
QLineEdit#commandLine {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12.5px;
    font-family: {ui_mono};
    min-height: 20px;
}}
QLineEdit#commandLine:focus {{
    border-color: {accent};
    background: {bg2};
}}
QLineEdit#commandLine:hover {{
    border-color: {fg_muted};
}}

/* ================= Status session chip ================================ */
QLabel#statusSession {{
    color: {fg_dim};
    font-family: {ui_sans};
    font-size: 11.5px;
    background: transparent;
    border: none;
    padding: 0px 8px;
}}

/* ================= Scroll area ========================================= */
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

/* ================= SpinBox buttons ===================================== */
QSpinBox::up-button, QSpinBox::down-button {{
    background: {bg2};
    border: none;
    border-left: 1px solid {border_subtle};
    border-radius: 0px;
    width: 18px;
    margin: 0px;
}}
QSpinBox::up-button {{
    border-bottom: 1px solid {border_subtle};
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {bg3};
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

/* ================= Sliders ============================================= */
QSlider::groove:horizontal {{
    height: 4px;
    background: {bg3};
    border: none;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {accent};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {bg2};
    border: 2px solid {accent};
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{
    background: {accent_subtle};
}}

/* ================= Dock / misc ========================================= */
QDockWidget::title {{
    background: {bg3};
    padding: 5px 8px;
    border: 1px solid {border};
}}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {border};
}}
QMessageBox {{
    background: {bg};
}}
"""

_QSS_COMPACT = """
/* ================= Compact density (Settings → UI) ===================== */
QWidget {{ font-size: 11.5px; }}
QMenuBar {{ min-height: 22px; font-size: 11.5px; }}
QMenuBar::item {{ padding: 3px 8px; }}
QMenu::item {{ padding: 4px 22px 4px 8px; }}
QToolBar {{ min-height: 32px; padding: 2px 6px; }}
QToolBar#moxaToolbar {{ min-height: 46px; padding: 3px 6px; }}
QToolBar#moxaToolbar QToolButton {{ min-height: 36px; min-width: 48px; padding: 3px 6px; font-size: 10.5px; }}
QToolButton {{ padding: 3px 6px; min-height: 22px; font-size: 11.5px; }}
QPushButton {{ padding: 3px 10px; min-height: 17px; font-size: 11.5px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    padding: 3px 7px; min-height: 17px; font-size: 11.5px;
}}
QTabBar::tab {{ padding: 4px 10px 4px 8px; min-height: 18px; font-size: 11.5px; }}
QTreeView::item, QListView::item, QTableView::item {{ padding: 2px 5px; min-height: 20px; }}
QTreeView#sessionTree::item {{ min-height: 21px; padding: 1px 5px; }}
QStatusBar {{ min-height: 21px; font-size: 11px; }}
QGroupBox {{ margin-top: 10px; padding: 12px 10px 9px 10px; }}
QCheckBox, QRadioButton {{ font-size: 11.5px; }}
QLabel#dashTitle {{ font-size: 18px; }}
QLabel#dashVersion {{ padding: 1px 7px; }}
"""
