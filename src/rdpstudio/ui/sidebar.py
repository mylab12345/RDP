"""Left sidebar: searchable tree of saved sessions — clean, compact, professional."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
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
from .theme import icon, palette, protocol_badge

ROLE_ID = Qt.ItemDataRole.UserRole + 1
ROLE_GROUP = Qt.ItemDataRole.UserRole + 2

_PROTO_ICONS = {"rdp": "windows", "ssh": "terminal", "local": "console"}


class SessionTree(QWidget):
    """Saved sessions with groups, search filter, context actions."""

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
        # Buttons whose icons are re-tinted on a live theme switch
        self._themed_buttons: list[tuple[QPushButton, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)

        # Header — compact title + count
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(2, 0, 2, 0)
        hl.setSpacing(8)

        title = QLabel("Sessions")
        title.setObjectName("sideTitle")
        hl.addWidget(title)
        hl.addStretch(1)

        self._count_label = QLabel("")
        self._count_label.setObjectName("sideCount")
        self._count_label.setToolTip("Number of saved sessions")
        hl.addWidget(self._count_label)
        layout.addWidget(header)

        # Search — standard input, icon inline
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Search sessions…")
        self.search.setClearButtonEnabled(True)
        self._search_action = self.search.addAction(
            icon("search"), QLineEdit.ActionPosition.LeadingPosition
        )
        self._search_action.setToolTip("Filter sessions by name, host, tag or folder")
        self.search.textChanged.connect(self._on_search)
        self.search.setFixedHeight(30)
        layout.addWidget(self.search)

        # Actions — consistent compact buttons
        bar_wrap = QWidget()
        bl = QHBoxLayout(bar_wrap)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(6)

        def make_btn(label, icon_name, tip, cb, primary=False):
            b = QPushButton(label)
            b.setIcon(icon(icon_name))
            self._themed_buttons.append((b, icon_name))
            b.setObjectName("primary" if primary else "subtle")
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(cb)
            b.setFixedHeight(28)
            return b

        btn_new = make_btn("plus", "plus", "New session (Ctrl+N)", self.newSessionRequested.emit, primary=True)
        btn_local = make_btn(
            "terminal",
            "terminal",
            "Open a local shell in a new tab (Ctrl+Shift+T)",
            self.localTerminalRequested.emit,
        )
        btn_folder = make_btn("folder", "folder", "New folder", self.newFolderRequested.emit)
        bl.addWidget(btn_new, 2)
        bl.addWidget(btn_local, 2)
        bl.addWidget(btn_folder, 1)
        layout.addWidget(bar_wrap)

        # Debounce typing
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(140)
        self._search_timer.timeout.connect(self.reload)

        # Tree — compact rows, keyboard navigable (styled via #sessionTree QSS)
        self.tree = QTreeWidget()
        self.tree.setObjectName("sessionTree")
        self.tree.setHeaderHidden(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setAnimated(False)
        self.tree.setIndentation(14)
        self.tree.setRootIsDecorated(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.tree, 1)

        # Footer hint — plain caption
        self._hint = QLabel("Double-click to connect · Right-click for actions")
        self._hint.setObjectName("caption")
        self._hint.setToolTip("Keyboard: Up/Down to move, Enter to connect, Menu key for actions")
        layout.addWidget(self._hint)

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

        # Count badge — styled by the global QSS (#sideCount)
        self._count_label.setText(str(total) if total else "")

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

        # top-level sessions first — pinned sessions float to the top
        def _sort_key(x: Session):
            return (not x.options.get("pinned", False), x.display_name().lower())

        for s in sorted(groups.get("", []), key=_sort_key):
            self._add_session_item(self.tree.invisibleRootItem(), s, reg)
        for name in sorted(g for g in groups if g):
            folder = QTreeWidgetItem([name])
            folder.setData(0, ROLE_GROUP, name)
            folder.setIcon(0, icon("folder"))
            folder.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            folder.setToolTip(0, f"Folder: {name} ({len(groups[name])} sessions)")
            for s in sorted(groups[name], key=_sort_key):
                self._add_session_item(folder, s, reg)
            folder.setExpanded(True)
            self.tree.addTopLevelItem(folder)

        if self._filter:
            self.tree.expandAll()

    def _add_session_item(self, parent, s: Session, reg) -> None:
        pinned = bool(s.options.get("pinned", False))
        label = f"★ {s.display_name()}" if pinned else s.display_name()
        item = QTreeWidgetItem([label])
        item.setData(0, ROLE_ID, s.id)
        plugin = reg.get(s.protocol)
        icon_name = plugin.icon_name if plugin else "server"
        # Protocol mini-badge: colour-coded (SSH/RDP/local) rounded tile
        item.setIcon(0, protocol_badge(s.protocol, _PROTO_ICONS.get(s.protocol, icon_name)))
        tooltip = f"{s.protocol.upper()} · {s.target()}"
        if s.description:
            tooltip += f"\n{s.description}"
        if s.tags:
            tooltip += f"\nTags: {', '.join(s.tags)}"
        if s.jump_session_id:
            tooltip += "\n(via jump host)"
        if pinned:
            tooltip += "\nPinned — right-click to unpin"
        item.setToolTip(0, tooltip)
        parent.addChild(item)

    def _on_search(self, text: str) -> None:
        self._filter = text.strip()
        self._search_timer.start()

    def refresh_theme(self) -> None:
        """Re-tint icons and protocol badges after a live theme switch."""
        # Rebuilding the tree re-renders the protocol badges and icons in
        # the new palette's colours.
        self.reload()
        self._search_action.setIcon(icon("search"))
        for btn, icon_name in self._themed_buttons:
            btn.setIcon(icon(icon_name))

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
        if item is not None:
            session_id = item.data(0, ROLE_ID)
            if session_id:
                s = self.store.get(session_id)
                pinned = bool(s and s.options.get("pinned", False))
                menu.addAction(icon("connect"), "Connect", lambda: self.connectRequested.emit(session_id))
                if s and s.protocol == "ssh":
                    menu.addAction(icon("folder"), "Browse files (SFTP)", lambda: self.sftpRequested.emit(session_id))
                pin_icon = icon("star", palette()["warn"]) if pinned else icon("star")
                menu.addAction(
                    pin_icon,
                    "Unpin session" if pinned else "Pin session",
                    lambda: self._toggle_pin(session_id),
                )
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
                    lambda: (self.store.delete_group(str(group)), self.reload()),
                )
            menu.exec(self.tree.viewport().mapToGlobal(pos))
            return
        menu.addAction(icon("plus"), "New session…", self.newSessionRequested.emit)
        menu.addAction(icon("folder"), "New folder…", self.newFolderRequested.emit)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _toggle_pin(self, session_id: str) -> None:
        s = self.store.get(session_id)
        if s is None:
            return
        s.options["pinned"] = not s.options.get("pinned", False)
        self.store.upsert(s)
        self.reload()

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
