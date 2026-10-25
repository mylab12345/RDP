"""Global stylesheets — the *Aurora workbench* design system.

Format templates — ``apply_theme()`` in ``theme.py`` fills them with the
palette plus the derived tokens from :func:`rdpstudio.ui.theme.design_tokens`.

Design tokens (single source of truth for the presentation layer):

  radius   — 4-step scale, never ad hoc: 6 px small/in-card items,
             8 px controls & chips, 10 px cards, menus, panels and
             floating surfaces, 999 px pills/indicators
  space    — 4 px grid; 10/14/18 px padding steps; 8 px gap between groups
  type     — 10.5 px overline/labels · 12.5 px body · 13 px titles ·
             15 px dialog headings · 21/26 px display
  surfaces — window wash → chrome → card → raised card (gradients, 1 px
             hairlines, a single accent-tinged elevation step)
  accent   — reserved for the primary action, active navigation and focus;
             never for body text or borders of static content
  focus    — 2 px accent outline offset outwards on every interactive family
  motion   — discrete easing is applied by widgets (fade/slide/glow); the
             sheet only carries the resting and hover states

The sheet stays declarative: no colours are hard-coded here, so every theme
(including the light and high-contrast palettes) is generated coherently.
"""

from __future__ import annotations

_QSS = """
/* =====================================================================
   KB-Remote — Aurora workbench design system
   ===================================================================== */

* {{
    font-family: {ui_sans};
    outline: none;
}}
QMainWindow {{
    background: {bg_grad};
}}
QDialog {{
    background: {bg_grad};
}}
QWidget {{
    color: {fg};
    font-size: 12.5px;
}}
QToolTip {{
    background: {panel2};
    color: {fg};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 7px 11px;
    font-size: 12px;
}}

/* ================= Menus — floating glass ============================ */
QMenuBar {{
    background: transparent;
    border: none;
    padding: 4px 12px 0px 12px;
    spacing: 3px;
    font-size: 12.5px;
    font-weight: 500;
    min-height: 30px;
}}
QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 8px;
    color: {fg_dim};
    margin: 3px 1px;
    background: transparent;
}}
QMenuBar::item:hover {{
    background: {accent_soft};
    color: {fg};
}}
QMenuBar::item:pressed {{
    background: {accent_soft2};
    color: {fg};
}}
QMenuBar::item:selected {{
    background: {accent_soft2};
    color: {fg};
}}
QMenuBar::item:focus {{
    background: {accent_soft2};
    color: {fg};
    outline: 2px solid {accent};
    outline-offset: -2px;
}}

QMenu {{
    background: {panel2};
    border: 1px solid {border_strong};
    border-radius: 10px;
    padding: 7px 6px;
    margin: 6px 0px;
}}
QMenu::item {{
    padding: 8px 28px 8px 12px;
    border-radius: 8px;
    color: {fg};
    font-size: 12.5px;
    margin: 1px 2px;
    background: transparent;
}}
QMenu::item:selected {{
    background: {accent_soft};
    color: {fg};
}}
QMenu::item:selected:active {{
    background: {accent_soft2};
    color: {fg};
}}
QMenu::item:disabled {{
    color: {fg_muted};
}}
QMenu::separator {{
    height: 1px;
    background: {hairline};
    margin: 6px 10px;
}}
QMenu::icon {{
    left: 9px;
    width: 16px;
    height: 16px;
}}
QMenu::indicator {{
    left: 8px;
    width: 15px;
    height: 15px;
    border-radius: 6px;
    border: 1px solid {border_strong};
    background: {field_bg};
}}
QMenu::indicator:checked {{
    background: {accent_grad};
    border-color: {accent};
    image: url({check_url});
}}
QMenu::indicator:exclusive:checked {{
    background: {accent_grad};
    border-color: {accent};
    image: url({dot_url});
}}
QMenu::right-arrow {{
    image: url({chev_right_url});
    width: 14px;
    height: 14px;
    right: 10px;
}}

/* ================= Toolbar — product command bar ===================== */
QToolBar {{
    background: {chrome_grad};
    border: none;
    border-bottom: 1px solid {hairline};
    padding: 7px 12px;
    spacing: 4px;
    min-height: 44px;
}}
QToolBar#moxaToolbar {{
    background: {chrome_grad};
    border-bottom: 1px solid {border};
    padding: 8px 14px;
    spacing: 5px;
    min-height: 46px;
}}
QToolBar#moxaToolbar QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 11px;
    color: {fg_dim};
    font-size: 12.5px;
    font-weight: 500;
    min-height: 20px;
    margin: 1px 0px;
}}
QToolBar#moxaToolbar QToolButton:hover {{
    background: {btn_face_hover};
    border: 1px solid {btn_line_hover};
    color: {fg};
}}
QToolBar#moxaToolbar QToolButton:pressed {{
    background: {btn_face_press};
    border: 1px solid {accent_line};
    color: {fg};
}}
QToolBar#moxaToolbar QToolButton:checked {{
    background: {accent_soft2};
    border: 1px solid {accent_line};
    color: {fg};
}}
QToolBar#moxaToolbar QToolButton:focus {{
    outline: 2px solid {accent};
    outline-offset: -2px;
}}
/* Primary call to action inside the command bar */
QToolBar#moxaToolbar QToolButton#tbPrimary {{
    background: {accent_grad};
    border: 1px solid {accent_hover};
    color: {accent_text};
    font-weight: 700;
    padding: 7px 14px;
}}
QToolBar#moxaToolbar QToolButton#tbPrimary:hover {{
    background: {accent_grad_hover};
    border-color: {accent_hover};
    color: {accent_text};
}}
QToolBar#moxaToolbar QToolButton#tbPrimary:pressed {{
    background: {accent_grad_press};
    border-color: {accent_active};
    color: {accent_text};
}}
/* Icon-only utility cluster on the right of the bar */
QToolBar#moxaToolbar QToolButton#tbIcon {{
    padding: 7px;
    min-width: 20px;
    color: {fg_muted};
}}
QToolBar#moxaToolbar QToolButton#tbIcon:hover {{
    color: {fg};
}}
QToolBar#moxaToolbar QToolButton::menu-indicator {{
    image: none;
}}
QToolBar::separator {{
    background: {hairline};
    width: 1px;
    margin: 8px 7px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px 9px;
    color: {fg_dim};
    min-height: 20px;
    font-size: 12.5px;
}}
QToolButton:hover {{
    background: {btn_face_hover};
    border: 1px solid {btn_line_hover};
    color: {fg};
}}
QToolButton:pressed {{
    background: {btn_face_press};
    border: 1px solid {accent_line};
    color: {fg};
}}
QToolButton:checked {{
    background: {accent_soft2};
    border: 1px solid {accent_line};
    color: {fg};
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

/* Brand block at the head of the command bar */
QWidget#brandBlock {{
    background: transparent;
}}
QLabel#brandMark {{
    background: {accent_grad};
    border-radius: 10px;
    color: {accent_text};
    font-size: 14px;
    font-weight: 800;
    padding: 0px;
}}
QLabel#brandName {{
    color: {fg};
    font-family: {ui_display};
    font-size: 15px;
    font-weight: 700;
}}
QLabel#brandTag {{
    color: {fg_muted};
    font-size: 10.5px;
    font-weight: 600;
}}
QFrame#brandDivider {{
    background: {hairline};
    max-width: 1px;
    min-width: 1px;
}}

/* ================= Buttons ========================================== */
QPushButton {{
    background: {btn_face};
    border: 1px solid {btn_line};
    border-radius: 8px;
    color: {fg};
    padding: 7px 14px;
    min-height: 20px;
    font-size: 12.5px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {btn_face_hover};
    border: 1px solid {btn_line_hover};
    color: {fg};
}}
QPushButton:pressed {{
    background: {btn_face_press};
    border: 1px solid {accent_line};
}}
QPushButton:focus {{
    outline: 2px solid {accent};
    outline-offset: 1px;
}}
QPushButton:default {{
    border: 1px solid {accent_line};
}}
QPushButton:disabled {{
    background: {btn_face};
    border-color: {border_subtle};
    color: {fg_muted};
}}

/* Primary — accent gradient, the single most prominent action on a surface */
QPushButton#primary, QPushButton#accent {{
    background: {accent_grad};
    border: 1px solid {accent_hover};
    border-radius: 8px;
    color: {accent_text};
    font-weight: 700;
    padding: 7px 16px;
}}
QPushButton#primary:hover, QPushButton#accent:hover {{
    background: {accent_grad_hover};
    border-color: {accent_hover};
}}
QPushButton#primary:pressed, QPushButton#accent:pressed {{
    background: {accent_grad_press};
    border-color: {accent_active};
}}
QPushButton#primary:disabled, QPushButton#accent:disabled {{
    background: {btn_face};
    border-color: {border_subtle};
    color: {fg_muted};
}}

/* Ghost — text/icon actions that must not compete with the primary */
QPushButton#ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {fg_dim};
    font-weight: 500;
    padding: 6px 10px;
}}
QPushButton#ghost:hover {{
    background: {btn_face_hover};
    border: 1px solid {btn_line_hover};
    color: {fg};
}}
QPushButton#ghost:pressed {{
    background: {btn_face_press};
    border: 1px solid {accent_line};
}}
QPushButton#ghost[iconOnly="true"] {{
    padding: 0px;
    border-radius: 8px;
}}
QPushButton#ghost[iconOnly="true"]:hover {{
    background: {accent_soft2};
    border: 1px solid {accent_line};
}}
QPushButton#ghost:checked {{
    background: {accent_soft2};
    border: 1px solid {accent_line};
    color: {fg};
}}

/* Subtle — secondary buttons that still read as buttons */
QPushButton#subtle {{
    background: {accent_soft};
    border: 1px solid {accent_line};
    color: {fg};
    font-weight: 500;
}}
QPushButton#subtle:hover {{
    background: {accent_soft2};
    border-color: {accent};
}}
QPushButton#link {{
    background: transparent;
    border: none;
    color: {accent};
    padding: 2px 4px;
    text-decoration: underline;
}}
QPushButton#link:hover {{
    color: {accent_hover};
}}

/* Danger — destructive, tinted rather than filled */
QPushButton#danger {{
    background: {bad_soft};
    border: 1px solid {bad_line};
    color: {bad};
    font-weight: 600;
}}
QPushButton#danger:hover {{
    background: {bad_hover};
    border: 1px solid {bad};
    color: {bad_text};
}}
QPushButton#danger:pressed {{
    background: {bad_active};
    border-color: {bad_active};
    color: {bad_text};
}}
QPushButton#danger:disabled {{
    background: {btn_face};
    border-color: {border_subtle};
    color: {fg_muted};
}}

QPushButton#dockGrip {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0px;
    color: {fg_muted};
}}
QPushButton#dockGrip:hover {{
    background: {accent_soft2};
    color: {fg};
}}
QPushButton#dockGrip:pressed {{
    background: {btn_face_press};
}}

/* ================= Quick connect — inline command field ============= */
QWidget#quickConnect {{
    background: {field_bg};
    border: 1px solid {border};
    border-radius: 10px;
}}
QWidget#quickConnect:hover {{
    border: 1px solid {btn_line_hover};
}}
QWidget#quickConnect:focus-within {{
    border: 1px solid {accent};
    background: {field_bg_focus};
}}
QWidget#quickConnect QLineEdit {{
    background: transparent;
    border: none;
    border-radius: 0px;
    padding: 0px 2px;
    min-height: 0px;
    color: {fg};
    selection-background-color: {accent};
    selection-color: {accent_text};
}}
QWidget#quickConnect QLineEdit:focus {{
    border: none;
    background: transparent;
}}
QWidget#quickConnect QPushButton {{
    background: {accent_grad};
    border: 1px solid {accent_hover};
    border-radius: 8px;
    color: {accent_text};
    font-weight: 700;
    padding: 4px 14px;
    margin: 2px;
    min-height: 18px;
}}
QWidget#quickConnect QPushButton:hover {{
    background: {accent_grad_hover};
}}
QWidget#quickConnect QPushButton:pressed {{
    background: {accent_grad_press};
}}

/* ================= Inputs — inset, calm, unambiguous focus ========== */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {field_bg};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 20px;
    color: {fg};
    selection-background-color: {accent};
    selection-color: {accent_text};
}}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QSpinBox:hover,
QDoubleSpinBox:hover, QComboBox:hover {{
    background: {field_bg_hover};
    border: 1px solid {btn_line_hover};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus {{
    background: {field_bg_focus};
    border: 1px solid {accent};
    outline: 2px solid {accent_ring};
    outline-offset: -1px;
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled,
QPlainTextEdit:disabled, QTextEdit:disabled {{
    background: {bg3};
    color: {fg_muted};
    border-color: {border_subtle};
}}
QLineEdit#search, QLineEdit#sideQuick {{
    background: {field_bg};
    border: 1px solid {border};
    border-radius: 999px;
    padding: 6px 13px;
}}
QLineEdit#search:focus, QLineEdit#sideQuick:focus {{
    border: 1px solid {accent};
    background: {field_bg_focus};
    outline: 2px solid {accent_ring};
    outline-offset: -1px;
}}
QLineEdit#search:hover, QLineEdit#sideQuick:hover {{
    border: 1px solid {btn_line_hover};
}}
QLineEdit#invalid, QSpinBox#invalid, QComboBox#invalid {{
    border: 1px solid {bad};
    background: {bad_soft};
}}
QLineEdit#invalid:focus, QSpinBox#invalid:focus, QComboBox#invalid:focus {{
    border: 1px solid {bad};
    outline: 2px solid {bad_soft};
}}

QComboBox {{
    padding-right: 26px;
}}
QComboBox:on {{
    border: 1px solid {accent};
    background: {field_bg_focus};
}}
QComboBox:editable {{
    background: {field_bg};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 24px;
    border: none;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background: transparent;
}}
QComboBox::drop-down:hover {{
    background: {accent_soft};
}}
QComboBox::down-arrow {{
    image: url({chev_down_url});
    width: 13px;
    height: 13px;
}}
QComboBox QAbstractItemView {{
    background: {panel2};
    border: 1px solid {border_strong};
    border-radius: 10px;
    padding: 5px;
    outline: none;
    selection-background-color: {accent_soft2};
}}
QComboBox QAbstractItemView::item {{
    min-height: 26px;
    padding: 4px 9px;
    border-radius: 6px;
    color: {fg};
}}
QComboBox QAbstractItemView::item:hover {{
    background: {accent_soft};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {accent_soft2};
    color: {fg};
}}

/* ================= Tabs — document tabs as soft pills =============== */
QTabWidget {{
    background: transparent;
}}
/* Flat pane: the tab strip already separates itself from the content, an
   extra frame line would just double the hairline. */
QTabWidget::pane {{
    background: transparent;
    border: none;
    top: -1px;
}}
QTabBar {{
    background: transparent;
    qproperty-drawBase: 0;
}}
QTabBar:focus {{
    outline: 2px solid {accent};
    outline-offset: -2px;
}}
QTabBar::tab {{
    background: transparent;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
    border-radius: 10px 10px 0px 0px;
    color: {fg_muted};
    padding: 9px 14px 8px 12px;
    margin: 4px 2px 0px 2px;
    min-height: 20px;
    font-size: 12.5px;
    font-weight: 500;
}}
QTabBar::tab:selected {{
    background: {tab_active_grad};
    border: 1px solid transparent;
    border-bottom: 2px solid {accent};
    color: {fg};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background: {btn_face_hover};
    color: {fg};
    border: 1px solid transparent;
    border-bottom: 2px solid {hairline};
}}
QTabBar::tab:first {{
    margin-left: 4px;
}}
/* A side-docked strip rotates its labels, so the tab must be wide enough to
   read the rotated text instead of eliding it to two characters. */
QTabBar[dock="left"]::tab, QTabBar[dock="right"]::tab {{
    border-radius: 0px 10px 10px 0px;
    margin: 1px 0px;
    max-width: none;
    max-height: 168px;
    min-width: 160px;
    min-height: 26px;
    padding: 8px 10px 8px 8px;
}}
QTabBar[dock="left"]::tab:first, QTabBar[dock="right"]::tab:first {{
    margin-top: 2px;
    margin-left: 0px;
}}
QTabBar[dock="left"]::tab {{
    border-radius: 0px 10px 10px 0px;
}}
QTabBar[dock="right"]::tab {{
    border-radius: 10px 0px 0px 10px;
}}
QTabBar[dock="left"]::tab:selected {{
    border-left: 2px solid {accent};
}}
QTabBar[dock="right"]::tab:selected {{
    border-right: 2px solid {accent};
}}
QTabBar[dock="left"]::close-button, QTabBar[dock="right"]::close-button {{
    padding: 2px;
}}
QTabBar[dock="left"]::scroller, QTabBar[dock="right"]::scroller {{
    width: 14px;
}}

/* ---- sidebar rail: vertical icon navigation ------------------------ */
QWidget#railColumn {{
    background: {rail_grad};
    border-right: 1px solid {hairline};
    border-radius: 0px;
}}
QPushButton#railCollapse {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {fg_muted};
    font-size: 13px;
    font-weight: 700;
    padding: 0px;
}}
QPushButton#railCollapse:hover {{
    background: {accent_soft2};
    color: {accent};
}}
QPushButton#railCollapse:pressed {{
    background: {btn_face_press};
}}
QTabBar#sideRail {{
    background: transparent;
    border: none;
}}
QTabBar#sideRail::tab {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    color: {fg_muted};
    padding: 7px 5px;
    margin: 3px 4px;
    min-height: 26px;
    min-width: 26px;
    font-size: 11px;
    font-weight: 600;
}}
QTabBar#sideRail::tab:selected {{
    background: {nav_active_grad};
    border: 1px solid {accent_line};
    color: {fg};
}}
QTabBar#sideRail::tab:hover:!selected {{
    background: {btn_face_hover};
    border: 1px solid {hairline};
    color: {fg};
}}

/* ================= Trees & lists — refined rows ===================== */
QTreeView, QListView, QTableView {{
    background: transparent;
    border: 1px solid {hairline};
    border-radius: 10px;
    padding: 4px;
    outline: none;
    alternate-background-color: {bg3};
    selection-background-color: {accent_soft2};
    selection-color: {fg};
}}
QTreeView::item, QListView::item, QTableView::item {{
    padding: 5px 8px;
    border-radius: 8px;
    min-height: 22px;
    color: {fg_dim};
    margin: 1px 2px;
}}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{
    background: {btn_face_hover};
    color: {fg};
}}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background: {accent_soft2};
    color: {fg};
}}
QTreeView::item:selected:active, QListView::item:selected:active {{
    background: {accent_soft2};
    color: {fg};
}}
QTreeView::item:selected:!active, QListView::item:selected:!active {{
    background: {accent_soft};
    color: {fg};
}}
QTreeView:focus, QListView:focus, QTableView:focus {{
    border: 1px solid {accent_line};
    outline: 2px solid {accent_ring};
    outline-offset: -1px;
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
QTreeView::branch:closed:has-children:has-siblings,
QTreeView::branch:closed:has-children:!has-siblings {{
    image: url({chev_right_url});
}}
QTreeView::branch:open:has-children:has-siblings,
QTreeView::branch:open:has-children:!has-siblings {{
    image: url({chev_down_dim_url});
}}
QHeaderView::section {{
    background: transparent;
    color: {fg_muted};
    border: none;
    border-bottom: 1px solid {border};
    padding: 8px 10px;
    font-size: 10.5px;
    font-weight: 700;
    min-height: 20px;
}}
QHeaderView::section:hover {{
    color: {fg};
    background: {accent_soft};
}}
QTableView QTableCornerButton::section {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {border};
}}
QTableView {{
    gridline-color: {border_subtle};
}}

/* ================= Splitter ========================================== */
QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:hover {{
    background: {accent_line};
}}
QSplitter::handle:pressed {{
    background: {accent};
}}
QSplitter::handle:horizontal {{
    width: 8px;
}}
QSplitter::handle:vertical {{
    height: 8px;
}}

/* ================= Scrollbars — slim overlay ======================== */
QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 4px 2px 4px 0px;
}}
QScrollBar::handle:vertical {{
    background: {panel3};
    border-radius: 6px;
    min-height: 34px;
    margin: 0px 3px;
}}
QScrollBar::handle:vertical:hover {{
    background: {accent_line};
}}
QScrollBar::handle:vertical:pressed {{
    background: {accent};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 0px 4px 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {panel3};
    border-radius: 6px;
    min-width: 34px;
    margin: 3px 0px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {accent_line};
}}
QScrollBar::handle:horizontal:pressed {{
    background: {accent};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
    border: none;
    background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ================= Status bar ======================================= */
QStatusBar {{
    background: {chrome_grad};
    border-top: 1px solid {hairline};
    min-height: 28px;
    padding: 2px 12px;
    font-size: 11.5px;
    color: {fg_muted};
}}
QStatusBar::item {{
    border: none;
}}
QStatusBar QLabel {{
    color: {fg_muted};
    padding: 0px 6px;
    font-size: 11.5px;
}}
QStatusBar QLabel#statusSession {{
    background: {accent_soft};
    color: {fg};
    border: 1px solid {accent_line};
    border-radius: 999px;
    padding: 2px 11px;
    font-size: 11px;
    font-weight: 600;
}}

/* ================= Group boxes — sectioned cards ==================== */
QGroupBox {{
    background: {card_grad};
    border: 1px solid {border};
    border-radius: 10px;
    margin-top: 16px;
    padding: 18px 14px 14px 14px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: 4px;
    padding: 2px 0px;
    color: {fg_dim};
    font-size: 11px;
    font-weight: 700;
}}
QDialog QGroupBox::title {{
    color: {fg_dim};
}}
QFormLayout QLabel {{
    color: {fg_dim};
    font-size: 12px;
    font-weight: 500;
}}

/* ================= Progress — slim accent meter ===================== */
QProgressBar {{
    background: {field_bg};
    border: 1px solid {border_subtle};
    border-radius: 999px;
    text-align: center;
    color: {fg};
    min-height: 8px;
    max-height: 10px;
    font-size: 10px;
}}
QProgressBar::chunk {{
    background: {accent_grad};
    border-radius: 999px;
}}

/* ================= Live monitor strip =============================== */
QWidget#monitorBar {{
    background: {chrome_grad};
    border-top: 1px solid {hairline};
    border-radius: 0px;
}}
QLabel#monitorTitle {{
    color: {fg};
    font-weight: 700;
    font-size: 11.5px;
}}
QLabel#monitorHost {{
    color: {fg_muted};
    font-family: {ui_mono};
    font-size: 11px;
}}
QLabel#monitorValue {{
    color: {fg_dim};
    font-family: {ui_mono};
    font-size: 11px;
    font-weight: 600;
}}
QWidget#monitorMeter QProgressBar {{
    background: {field_bg};
    border: none;
    border-radius: 999px;
    min-height: 5px;
    max-height: 5px;
}}
QWidget#monitorMeter QProgressBar::chunk {{
    background: {accent_grad};
    border-radius: 999px;
}}

/* ================= Checkboxes & radios ============================== */
QCheckBox, QRadioButton {{
    spacing: 9px;
    color: {fg_dim};
    font-size: 12.5px;
    padding: 2px 0px;
}}
QCheckBox:hover, QRadioButton:hover {{
    color: {fg};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 17px;
    height: 17px;
    border: 1px solid {border_strong};
    border-radius: 6px;
    background: {field_bg};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {accent_grad};
    border: 1px solid {accent};
    image: url({check_url});
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border: 1px solid {accent};
}}
QCheckBox::indicator:indeterminate {{
    background: {accent_soft2};
    border: 1px solid {accent};
    image: url({dot_url});
}}
QRadioButton::indicator {{
    border-radius: 999px;
}}
QRadioButton::indicator:checked {{
    background: {field_bg};
    border: 5px solid {accent};
    image: url({dot_url});
}}
QCheckBox::indicator:checked:hover {{
    border-color: {accent_hover};
}}
QRadioButton::indicator:checked:hover {{
    border-color: {accent_hover};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background: {bg3};
    border-color: {border_subtle};
}}
QCheckBox::indicator:focus, QRadioButton::indicator:focus {{
    outline: 2px solid {accent};
    outline-offset: 1px;
}}
QCheckBox:focus, QRadioButton:focus {{
    outline: 2px solid {accent};
    outline-offset: 1px;
    border-radius: 6px;
}}

/* ================= Labels & type scale ============================== */
QLabel {{
    background: transparent;
    color: {fg};
    font-size: 12.5px;
}}
QLabel#muted {{
    color: {fg_muted};
    font-size: 11.5px;
}}
QLabel#h1 {{
    color: {fg};
    font-family: {ui_display};
    font-size: 19px;
    font-weight: 700;
}}
QLabel#h2 {{
    color: {fg};
    font-size: 13.5px;
    font-weight: 700;
}}
QLabel#dialogTitle {{
    color: {fg};
    font-size: 15px;
    font-weight: 700;
}}
QLabel#caption {{
    color: {fg_muted};
    font-size: 11.5px;
}}
QLabel#dashTitle {{
    color: {fg};
    font-family: {ui_display};
    font-size: 26px;
    font-weight: 700;
}}
QLabel#dashSubtitle {{
    color: {fg_muted};
    font-size: 12.5px;
}}
QLabel#dashSection {{
    color: {fg_muted};
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.9px;
    padding: 2px 0px;
}}
QLabel#dashVersion {{
    background: {accent_soft};
    border: 1px solid {accent_line};
    border-radius: 999px;
    color: {accent};
    padding: 3px 11px;
    font-size: 10.5px;
    font-weight: 700;
}}
QLabel#cardTitle {{
    color: {fg};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#cardSub {{
    color: {fg_muted};
    font-size: 11.5px;
}}
QLabel#protoChip {{
    background: {accent_soft};
    border: 1px solid {accent_line};
    border-radius: 999px;
    color: {accent_text_soft};
    padding: 2px 9px;
    font-size: 10px;
    font-weight: 700;
}}
QLabel#tabCount {{
    background: {accent_soft2};
    border: 1px solid {accent_line};
    border-radius: 999px;
    color: {fg};
    padding: 2px 10px;
    font-size: 10.5px;
    font-weight: 700;
    min-width: 12px;
}}
QLabel#sideTitle {{
    color: {fg};
    font-size: 13.5px;
    font-weight: 700;
}}
QLabel#sideCount {{
    background: {accent_soft2};
    border: 1px solid {accent_line};
    border-radius: 999px;
    color: {accent};
    padding: 1px 8px;
    font-size: 10px;
    font-weight: 700;
    min-width: 10px;
}}
QWidget#sideHeader {{
    background: transparent;
}}
QPushButton#sideNew {{
    background: {accent_soft};
    border: 1px solid {accent_line};
    border-radius: 8px;
    padding: 0px;
}}
QPushButton#sideNew:hover {{
    background: {accent_soft2};
    border-color: {accent};
}}
QPushButton#sideNew:pressed {{
    background: {accent};
}}
QPushButton#sideNew:focus {{
    outline: 2px solid {accent};
    outline-offset: 1px;
}}
QLabel#sectionLabel {{
    color: {fg_muted};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}
QLabel#group {{
    color: {fg_dim};
    font-weight: 600;
}}

/* ================= Session tree ===================================== */
QTreeView#sessionTree {{
    background: transparent;
    border: none;
    padding: 0px;
}}
QTreeView#sessionTree::item {{
    padding: 6px 8px;
    border-radius: 8px;
    min-height: 24px;
    margin: 1px 2px;
    color: {fg_dim};
}}
QTreeView#sessionTree::item:hover {{
    background: {btn_face_hover};
    color: {fg};
}}
QTreeView#sessionTree::item:selected {{
    background: {accent_soft2};
    color: {fg};
}}
QTreeView#sessionTree::item:selected:!active {{
    background: {accent_soft};
}}
QTreeView#sessionTree::branch {{
    background: transparent;
}}

/* ================= Palette preview / keyboard hints ================= */
QLabel#pvTitle {{
    color: {fg};
    font-weight: 700;
    font-size: 12.5px;
}}
QFrame#palettePreview {{
    border-radius: 8px;
    border: 1px solid {border_strong};
    background: {panel2};
}}
QSplitter#paletteSplit::handle {{
    background: {border};
    border-radius: 6px;
}}
QLabel#pvSub {{
    color: {fg_muted};
    font-size: 11px;
}}
QLabel#pvChip {{
    background: {accent_soft};
    border: 1px solid {accent_line};
    border-radius: 999px;
    color: {accent};
    padding: 1px 8px;
    font-size: 10px;
    font-weight: 700;
}}
QLabel#pvKbd, QLabel#kbd {{
    background: {field_bg};
    border: 1px solid {border_strong};
    border-bottom: 2px solid {border_strong};
    border-radius: 6px;
    color: {fg_dim};
    padding: 2px 7px;
    font-family: {ui_mono};
    font-size: 10.5px;
    font-weight: 600;
}}
QPushButton#tabClose {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0px;
    color: {fg_muted};
}}
QPushButton#tabClose:hover {{
    background: {bad_soft};
    color: {bad};
}}
QPushButton#tabClose:pressed {{
    background: {bad_active};
    color: {bad_text};
}}
QFrame#hairline {{
    background: {hairline};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

/* ================= Session header — workspace title bar ============= */
QWidget#sessionHeader {{
    background: {chrome_grad};
    border-bottom: 1px solid {hairline};
    border-radius: 0px;
}}
QWidget#sessionHeaderLeft {{
    background: transparent;
}}
QWidget#sessionActions {{
    background: transparent;
}}
QLabel#sessionInfo {{
    color: {fg_dim};
    font-family: {ui_mono};
    font-size: 11.5px;
    font-weight: 500;
}}
QFrame#sessionSep {{
    background: {border};
    max-width: 1px;
    min-width: 1px;
    border: none;
}}
QFrame#sessionDivider {{
    background: {hairline};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QWidget#terminalContainer {{
    background: {term_bg};
}}
QWidget#terminalContent {{
    background: {term_bg};
}}
QTabWidget#sessionTabs {{
    background: transparent;
}}
QTabWidget#sessionTabs::pane {{
    background: {bg};
    border: none;
}}
QPushButton#sessionAction {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: {fg_dim};
    padding: 5px 9px;
    font-size: 11.5px;
    font-weight: 500;
}}
QPushButton#sessionAction:hover {{
    background: {btn_face_hover};
    border: 1px solid {btn_line_hover};
    color: {fg};
}}
QPushButton#sessionAction:pressed {{
    background: {btn_face_press};
    border: 1px solid {accent_line};
}}
QPushButton#sessionActionPrimary {{
    background: {accent_grad};
    border: 1px solid {accent_hover};
    border-radius: 8px;
    color: {accent_text};
    padding: 5px 13px;
    font-size: 11.5px;
    font-weight: 700;
}}
QPushButton#sessionActionPrimary:hover {{
    background: {accent_grad_hover};
}}
QPushButton#sessionActionPrimary:pressed {{
    background: {accent_grad_press};
}}
QPushButton#sessionClose {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: {fg_muted};
    padding: 5px 12px;
    font-size: 11.5px;
    font-weight: 600;
}}
QPushButton#sessionClose:hover {{
    background: {bad_soft};
    border: 1px solid {bad_line};
    color: {bad};
}}
QPushButton#sessionClose:pressed {{
    background: {bad_active};
    border-color: {bad_active};
    color: {bad_text};
}}
QPushButton#sessionClose:focus {{
    outline: 2px solid {accent};
    outline-offset: -2px;
}}

/* ================= Dialogs ========================================== */
QDialog {{
    background: {bg_grad};
}}
QDialog QLabel {{
    color: {fg};
}}
QDialogButtonBox {{
    background: transparent;
}}

/* Read-only monospace readout (RDP server manager, diagnostics) */
QPlainTextEdit#readout, QTextEdit#readout {{
    background: {term_bg};
    border: 1px solid {hairline};
    border-radius: 8px;
    color: {term_fg};
    font-family: {ui_mono};
    font-size: 12px;
    selection-background-color: {accent_soft2};
    selection-color: {fg};
    padding: 8px 10px;
}}

/* Dialog shell — one anatomy for every tool dialog */
QWidget#dialogHeader {{
    background: transparent;
}}
QLabel#dialogGlyph {{
    background: {accent_soft};
    border: 1px solid {accent_line};
    border-radius: 10px;
}}
QLabel#dialogTitle {{
    color: {fg};
    font-family: {ui_display};
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.1px;
}}
QLabel#dialogSubtitle {{
    color: {fg_muted};
    font-size: 12.5px;
}}
QWidget#dialogActions {{
    background: transparent;
    padding-top: 2px;
}}
QWidget#sectionCard {{
    background: {card_grad};
    border: 1px solid {border};
    border-radius: 10px;
}}
QWidget#sectionCard:hover {{
    border-color: {border_strong};
}}
QWidget#sectionCardHead {{
    background: transparent;
}}
QFrame#sectionRule {{
    background: {accent_grad};
    border: none;
    border-radius: 6px;
}}
QLabel#sectionCardTitle {{
    color: {fg};
    font-size: 12.5px;
    font-weight: 700;
    letter-spacing: 0.2px;
}}
QLabel#sectionCardHint {{
    color: {fg_muted};
    font-size: 11.5px;
}}
QWidget#sectionCardBody {{
    background: transparent;
}}
/* ================= Surfaces ========================================= */
QWidget#card {{
    background: {card_grad};
    border: 1px solid {border};
    border-radius: 10px;
}}
QWidget#card_hover {{
    background: {card_grad};
    border: 1px solid {border};
    border-radius: 10px;
}}
QWidget#card_hover:hover {{
    background: {card_grad_hover};
    border: 1px solid {accent_line};
}}
QWidget#header {{
    background: {chrome_grad};
    border-bottom: 1px solid {hairline};
}}
QWidget#sidebar {{
    background: {panel};
    border-right: 1px solid {hairline};
}}
QWidget#sidebar[side="right"] {{
    border-right: none;
    border-left: 1px solid {hairline};
}}
QWidget#sidebarPanel {{
    background: transparent;
}}
QWidget#workArea {{
    background: {bg};
    border-top-left-radius: 10px;
}}
QWidget#tabCorner {{
    background: transparent;
}}
QWidget#tabCornerBar {{
    background: transparent;
    border-bottom: 1px solid {hairline};
}}
QWidget#dashboard {{
    background: {bg_grad};
}}
QScrollArea#dashScroll {{
    background: {bg_grad};
    border: none;
}}
QScrollArea#dashScroll > QWidget > QWidget {{
    background: transparent;
}}
QWidget#dashHeroCard, QWidget#dashSectionQuick {{
    background: {hero_grad};
    border: 1px solid {accent_line};
    border-radius: 10px;
}}
QLabel#heroTitle {{
    color: {fg};
    font-family: {ui_display};
    font-size: 19px;
    font-weight: 700;
    letter-spacing: 0.1px;
}}
QLabel#heroSubtitle {{
    color: {fg_muted};
    font-size: 12.5px;
}}
QLineEdit#dashQuick {{
    background: {field_bg};
    border: 1px solid {border_strong};
    border-radius: 10px;
    padding: 9px 14px;
    font-size: 13.5px;
    min-height: 22px;
}}
QLineEdit#dashQuick:focus {{
    border: 1px solid {accent};
    background: {field_bg_focus};
    outline: 2px solid {accent_ring};
    outline-offset: -1px;
}}
QLineEdit#dashQuick:hover {{
    border: 1px solid {btn_line_hover};
}}
QWidget#dashTile {{
    background: {card_grad};
    border: 1px solid {border};
    border-radius: 10px;
}}
QWidget#dashTile:hover {{
    background: {card_grad_hover};
    border: 1px solid {accent_line};
}}
QWidget#dashTile:pressed {{
    background: {btn_face_press};
    border: 1px solid {accent};
}}
QWidget#dashTile:focus, QWidget#card_hover:focus {{
    outline: 2px solid {accent};
    outline-offset: 1px;
}}
QWidget#card_hover:pressed {{
    background: {btn_face_press};
}}
QLabel#dashTileIcon {{
    background: {accent_soft};
    border: 1px solid {accent_line};
    border-radius: 10px;
}}
QTabBar::close-button {{
    subcontrol-position: right;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    width: 18px;
    height: 18px;
    margin-left: 7px;
    margin-right: 2px;
}}
QTabBar::close-button:hover {{
    background: {bad_soft};
    border-color: {bad_line};
}}
QTabBar::close-button:pressed {{
    background: {bad_active};
    border-color: {bad_active};
}}

/* ================= Scroll area ====================================== */
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

/* ================= SpinBox steppers ================================= */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    background: transparent;
    border: none;
    width: 18px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-position: top right;
    border-top-right-radius: 8px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-position: bottom right;
    border-bottom-right-radius: 8px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {accent_soft};
}}
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed,
QDoubleSpinBox::up-button:pressed, QDoubleSpinBox::down-button:pressed {{
    background: {accent_soft2};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({chev_up_url});
    width: 10px;
    height: 10px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({chev_down_url});
    width: 10px;
    height: 10px;
}}

/* ================= Sliders =========================================== */
QSlider::groove:horizontal {{
    height: 5px;
    background: {field_bg};
    border: 1px solid {border_subtle};
    border-radius: 999px;
}}
QSlider::sub-page:horizontal {{
    background: {accent_grad};
    border-radius: 999px;
}}
QSlider::handle:horizontal {{
    background: {fg};
    border: 3px solid {accent};
    width: 12px;
    height: 12px;
    margin: -6px 0px;
    border-radius: 999px;
}}
QSlider::handle:horizontal:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
}}
QSlider::handle:horizontal:focus {{
    outline: 2px solid {accent};
    outline-offset: 2px;
}}

/* ================= Docks & misc ===================================== */
QDockWidget::title {{
    background: {chrome_grad};
    color: {fg};
    padding: 8px 11px;
    border-bottom: 1px solid {border};
    font-weight: 600;
}}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {hairline};
}}
QMessageBox {{
    background: {bg};
}}
QMessageBox QLabel {{
    color: {fg};
    font-size: 12.5px;
}}
"""

_QSS_COMPACT = """
/* ================= Compact density (Settings → UI) ===================== */
QWidget {{ font-size: 11.5px; }}
QMenuBar {{ min-height: 24px; padding: 2px 10px 0px 10px; }}
QMenuBar::item {{ padding: 4px 9px; }}
QMenu::item {{ padding: 5px 24px 5px 10px; }}
QToolBar {{ min-height: 34px; padding: 3px 8px; }}
QToolBar#moxaToolbar {{ min-height: 38px; padding: 3px 9px; }}
QToolBar#moxaToolbar QToolButton {{ min-height: 18px; min-width: 0px; padding: 5px 8px; font-size: 11.5px; }}
QToolButton {{ padding: 4px 7px; min-height: 18px; font-size: 11.5px; }}
QPushButton {{ padding: 5px 11px; min-height: 18px; font-size: 11.5px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    padding: 4px 8px; min-height: 18px; font-size: 11.5px;
}}
QTabBar::tab {{ padding: 6px 11px 6px 10px; min-height: 18px; font-size: 11.5px; }}
QTreeView::item, QListView::item, QTableView::item {{ padding: 3px 6px; min-height: 20px; }}
QTreeView#sessionTree::item {{ min-height: 22px; padding: 3px 6px; }}
QStatusBar {{ min-height: 24px; font-size: 11px; }}
QGroupBox {{ margin-top: 12px; padding: 14px 11px 10px 11px; }}
QCheckBox, QRadioButton {{ font-size: 11.5px; }}
QLabel#dashTitle {{ font-size: 22px; }}
QLabel#h1 {{ font-size: 17px; }}
QLabel#dashVersion {{ padding: 2px 8px; }}
QWidget#dashTile {{ border-radius: 10px; }}
"""
