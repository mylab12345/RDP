"""Spotlight-style command palette and quick switcher (Ctrl+P / Ctrl+K)."""

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
    category: str  # "Tabs" | "Sessions" | "Tools" | "Actions"
    title: str
    subtitle: str
    action: Callable[[], Any]
    icon_name: str = "gear"
    shortcut: str = ""


class CommandPaletteDialog(QDialog):
    """Modern keyboard-driven launcher & switcher."""

    def __init__(self, main_window, parent=None) -> None:
        super().__init__(parent or main_window)
        self.main = main_window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self.resize(620, 440)

        pal = palette()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        self.card = QWidget()
        self.card.setObjectName("card")
        self.card.setStyleSheet(
            f"""
            QWidget#card {{
                background: {pal['panel']};
                border: 1.5px solid {pal['border_strong']};
                border-radius: 14px;
            }}
            """
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(pal["shadow"] or "#00000066"))
        self.card.setGraphicsEffect(shadow)

        outer.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12, 12, 12, 10)
        card_layout.setSpacing(10)

        # Search bar row
        search_row = QHBoxLayout()
        search_row.setSpacing(10)

        icon_lbl = QLabel("⌕")
        icon_lbl.setObjectName("muted")
        icon_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        search_row.addWidget(icon_lbl)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search sessions, open tabs, tools, commands… (Esc to close)")
        self.search.setObjectName("search")
        self.search.setStyleSheet(
            f"""
            QLineEdit {{
                background: {pal['bg2']};
                border: 1px solid {pal['border']};
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 14px;
                color: {pal['fg']};
            }}
            QLineEdit:focus {{
                border-color: {pal['accent']};
            }}
            """
        )
        self.search.textChanged.connect(self._on_search)
        search_row.addWidget(self.search, 1)
        card_layout.addLayout(search_row)

        # Results list
        self.list = QListWidget()
        self.list.setStyleSheet(
            f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 10px;
                border-radius: 8px;
                margin: 2px 0px;
                color: {pal['fg']};
            }}
            QListWidget::item:selected {{
                background: {pal['panel2']};
                border: 1px solid {pal['accent']}55;
            }}
            """
        )
        self.list.itemActivated.connect(self._on_item_activated)
        self.list.itemClicked.connect(self._on_item_activated)
        card_layout.addWidget(self.list, 1)

        # Footer hints
        footer = QHBoxLayout()
        hint = QLabel("↑↓ Navigate  •  ⏎ Execute / Switch  •  Esc Close")
        hint.setObjectName("caption")
        hint.setStyleSheet(f"color: {pal['fg_dim']}; font-size: 11px;")
        footer.addWidget(hint)
        footer.addStretch(1)
        card_layout.addLayout(footer)

        self._items: list[PaletteItem] = []
        self._build_items()
        self._populate_list("")

    def _build_items(self) -> None:
        self._items.clear()
        main = self.main
        ctx = main.ctx

        # 1. Open tabs
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

        # 2. Saved sessions
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

        # 3. Tools & Diagnostics
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
                    title="Multi-Host Parallel Runner",
                    subtitle="Run bash/shell commands across multiple SSH hosts simultaneously",
                    action=lambda: (main.open_cluster_runner(), self.accept()),
                    icon_name="transfer",
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
                    title="Credential Vault",
                    subtitle="Encrypted credential store and master password manager",
                    action=lambda: (main.open_vault(), self.accept()),
                    icon_name="shield",
                    shortcut="Ctrl+Shift+K",
                ),
                PaletteItem(
                    category="Tools & Diagnostics",
                    title="Port Forwarding & Tunnels",
                    subtitle="Manage local, remote, and dynamic SOCKS5 proxies",
                    action=lambda: (main.open_tunnels_dialog(), self.accept()),
                    icon_name="plug",
                    shortcut="Ctrl+Shift+P",
                ),
                PaletteItem(
                    category="Tools & Diagnostics",
                    title="Remote Monitoring",
                    subtitle="Bottom live CPU, memory, disk and network monitor for SSH/OpenSSH hosts on any OS",
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

        # 4. Actions
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
                    title="Toggle Broadcast Input Mode",
                    subtitle="Mirror keystrokes across all open terminal tabs",
                    action=lambda: (main.toggle_broadcast_mode(), self.accept()),
                    icon_name="connect",
                    shortcut="Ctrl+Shift+B",
                ),
                PaletteItem(
                    category="Actions",
                    title="Toggle Snippets Panel",
                    subtitle="Show/hide command snippets drawer",
                    action=lambda: (main.toggle_snippets_panel(), self.accept()),
                    icon_name="edit",
                    shortcut="Ctrl+Shift+S",
                ),
                PaletteItem(
                    category="Actions",
                    title="Cycle theme",
                    subtitle=f"Current: {ctx.settings.theme} — dark, light, and nature palettes",
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
