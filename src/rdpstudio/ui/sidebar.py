"""Left sidebar: searchable tree of saved sessions — modern 2026 design."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Session
from ..core.plugin import registry
from ..core.store import SessionStore
from .theme import icon, palette

ROLE_ID = Qt.ItemDataRole.UserRole + 1
ROLE_GROUP = Qt.ItemDataRole.UserRole + 2


class SessionTree(QWidget):
    """Saved sessions with groups, search filter, context actions — modern."""

    connectRequested = Signal(str)  # session id
    editRequested = Signal(str)
    duplicateRequested = Signal(str)
    deleteRequested = Signal(str)
    sftpRequested = Signal(str)
    newFolderRequested = Signal()
    newSessionRequested = Signal()

    def __init__(self, store: SessionStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._filter = ""
        self.setObjectName("sidebar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Header
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(4, 2, 4, 2)
        title = QLabel("Sessions")
        title.setObjectName("h1")
        hl.addWidget(title)
        hl.addStretch(1)
        # Count badge
        self._count_label = QLabel("")
        self._count_label.setObjectName("caption")
        hl.addWidget(self._count_label)
        layout.addWidget(header)

        # Search — modern pill with icon
        search_wrap = QWidget()
        search_wrap.setObjectName("card")
        sl = QHBoxLayout(search_wrap)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.setSpacing(0)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Search sessions, hosts, tags…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search)
        sl.addWidget(self.search, 1)
        layout.addWidget(search_wrap)

        # Toolbar — modern icon buttons
        bar_wrap = QWidget()
        bl = QHBoxLayout(bar_wrap)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(6)

        def make_btn(text, icon_name, tip, cb):
            b = QPushButton(text)
            b.setIcon(icon(icon_name))
            b.setObjectName("subtle")
            b.setToolTip(tip)
            b.clicked.connect(cb)
            b.setMinimumHeight(32)
            return b

        btn_new = make_btn(" New", "plus", "New session (Ctrl+N)", self.newSessionRequested.emit)
        btn_folder = make_btn(" Folder", "folder", "New folder", self.newFolderRequested.emit)
        bl.addWidget(btn_new, 1)
        bl.addWidget(btn_folder, 1)
        layout.addWidget(bar_wrap)

        # Debounce typing
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self.reload)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setAnimated(True)
        self.tree.setIndentation(16)
        self.tree.setRootIsDecorated(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Modern styling tweaks
        self.tree.setStyleSheet(
            """
            QTreeView { border: none; background: transparent; }
            QTreeView::item { min-height: 32px; }
            """
        )
        layout.addWidget(self.tree, 1)

        # Footer hint — modern muted card
        hint = QFrame()
        hint.setObjectName("card")
        hint_l = QHBoxLayout(hint)
        hint_l.setContentsMargins(10, 8, 10, 8)
        self._hint = QLabel("Double-click to connect • Right-click for actions")
        self._hint.setObjectName("caption")
        self._hint.setWordWrap(True)
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
        self._count_label.setText(f"{total}" if total else "")

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
            folder = QTreeWidgetItem([f"{name}"])
            folder.setData(0, ROLE_GROUP, name)
            folder.setIcon(0, icon("folder"))
            folder.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            # Folder styling: bold-ish via tooltip
            folder.setToolTip(0, f"Folder: {name} ({len(groups[name])} sessions)")
            for s in sorted(groups[name], key=lambda x: x.display_name().lower()):
                self._add_session_item(folder, s, reg)
            folder.setExpanded(True)
            self.tree.addTopLevelItem(folder)

        # Expand all if searching
        if self._filter:
            self.tree.expandAll()

    def _add_session_item(self, parent, s: Session, reg) -> None:
        item = QTreeWidgetItem([s.display_name()])
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
        # Subtle: add host as secondary text via status tip?
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
