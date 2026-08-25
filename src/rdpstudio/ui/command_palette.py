"""Spotlight-style command palette and quick switcher — beautiful natural bento 2026."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import icon, palette


@dataclass
class PaletteItem:
    category: str
    title: str
    subtitle: str
    action: Callable[[], Any]
    icon_name: str = "gear"
    shortcut: str = ""


class CommandPaletteDialog(QDialog):
    """Modern keyboard-driven launcher — natural bento, soft shadows."""

    def __init__(self, main_window, parent=None) -> None:
        super().__init__(parent or main_window)
        self.main = main_window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self.resize(680, 480)

        pal = palette()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)

        self.card = QWidget()
        self.card.setObjectName("card")
        self.card.setStyleSheet(
            f"""
            QWidget#card {{
                background: {pal['bg2']};
                border: 1px solid {pal['border']};
                border-radius: 6px;
            }}
            """
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(pal["shadow"] or "#00000066"))
        self.card.setGraphicsEffect(shadow)

        outer.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(16, 16, 16, 14)
        card_layout.setSpacing(14)

        # Search bar row — pill, natural
        search_row = QWidget()
        search_row.setObjectName("searchRow")
        search_row.setStyleSheet(
            f"""
            QWidget#searchRow {{
                background: {pal['bg3']};
                border: 1px solid {pal['border_subtle']};
                border-radius: 8px;
            }}
            QWidget#searchRow:focus-within {{
                border-color: {pal['accent']};
                background: {pal['bg2']};
            }}
            """
        )
        sr_l = QHBoxLayout(search_row)
        sr_l.setContentsMargins(6, 6, 6, 6)
        sr_l.setSpacing(10)

        icon_lbl = QLabel("⌕")
        icon_lbl.setStyleSheet(f"color: {pal['accent']}; font-size: 18px; font-weight: 800; padding-left: 8px;")
        sr_l.addWidget(icon_lbl)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search sessions, tabs, tools, commands…")
        self.search.setObjectName("paletteSearch")
        self.search.setStyleSheet(
            f"""
            QLineEdit#paletteSearch {{
                background: transparent;
                border: none;
                padding: 10px 8px;
                font-size: 15px;
                color: {pal['fg']};
            }}
            """
        )
        self.search.textChanged.connect(self._on_search)
        sr_l.addWidget(self.search, 1)

        esc_hint = QLabel("Esc")
        esc_hint.setStyleSheet(
            f"""
            background: {pal['panel2']};
            border: 1px solid {pal['border']};
            border-radius: 6px;
            padding: 3px 8px;
            color: {pal['fg_dim']};
            font-size: 11px;
            font-weight: 600;
            """
        )
        sr_l.addWidget(esc_hint)

        card_layout.addWidget(search_row)

        # Results list — bento cards
        self.list = QListWidget()
        self.list.setStyleSheet(
            f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 12px 14px;
                border-radius: 6px;
                margin: 3px 2px;
                color: {pal['fg']};
                border: 1px solid transparent;
            }}
            QListWidget::item:hover {{
                background: {pal['bg3']};
                border-color: {pal['border_subtle']};
            }}
            QListWidget::item:selected {{
                background: {pal['accent_subtle']};
                border: 1px solid {pal['accent']}40;
                color: {pal['fg']};
            }}
            """
        )
        self.list.itemActivated.connect(self._on_item_activated)
        self.list.itemClicked.connect(self._on_item_activated)
        card_layout.addWidget(self.list, 1)

        # Footer hints — pill badges
        footer = QHBoxLayout()
        footer.setSpacing(8)

        def footer_pill(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"""
                background: {pal['bg3']};
                border: 1px solid {pal['border_subtle']};
                border-radius: 6px;
                padding: 4px 10px;
                color: {pal['fg_dim']};
                font-size: 11px;
                font-weight: 600;
                """
            )
            return lbl

        footer.addWidget(footer_pill("↑↓ Navigate"))
        footer.addWidget(footer_pill("⏎ Execute"))
        footer.addWidget(footer_pill("Esc Close"))
        footer.addStretch(1)

        hint = QLabel(f"{len(self._items) if hasattr(self, '_items') else 0} commands")
        hint.setObjectName("caption")
        hint.setStyleSheet(f"color: {pal['fg_muted']}; font-size: 11px;")
        footer.addWidget(hint)

        card_layout.addLayout(footer)

        self._items: list[PaletteItem] = []
        self._build_items()
        self._populate_list("")

    def _build_items(self) -> None:
        self._items.clear()
        main = self.main
        ctx = main.ctx

        for i in range(main.tabs.count()):
            tab_title = main.tabs.tabText(i)
            widget = main.tabs.widget(i)
            sub = "Active tab"
            if hasattr(widget, "controller"):
                c = widget.controller
                sub = f"{c.definition.protocol.upper()} · {c.definition.target()}"
            self._items.append(
                PaletteItem(
                    category="Open Tabs",
                    title=f"Switch to: {tab_title}",
                    subtitle=sub,
                    action=lambda idx=i: (main.tabs.setCurrentIndex(idx), self.accept()),
                    icon_name="console",
                    shortcut=f"Tab #{i + 1}",
                )
            )

        for s in ctx.store.sessions():
            self._items.append(
                PaletteItem(
                    category="Saved Sessions",
                    title=f"Connect: {s.display_name()}",
                    subtitle=f"{s.protocol.upper()} · {s.target()}" + (f" · {s.group}" if s.group else ""),
                    action=lambda sid=s.id: (main.connect_session(sid), self.accept()),
                    icon_name="connect" if s.protocol == "ssh" else ("windows" if s.protocol == "rdp" else "terminal"),
                )
            )

        self._items.extend(
            [
                PaletteItem(
                    category="Tools & Diagnostics",
                    title="Network Tools & Port Scanner",
                    subtitle="TCP port scanner, ping latency probe, DNS diagnostics",
                    action=lambda: (main.open_network_tools(), self.accept()),
                    icon_name="server",
                ),
                PaletteItem(
                    category="Tools & Diagnostics",
                    title="SSH Key Utility & Converter",
                    subtitle="Key generator, randomart visualizer, and PuTTY PPK converter",
                    action=lambda: (main.open_key_utility(), self.accept()),
                    icon_name="key",
                ),
                PaletteItem(
                    category="Tools & Diagnostics",
                    title="Remote Monitoring",
                    subtitle="Bottom live CPU, memory, disk and network monitor",
                    action=lambda: (main.open_monitor_dialog(), self.accept()),
                    icon_name="server",
                    shortcut="Ctrl+Shift+M",
                ),
                PaletteItem(
                    category="Tools & Diagnostics",
                    title="RDP Server Manager",
                    subtitle="Check and enable/disable local machine RDP listener",
                    action=lambda: (main.open_rdp_server_manager(), self.accept()),
                    icon_name="windows",
                ),
            ]
        )

        self._items.extend(
            [
                PaletteItem(
                    category="Actions",
                    title="New Session…",
                    subtitle="Create a new saved SSH or RDP connection",
                    action=lambda: (main.new_session(), self.accept()),
                    icon_name="plus",
                    shortcut="Ctrl+N",
                ),
                PaletteItem(
                    category="Actions",
                    title="New Local Terminal",
                    subtitle="Open a native local shell tab",
                    action=lambda: (main.open_local_terminal(), self.accept()),
                    icon_name="console",
                    shortcut="Ctrl+Shift+T",
                ),
                PaletteItem(
                    category="Actions",
                    title="Cycle theme",
                    subtitle=f"Current: {ctx.settings.theme} — explore natural palettes",
                    action=lambda: (main.cycle_theme(), self.accept()),
                    icon_name="gear",
                ),
                PaletteItem(
                    category="Actions",
                    title="Settings…",
                    subtitle="Preferences, terminal fonts, and nature themes",
                    action=lambda: (main.open_settings(), self.accept()),
                    icon_name="gear",
                    shortcut="Ctrl+,",
                ),
                PaletteItem(
                    category="Actions",
                    title="Import from ~/.ssh/config",
                    subtitle="Import hosts from default SSH config file",
                    action=lambda: (main._import_ssh_config(), self.accept()),
                    icon_name="folder",
                ),
                PaletteItem(
                    category="Actions",
                    title="Export Sessions to JSON",
                    subtitle="Export saved sessions (passwords excluded)",
                    action=lambda: (main._export_json(), self.accept()),
                    icon_name="transfer",
                ),
            ]
        )

    def _populate_list(self, filter_text: str) -> None:
        self.list.clear()
        needle = filter_text.strip().lower()

        filtered: list[PaletteItem] = []
        for item in self._items:
            if not needle:
                filtered.append(item)
            else:
                combined = f"{item.category} {item.title} {item.subtitle} {item.shortcut}".lower()
                if needle in combined:
                    filtered.append(item)

        for item in filtered:
            disp = f"{item.title}\n{item.subtitle}"
            if item.shortcut:
                disp += f"   [{item.shortcut}]"
            list_item = QListWidgetItem(icon(item.icon_name), disp)
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.list.addItem(list_item)

        if self.list.count() > 0:
            self.list.setCurrentRow(0)

    def _on_search(self, text: str) -> None:
        self._populate_list(text)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        p_item: PaletteItem | None = item.data(Qt.ItemDataRole.UserRole)
        if p_item and p_item.action:
            p_item.action()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            row = self.list.currentRow()
            count = self.list.count()
            if count > 0:
                if event.key() == Qt.Key.Key_Down:
                    self.list.setCurrentRow((row + 1) % count)
                else:
                    self.list.setCurrentRow((row - 1 + count) % count)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.list.currentItem()
            if item is not None:
                self._on_item_activated(item)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)
