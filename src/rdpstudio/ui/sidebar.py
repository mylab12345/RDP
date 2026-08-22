"""Left sidebar: searchable tree of saved sessions grouped in folders."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Session
from ..core.plugin import registry
from ..core.store import SessionStore
from .theme import icon

ROLE_ID = Qt.ItemDataRole.UserRole + 1
ROLE_GROUP = Qt.ItemDataRole.UserRole + 2


class SessionTree(QWidget):
    """Saved sessions with groups, search filter, context actions."""

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        bar = QToolBar()
        new_btn = bar.addAction(icon("plus"), "New session")
        new_btn.triggered.connect(self.newSessionRequested.emit)
        new_folder = bar.addAction(icon("folder"), "New folder")
        new_folder.triggered.connect(self.newFolderRequested.emit)
        layout.addWidget(bar)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search sessions…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search)
        layout.addWidget(self.search)

        # Debounce typing: every keystroke used to re-read the store and
        # rebuild the whole tree, which is visibly janky with many sessions.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self.reload)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        layout.addWidget(self.tree, 1)

        hint = QFrame()
        hint.setObjectName("muted")
        hint_l = QHBoxLayout(hint)
        from PySide6.QtWidgets import QLabel

        self._hint = QLabel("Double-click to connect")
        self._hint.setObjectName("muted")
        hint_l.addWidget(self._hint)
        layout.addWidget(hint)

        self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> None:
        # setUpdatesEnabled(False) collapses N item insertions into a single
        # repaint/relayout instead of one per row.
        self.tree.setUpdatesEnabled(False)
        try:
            self._reload()
        finally:
            self.tree.setUpdatesEnabled(True)

    def _reload(self) -> None:
        self.tree.clear()
        reg = registry()
        sessions = self.store.sessions()
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
        for s in groups.get("", []):
            self._add_session_item(self.tree.invisibleRootItem(), s, reg)
        for name in sorted(g for g in groups if g):
            folder = QTreeWidgetItem([f"📁 {name}"])
            folder.setData(0, ROLE_GROUP, name)
            folder.setIcon(0, icon("folder"))
            folder.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for s in groups[name]:
                self._add_session_item(folder, s, reg)
            folder.setExpanded(True)
            self.tree.addTopLevelItem(folder)

    def _add_session_item(self, parent, s: Session, reg) -> None:
        item = QTreeWidgetItem([s.display_name()])
        item.setData(0, ROLE_ID, s.id)
        item.setIcon(0, icon(reg.get(s.protocol).icon_name if reg.get(s.protocol) else "server"))
        tooltip = f"{s.protocol.upper()} · {s.target()}"
        if s.description:
            tooltip += f"\n{s.description}"
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
        if item is not None:
            session_id = item.data(0, ROLE_ID)
            if session_id:
                s = self.store.get(session_id)
                menu.addAction("Connect", lambda: self.connectRequested.emit(session_id))
                if s and s.protocol == "ssh":
                    menu.addAction("Browse files (SFTP)", lambda: self.sftpRequested.emit(session_id))
                menu.addSeparator()
                menu.addAction("Edit…", lambda: self.editRequested.emit(session_id))
                menu.addAction("Duplicate", lambda: self.duplicateRequested.emit(session_id))
                menu.addSeparator()
                menu.addAction("Delete", lambda: self.deleteRequested.emit(session_id))
            elif item.data(0, ROLE_GROUP):
                group = item.data(0, ROLE_GROUP)

                menu.addAction(
                    "Rename folder…",
                    lambda: self._rename_group(str(group)),
                )
                menu.addAction(
                    "Delete folder",
                    lambda: self.store.delete_group(str(group)) or self.reload(),
                )
            menu.exec(self.tree.viewport().mapToGlobal(pos))
            return
        menu.addAction("New session…", self.newSessionRequested.emit)
        menu.addAction("New folder…", self.newFolderRequested.emit)
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
