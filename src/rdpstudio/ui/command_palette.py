"""Spotlight-style command palette and quick switcher — beautiful natural bento 2026."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core import paths
from .theme import icon, palette


@dataclass
class PaletteItem:
    category: str
    title: str
    subtitle: str
    action: Callable[[], Any]
    icon_name: str = "gear"
    shortcut: str = ""


def fuzzy_score(needle: str, text: str) -> int:
    """Subsequence fuzzy matcher — higher is better, 0 means no match.

    Rewards early hits, consecutive runs and word-boundary matches, so
    "nw" ranks "Network Tools" above "New Session". Pure function (tested).
    """
    needle = needle.lower()
    text = text.lower()
    if not needle:
        return 1
    if len(needle) > len(text):
        return 0
    score = 0
    ti = 0
    prev = -2
    for ch in needle:
        found = text.find(ch, ti)
        if found < 0:
            return 0
        score += max(0, 10 - found // 2)  # prefer matches near the start
        if found == prev + 1:
            score += 6  # consecutive run bonus
        if found == 0 or text[found - 1] in " \t·/_&-:(":
            score += 5  # word-boundary bonus
        prev = found
        ti = found + 1
    return score


class _PalettePreview(QFrame):
    """Right-hand preview pane — shows what the selected command will do."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("palettePreview")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(28, 28)
        lay.addWidget(self.icon_label)

        self.title = QLabel("")
        self.title.setObjectName("pvTitle")
        self.title.setWordWrap(True)
        lay.addWidget(self.title)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("pvSub")
        self.subtitle.setWordWrap(True)
        lay.addWidget(self.subtitle)

        lay.addStretch(1)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        self.chip = QLabel("")
        self.chip.setObjectName("pvChip")
        meta.addWidget(self.chip)
        self.kbd = QLabel("")
        self.kbd.setObjectName("pvKbd")
        self.kbd.setVisible(False)
        meta.addWidget(self.kbd)
        meta.addStretch(1)
        lay.addLayout(meta)

    def show_item(self, item: PaletteItem | None) -> None:
        pal = palette()
        if item is None:
            self.icon_label.setPixmap(QPixmap())
            self.title.setText("")
            self.subtitle.setText("Select a command to preview it here.")
            self.chip.setText("")
            self.kbd.setVisible(False)
            return
        self.icon_label.setPixmap(icon(item.icon_name, pal["accent"]).pixmap(QSize(28, 28)))
        self.title.setText(item.title)
        self.subtitle.setText(item.subtitle or "—")
        self.chip.setText(item.category.upper() if item.category else "")
        if item.shortcut:
            self.kbd.setText(item.shortcut)
            self.kbd.setVisible(True)
        else:
            self.kbd.setVisible(False)


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
        # Two-pane layout: results on the left, live preview on the right
        self.preview = _PalettePreview()
        split = QSplitter(Qt.Orientation.Horizontal, self.card)
        split.setObjectName("paletteSplit")
        split.setHandleWidth(8)
        split.setChildrenCollapsible(False)
        split.addWidget(self.list)
        split.addWidget(self.preview)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([400, 240])
        self.list.itemSelectionChanged.connect(self._update_preview)
        card_layout.addWidget(split, 1)

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

        self._hint = QLabel("0 commands")
        self._hint.setObjectName("caption")
        self._hint.setStyleSheet(f"color: {pal['fg_muted']}; font-size: 11px;")
        footer.addWidget(self._hint)

        card_layout.addLayout(footer)

        self._items: list[PaletteItem] = []
        self._build_items()
        self._populate_list("")
        self._update_preview()

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

        # Every real menu action becomes searchable — full menu coverage.
        mb = main.menuBar()
        for top_act in mb.actions():
            menu = top_act.menu()
            if menu is None:
                continue
            menu_title = menu.title().replace("&", "").strip()
            for act in menu.actions():
                if act.isSeparator() or not act.isEnabled() or act.menu() is not None:
                    continue
                label = act.text().replace("&", "").replace("\t", "").strip()
                if not label:
                    continue
                seqs = act.shortcuts()
                shortcut = seqs[0].toString() if seqs else ""
                self._items.append(
                    PaletteItem(
                        category=f"Menu · {menu_title}",
                        title=label,
                        subtitle="Menu command",
                        action=lambda a=act: (a.trigger(), self.accept()),
                        icon_name="gear",
                        shortcut=shortcut,
                    )
                )

    def _recents(self) -> list[PaletteItem]:
        """Recently executed commands, mapped back to live items."""
        recents = list(getattr(self.main.ctx.settings, "palette_recents", []) or [])
        by_title = {item.title: item for item in self._items}
        out: list[PaletteItem] = []
        for title in recents:
            base = by_title.get(title)
            if base is None:
                continue
            out.append(
                PaletteItem(
                    category="Recent",
                    title=base.title,
                    subtitle=base.subtitle,
                    action=base.action,
                    icon_name="clock",
                    shortcut=base.shortcut,
                )
            )
        return out

    def _populate_list(self, filter_text: str) -> None:
        self.list.clear()
        needle = filter_text.strip()

        if needle:
            scored = []
            for item in self._items:
                combined = f"{item.title} {item.subtitle} {item.category} {item.shortcut}"
                score = fuzzy_score(needle, combined)
                if score > 0:
                    scored.append((score, item))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            filtered = [item for _, item in scored]
        else:
            # No query: recents first, then everything else in build order.
            seen = set()
            filtered = []
            for item in self._recents():
                key = item.title
                if key in seen:
                    continue
                seen.add(key)
                filtered.append(item)
            for item in self._items:
                if item.title not in seen:
                    seen.add(item.title)
                    filtered.append(item)

        if not filtered:
            empty = QListWidgetItem("No matching commands")
            empty.setForeground(QColor(palette()["fg_muted"]))
            self.list.addItem(empty)
            self._hint.setText("0 matches")
            return

        for item in filtered:
            disp = f"{item.title}\n{item.subtitle}"
            if item.shortcut:
                disp += f"   [{item.shortcut}]"
            list_item = QListWidgetItem(icon(item.icon_name), disp)
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.list.addItem(list_item)

        self._hint.setText(f"{len(filtered)} command{'s' if len(filtered) != 1 else ''}")
        self.list.setCurrentRow(0)

    def _on_search(self, text: str) -> None:
        self._populate_list(text)

    def _update_preview(self) -> None:
        item = self.list.currentItem()
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.preview.show_item(data if isinstance(data, PaletteItem) else None)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        p_item: PaletteItem | None = item.data(Qt.ItemDataRole.UserRole)
        if p_item and p_item.action:
            self._remember(p_item.title)
            p_item.action()

    def _remember(self, title: str) -> None:
        """Keep the last 8 executed commands for the "Recent" section."""
        try:
            s = self.main.ctx.settings
            recents = [t for t in (getattr(s, "palette_recents", []) or []) if t != title]
            recents.insert(0, title)
            s.palette_recents = recents[:8]
            s.save(paths.settings_file())
        except Exception:
            pass

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
