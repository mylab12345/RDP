"""Command snippets & macros panel — 1-click execution to active terminal."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..tools.snippets import Snippet, SnippetStore
from .theme import icon
from .widgets import toast


class SnippetEditDialog(QDialog):
    """Create or edit a snippet."""

    def __init__(self, snippet: Snippet | None = None, categories: list[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.snippet = snippet or Snippet(name="", command="", category="General")
        self.setWindowTitle("New Snippet" if not snippet else f"Edit “{snippet.name}”")
        self.resize(500, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.name = QLineEdit(self.snippet.name)
        self.name.setPlaceholderText("e.g. Docker Container Stats")
        form.addRow("Name", self.name)

        self.category = QComboBox()
        self.category.setEditable(True)
        cats = categories or ["General", "System Info", "Processes", "Network", "Docker & Containers", "Disk & Storage", "Services & Logs"]
        for c in sorted(set(cats), key=str.lower):
            self.category.addItem(c)
        self.category.setCurrentText(self.snippet.category)
        form.addRow("Category", self.category)

        self.command = QPlainTextEdit(self.snippet.command)
        self.command.setPlaceholderText("e.g. docker stats --no-stream\nPlaceholders: $HOST, $USER, $PORT, $SELECTION")
        form.addRow("Command", self.command)

        self.desc = QLineEdit(self.snippet.description)
        self.desc.setPlaceholderText("Optional description")
        form.addRow("Description", self.desc)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setObjectName("subtle")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        name = self.name.text().strip()
        cmd = self.command.toPlainText().strip()
        if not name or not cmd:
            toast(self, "Name and Command are required", "warn")
            return
        self.snippet.name = name
        self.snippet.category = self.category.currentText().strip() or "General"
        self.snippet.command = cmd
        self.snippet.description = self.desc.text().strip()
        self.accept()


class SnippetsPanel(QWidget):
    """Panel with searchable command snippets and one-click execution."""

    runSnippetRequested = Signal(str)  # rendered command text

    def __init__(self, main_window, parent=None) -> None:
        super().__init__(parent or main_window)
        self.main = main_window
        self.store = SnippetStore()
        self.setObjectName("card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header
        head = QHBoxLayout()
        title = QLabel("<b>Command Snippets</b>")
        title.setObjectName("h2")
        head.addWidget(title)
        head.addStretch(1)

        btn_add = QPushButton("＋ Add")
        btn_add.setObjectName("subtle")
        btn_add.setToolTip("Create new snippet")
        btn_add.clicked.connect(self._on_add)
        head.addWidget(btn_add)
        layout.addLayout(head)

        # Search & category filter
        filter_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter snippets…")
        self.search.setObjectName("search")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._reload_tree)
        filter_row.addWidget(self.search, 1)

        self.category_filter = QComboBox()
        self.category_filter.addItem("All Categories")
        self.category_filter.currentIndexChanged.connect(self._reload_tree)
        filter_row.addWidget(self.category_filter)
        layout.addLayout(filter_row)

        # Snippets Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Snippet / Command", "Run"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAnimated(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree, 1)

        # Action bar
        act_row = QHBoxLayout()
        btn_run = QPushButton("▶ Run in Terminal")
        btn_run.setObjectName("primary")
        btn_run.setToolTip("Execute selected snippet in current active session (Enter)")
        btn_run.clicked.connect(self._on_run_selected)
        act_row.addWidget(btn_run, 1)

        btn_defaults = QPushButton("↺ Defaults")
        btn_defaults.setObjectName("ghost")
        btn_defaults.setToolTip("Reset snippets to default system administration macros")
        btn_defaults.clicked.connect(self._on_reset_defaults)
        act_row.addWidget(btn_defaults)
        layout.addLayout(act_row)

        self._refresh_categories()
        self._reload_tree()

    def _refresh_categories(self) -> None:
        current = self.category_filter.currentText()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All Categories")
        for cat in self.store.categories():
            self.category_filter.addItem(cat)
        idx = self.category_filter.findText(current)
        self.category_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.category_filter.blockSignals(False)

    def _reload_tree(self) -> None:
        self.tree.clear()
        query = self.search.text().strip().lower()
        cat_filter = self.category_filter.currentText()

        all_snippets = self.store.snippets()
        by_cat: dict[str, list[Snippet]] = {}

        for s in all_snippets:
            if cat_filter != "All Categories" and s.category != cat_filter:
                continue
            if query:
                combined = f"{s.name} {s.command} {s.category} {s.description}".lower()
                if query not in combined:
                    continue
            by_cat.setdefault(s.category, []).append(s)

        for cat_name in sorted(by_cat.keys(), key=str.lower):
            cat_item = QTreeWidgetItem([f"📁 {cat_name} ({len(by_cat[cat_name])})", ""])
            cat_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            cat_item.setExpanded(True)
            self.tree.addTopLevelItem(cat_item)

            for s in by_cat[cat_name]:
                item = QTreeWidgetItem([f"  {s.name}\n    {s.command[:60]}…", "▶"])
                item.setData(0, Qt.ItemDataRole.UserRole, s)
                item.setToolTip(0, f"Name: {s.name}\nCommand:\n{s.command}\n\nDescription: {s.description}")
                cat_item.addChild(item)

        if query:
            self.tree.expandAll()

    def _selected_snippet(self) -> Snippet | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.ItemDataRole.UserRole)

    def _on_double_click(self, item: QTreeWidgetItem, col: int) -> None:
        s: Snippet | None = item.data(0, Qt.ItemDataRole.UserRole)
        if s:
            self._execute_snippet(s)

    def _on_run_selected(self) -> None:
        s = self._selected_snippet()
        if s:
            self._execute_snippet(s)
        else:
            toast(self, "Select a snippet first", "warn")

    def _execute_snippet(self, s: Snippet) -> None:
        # Resolve variables from active session controller
        controller = self.main.current_controller()
        ctx_vars: dict[str, str] = {}
        selection = ""
        if controller:
            defn = getattr(controller, "definition", None)
            if defn:
                ctx_vars["HOST"] = defn.host or "localhost"
                ctx_vars["USER"] = defn.username or "root"
                ctx_vars["PORT"] = str(defn.port or 22)
            term = getattr(controller, "term", None)
            if term and hasattr(term, "selection"):
                selection = term.selection()
                ctx_vars["SELECTION"] = selection

        rendered = s.render(ctx_vars)
        if not rendered.endswith("\n"):
            rendered += "\n"

        # Shell-capable controllers (SSH / local terminal) implement write();
        # anything else (e.g. RDP) cannot take injected keystrokes.
        if controller is not None and controller.capabilities().shell:
            controller.write(rendered.encode("utf-8"))
            toast(self, f"Executed “{s.name}”", "good")
        else:
            toast(self, "Open a terminal session to run snippets", "warn")
            self.runSnippetRequested.emit(rendered)

    def _on_add(self) -> None:
        dlg = SnippetEditDialog(categories=self.store.categories(), parent=self)
        if dlg.exec():
            self.store.upsert(dlg.snippet)
            self._refresh_categories()
            self._reload_tree()
            toast(self, f"Added “{dlg.snippet.name}”", "good")

    def _on_edit(self, s: Snippet) -> None:
        dlg = SnippetEditDialog(snippet=s, categories=self.store.categories(), parent=self)
        if dlg.exec():
            self.store.upsert(s)
            self._refresh_categories()
            self._reload_tree()
            toast(self, f"Saved “{s.name}”", "good")

    def _on_delete(self, s: Snippet) -> None:
        self.store.delete(s.id)
        self._refresh_categories()
        self._reload_tree()
        toast(self, f"Deleted “{s.name}”", "info")

    def _on_reset_defaults(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        ans = QMessageBox.question(
            self,
            "Reset Snippets",
            "Reset all snippets to default system administration commands?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.store.reset_defaults()
            self._refresh_categories()
            self._reload_tree()
            toast(self, "Reset to default snippets", "good")

    def _context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        s: Snippet | None = item.data(0, Qt.ItemDataRole.UserRole)
        if not s:
            return
        menu = QMenu(self)
        menu.addAction("▶ Run in Active Terminal", lambda: self._execute_snippet(s))
        menu.addAction(icon("edit"), "Edit Snippet…", lambda: self._on_edit(s))
        menu.addAction(icon("trash"), "Delete Snippet", lambda: self._on_delete(s))
        menu.exec(self.tree.viewport().mapToGlobal(pos))
