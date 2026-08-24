"""Left sidebar: searchable tree of saved sessions — beautiful natural bento design 2026."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Session
from ..core.plugin import registry
from ..core.store import SessionStore
from .theme import icon, palette
from .widgets import PillBadge

ROLE_ID = Qt.ItemDataRole.UserRole + 1
ROLE_GROUP = Qt.ItemDataRole.UserRole + 2


class SessionTree(QWidget):
    """Saved sessions with groups, search filter, context actions — natural bento."""

    connectRequested = Signal(str)  # session id
    editRequested = Signal(str)
    duplicateRequested = Signal(str)
    deleteRequested = Signal(str)
    sftpRequested = Signal(str)
    newFolderRequested = Signal()
    newSessionRequested = Signal()
    localTerminalRequested = Signal()

    def __init__(self, store: SessionStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._filter = ""
        self.setObjectName("sidebar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(14)

        # Header — natural, with accent dot
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(4, 2, 4, 2)
        hl.setSpacing(8)

        dot = QLabel("◉")
        pal = palette()
        dot.setStyleSheet(f"color: {pal['accent']}; font-size: 14px;")
        hl.addWidget(dot)

        title = QLabel("Sessions")
        title.setObjectName("h1")
        title.setStyleSheet("font-size: 18px; font-weight: 800; letter-spacing: -0.3px;")
        hl.addWidget(title)
        hl.addStretch(1)

        # Count badge — pill
        self._count_label = QLabel("")
        self._count_label.setObjectName("countBadge")
        hl.addWidget(self._count_label)
        layout.addWidget(header)

        # Search — pill, soft, natural
        search_wrap = QWidget()
        search_wrap.setObjectName("searchWrap")
        pal = palette()
        search_wrap.setStyleSheet(
            f"""
            QWidget#searchWrap {{
                background: {pal['bg2']};
                border: 1.5px solid {pal['border']};
                border-radius: 22px;
            }}
            QWidget#searchWrap:focus-within {{
                border-color: {pal['accent']};
            }}
            """
        )
        sl = QHBoxLayout(search_wrap)
        sl.setContentsMargins(6, 4, 6, 4)
        sl.setSpacing(6)

        search_icon = QLabel("⌕")
        search_icon.setStyleSheet(f"color: {pal['fg_dim']}; font-size: 14px; padding-left: 6px;")
        sl.addWidget(search_icon)

        self.search = QLineEdit()
        self.search.setObjectName("searchInner")
        self.search.setPlaceholderText("Search sessions…")
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet(
            f"""
            QLineEdit#searchInner {{
                background: transparent;
                border: none;
                padding: 6px 8px;
                font-size: 13px;
                color: {pal['fg']};
            }}
            """
        )
        self.search.textChanged.connect(self._on_search)
        sl.addWidget(self.search, 1)
        layout.addWidget(search_wrap)

        # Toolbar — bento pill buttons
        bar_wrap = QWidget()
        bl = QHBoxLayout(bar_wrap)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)

        def make_btn(text, icon_name, tip, cb, primary=False):
            b = QPushButton(text)
            b.setIcon(icon(icon_name))
            b.setObjectName("primary" if primary else "subtle")
            b.setToolTip(tip)
            b.clicked.connect(cb)
            b.setMinimumHeight(36)
            b.setStyleSheet(
                f"""
                QPushButton {{
                    border-radius: 11px;
                    padding: 6px 12px;
                    font-weight: 600;
                    font-size: 12.5px;
                }}
                """
            )
            return b

        btn_new = make_btn(" New", "plus", "New session (Ctrl+N)", self.newSessionRequested.emit, primary=True)
        btn_local = make_btn(
            " Term",
            "console",
            "Open a local shell in a new tab (Ctrl+Shift+T)",
            self.localTerminalRequested.emit,
        )
        btn_folder = make_btn(" Folder", "folder", "New folder", self.newFolderRequested.emit)
        bl.addWidget(btn_new, 1)
        bl.addWidget(btn_local, 1)
        bl.addWidget(btn_folder, 1)
        layout.addWidget(bar_wrap)

        # Debounce typing
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(140)
        self._search_timer.timeout.connect(self.reload)

        # Tree — bento cards
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setAnimated(True)
        self.tree.setIndentation(18)
        self.tree.setRootIsDecorated(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tree.setStyleSheet(
            f"""
            QTreeView {{
                border: none;
                background: transparent;
                outline: none;
            }}
            QTreeView::item {{
                min-height: 38px;
                border-radius: 11px;
                margin: 2px 4px;
                padding: 6px 8px;
                border: 1px solid transparent;
            }}
            QTreeView::item:hover {{
                background: {pal['bg3']};
                border-color: {pal['border_subtle']};
            }}
            QTreeView::item:selected {{
                background: {pal['accent']};
                color: {pal['accent_text']};
                border-color: {pal['accent']};
            }}
            QTreeView::branch {{
                background: transparent;
            }}
            """
        )
        layout.addWidget(self.tree, 1)

        # Footer hint — bento card
        hint = QFrame()
        hint.setObjectName("card")
        pal = palette()
        hint.setStyleSheet(
            f"""
            QFrame#card {{
                background: {pal['bg3']};
                border: 1px solid {pal['border_subtle']};
                border-radius: 12px;
            }}
            """
        )
        hint_l = QHBoxLayout(hint)
        hint_l.setContentsMargins(12, 10, 12, 10)
        self._hint = QLabel("Double-click to connect  •  Right-click for actions")
        self._hint.setObjectName("caption")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(f"font-size: 11px; color: {pal['fg_dim']};")
        hint_l.addWidget(self._hint)
        layout.addWidget(hint)

        self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> None:
        self.tree.setUpdatesEnabled(False)
        try:
            self._reload()
        finally:
            self.tree.setUpdatesEnabled(True)

    def _reload(self) -> None:
        self.tree.clear()
        reg = registry()
        sessions = self.store.sessions()
        total = len(sessions)

        # Update count badge with pill styling
        pal = palette()
        if total:
            self._count_label.setText(f"{total}")
            self._count_label.setStyleSheet(
                f"""
                QLabel {{
                    background: {pal['accent_subtle']};
                    color: {pal['accent']};
                    border: 1px solid {pal['accent']}30;
                    border-radius: 20px;
                    padding: 2px 10px;
                    font-size: 11px;
                    font-weight: 700;
                }}
                """
            )
        else:
            self._count_label.setText("")
            self._count_label.setStyleSheet("")

        if self._filter:
            needle = self._filter.lower()
            sessions = [
                s for s in sessions
                if needle in s.display_name().lower()
                or needle in (s.host or "").lower()
                or needle in " ".join(s.tags).lower()
                or needle in s.group.lower()
            ]

        groups: dict[str, list[Session]] = {}
        for s in sessions:
            groups.setdefault(s.group or "", []).append(s)

        # top-level sessions first
        for s in sorted(groups.get("", []), key=lambda x: x.display_name().lower()):
            self._add_session_item(self.tree.invisibleRootItem(), s, reg)
        for name in sorted(g for g in groups if g):
            folder = QTreeWidgetItem([f"  {name}"])
            folder.setData(0, ROLE_GROUP, name)
            folder.setIcon(0, icon("folder"))
            folder.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            folder.setToolTip(0, f"Folder: {name} ({len(groups[name])} sessions)")
            for s in sorted(groups[name], key=lambda x: x.display_name().lower()):
                self._add_session_item(folder, s, reg)
            folder.setExpanded(True)
            self.tree.addTopLevelItem(folder)

        if self._filter:
            self.tree.expandAll()

    def _add_session_item(self, parent, s: Session, reg) -> None:
        # Natural: show name with subtle protocol indicator
        item = QTreeWidgetItem([f"  {s.display_name()}"])
        item.setData(0, ROLE_ID, s.id)
        icon_name = reg.get(s.protocol).icon_name if reg.get(s.protocol) else "server"
        item.setIcon(0, icon(icon_name))
        tooltip = f"{s.protocol.upper()} · {s.target()}"
        if s.description:
            tooltip += f"\n{s.description}"
        if s.tags:
            tooltip += f"\nTags: {', '.join(s.tags)}"
        if s.jump_session_id:
            tooltip += "\n(via jump host)"
        item.setToolTip(0, tooltip)
        parent.addChild(item)

    def _on_search(self, text: str) -> None:
        self._filter = text.strip()
        self._search_timer.start()

    # -- events -----------------------------------------------------------
    def _double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        session_id = item.data(0, ROLE_ID)
        if session_id:
            self.connectRequested.emit(session_id)

    def selected_session_id(self) -> str | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.data(0, ROLE_ID)

    def selected_group(self) -> str:
        item = self.tree.currentItem()
        if item is None:
            return ""
        group = item.data(0, ROLE_GROUP)
        if group:
            return str(group)
        session_id = item.data(0, ROLE_ID)
        if session_id:
            s = self.store.get(session_id)
            if s:
                return s.group
        return ""

    def _context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        pal = palette()
        menu.setStyleSheet(
            f"""
            QMenu {{
                background: {pal['bg2']};
                border: 1.5px solid {pal['border']};
                border-radius: 14px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 9px 14px;
                border-radius: 10px;
                margin: 1px 2px;
            }}
            QMenu::item:selected {{
                background: {pal['accent_subtle']};
            }}
            """
        )
        if item is not None:
            session_id = item.data(0, ROLE_ID)
            if session_id:
                s = self.store.get(session_id)
                menu.addAction(icon("connect"), "Connect", lambda: self.connectRequested.emit(session_id))
                if s and s.protocol == "ssh":
                    menu.addAction(icon("folder"), "Browse files (SFTP)", lambda: self.sftpRequested.emit(session_id))
                menu.addSeparator()
                menu.addAction(icon("edit"), "Edit…", lambda: self.editRequested.emit(session_id))
                menu.addAction(icon("plus"), "Duplicate", lambda: self.duplicateRequested.emit(session_id))
                menu.addSeparator()
                menu.addAction(icon("trash"), "Delete", lambda: self.deleteRequested.emit(session_id))
            elif item.data(0, ROLE_GROUP):
                group = item.data(0, ROLE_GROUP)
                menu.addAction(
                    icon("edit"),
                    "Rename folder…",
                    lambda: self._rename_group(str(group)),
                )
                menu.addAction(
                    icon("trash"),
                    "Delete folder",
                    lambda: self.store.delete_group(str(group)) or self.reload(),
                )
            menu.exec(self.tree.viewport().mapToGlobal(pos))
            return
        menu.addAction(icon("plus"), "New session…", self.newSessionRequested.emit)
        menu.addAction(icon("folder"), "New folder…", self.newFolderRequested.emit)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _rename_group(self, group: str) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Rename folder", "New name:", text=group)
        if ok and name:
            self.store.rename_group(group, name)
            self.reload()

    def prompt_new_folder(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "New folder", "Folder name:")
        if ok and name:
            self.store.ensure_group(name)
            self.reload()
