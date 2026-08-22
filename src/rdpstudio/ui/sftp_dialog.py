"""SFTP browser: dual-pane remote/local with transfer queue, progress, and inline editor."""

from __future__ import annotations

import posixpath
import time
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.plugin import SessionContext
from ..protocols.ssh.sftp import SftpEngine
from .file_editor_dialog import FileEditorDialog
from .widgets import format_bytes, toast

# Text / config file extensions for direct editor opening
TEXT_EXTS = {
    ".txt", ".log", ".py", ".sh", ".bash", ".conf", ".cfg", ".ini", ".yaml", ".yml",
    ".json", ".xml", ".html", ".css", ".js", ".ts", ".md", ".env", ".toml", ".service",
    ".c", ".h", ".cpp", ".rs", ".go", ".sql", ".csv", ".zsh", ".profile",
}


class _Pane(QWidget):
    """One side of the browser: path bar + list."""

    def __init__(self, title: str, is_remote: bool, parent=None) -> None:
        super().__init__(parent)
        self.is_remote = is_remote
        self.show_hidden = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        head = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setObjectName("muted")
        self.path = QLineEdit()
        self.path.returnPressed.connect(self._go)

        self.btn_up = QPushButton("↑")
        self.btn_up.setToolTip("Go to parent directory")
        self.btn_up.setFixedWidth(32)
        self.btn_up.clicked.connect(self._go_up)

        self.btn_refresh = QPushButton("↻")
        self.btn_refresh.setToolTip("Refresh (F5)")
        self.btn_refresh.setFixedWidth(32)
        self.btn_refresh.clicked.connect(self._go)

        head.addWidget(self.title)
        head.addWidget(self.path, 1)
        head.addWidget(self.btn_up)
        head.addWidget(self.btn_refresh)
        layout.addLayout(head)

        self.list = QTreeWidget()
        self.list.setHeaderLabels(["Name", "Size", "Modified"])
        self.list.setRootIsDecorated(False)
        self.list.setSortingEnabled(True)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.list, 1)

    def _go(self) -> None:
        if self.on_navigate:
            self.on_navigate(self.path.text().strip())

    def _go_up(self) -> None:
        p = self.path.text().strip()
        if not p:
            return
        if self.is_remote:
            parent = posixpath.dirname(p.rstrip("/")) or "/"
        else:
            parent = str(Path(p).parent)
        self.path.setText(parent)
        if self.on_navigate:
            self.on_navigate(parent)

    on_navigate = None  # set by owner


class SftpDialog(QDialog):
    _sigChdir = Signal(str)
    _sigList = Signal(str)
    _sigListLocal = Signal(str)
    _sigMkdir = Signal(str, str)
    _sigRemove = Signal(str, str)
    _sigRename = Signal(str, str, str)
    _sigDownload = Signal(str, str, str)
    _sigUpload = Signal(str, str, str)
    _sigReadFile = Signal(str)
    _sigWriteFile = Signal(str, bytes)

    def __init__(self, ctx: SessionContext, controller, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.controller = controller
        self.setWindowTitle(f"Files (SFTP) — {controller.definition.display_name()}")
        self.resize(1100, 660)
        self.setMinimumSize(800, 500)

        self.engine = SftpEngine(controller.transport_provider())
        self.thread = QThread(self)
        self.thread.setObjectName("sftp")
        self.engine.moveToThread(self.thread)
        self.thread.start()

        self._ops: dict[str, dict] = {}
        self._open_editors: dict[str, FileEditorDialog] = {}
        self._raw_remote_entries: list[dict] = []
        self._raw_local_entries: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        # Top toolbar
        top_bar = QHBoxLayout()
        self.chk_hidden = QCheckBox("Show Hidden Files (.*)")
        self.chk_hidden.setChecked(False)
        self.chk_hidden.toggled.connect(self._toggle_hidden)
        top_bar.addWidget(self.chk_hidden)
        top_bar.addStretch(1)

        btn_refresh_all = QPushButton("↻ Refresh Both")
        btn_refresh_all.setObjectName("subtle")
        btn_refresh_all.clicked.connect(self._refresh_all)
        top_bar.addWidget(btn_refresh_all)
        layout.addLayout(top_bar)

        # Splitter panes
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.remote = _Pane("REMOTE (SFTP)", True)
        self.local = _Pane("LOCAL", False)
        self.remote.on_navigate = lambda p: self._call("chdir", p)
        self.local.on_navigate = lambda p: self._call("list_local", p)
        splitter.addWidget(self.remote)
        splitter.addWidget(self.local)
        splitter.setSizes([550, 550])
        layout.addWidget(splitter, 1)

        # Transfer buttons
        actions = QHBoxLayout()
        download = QPushButton("⇩ Download Selected")
        download.setObjectName("primary")
        upload = QPushButton("⇧ Upload Selected")
        upload.setObjectName("primary")
        actions.addWidget(download)
        actions.addWidget(upload)
        actions.addStretch(1)
        layout.addLayout(actions)

        # Transfer queue
        self.queue = QTreeWidget()
        self.queue.setHeaderLabels(["Direction", "Files / Target", "Progress", "Speed / Rate", "Status"])
        self.queue.setRootIsDecorated(False)
        self.queue.setMaximumHeight(140)
        self.queue.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.queue)

        # Wire engine signals
        self.engine.listed.connect(self._on_listed)
        self.engine.listedLocal.connect(self._on_listed_local)
        self.engine.transferProgress.connect(self._on_progress)
        self.engine.transferDone.connect(self._on_done)
        self.engine.opDone.connect(self._on_opdone)
        self.engine.fileRead.connect(self._on_file_read)
        self.engine.fileWritten.connect(self._on_file_written)
        self.engine.failed.connect(lambda msg: toast(self, msg, "bad"))

        # Bridge signals → engine slots
        self._sigChdir.connect(self.engine.chdir)
        self._sigList.connect(self.engine.list_dir)
        self._sigListLocal.connect(self.engine.list_local)
        self._sigMkdir.connect(self.engine.mkdir)
        self._sigRemove.connect(self.engine.remove)
        self._sigRename.connect(self.engine.rename)
        self._sigDownload.connect(self.engine.download_to)
        self._sigUpload.connect(self.engine.upload_to)
        self._sigReadFile.connect(self.engine.read_file_content)
        self._sigWriteFile.connect(self.engine.write_file_content)

        # Context menus & double clicks
        self.remote.list.customContextMenuRequested.connect(lambda pos: self._menu(self.remote, pos))
        self.local.list.customContextMenuRequested.connect(lambda pos: self._menu(self.local, pos))
        self.remote.list.itemDoubleClicked.connect(lambda item, col: self._on_item_double_click(self.remote, item))
        self.local.list.itemDoubleClicked.connect(lambda item, col: self._on_item_double_click(self.local, item))

        download.clicked.connect(lambda: self._transfer("download"))
        upload.clicked.connect(lambda: self._transfer("upload"))

        # Initial directory listings
        QTimer.singleShot(80, lambda: self._call("chdir", ""))
        QTimer.singleShot(80, lambda: self._call("list_local", str(Path.home())))

    # ------------------------------------------------------------------
    def _call(self, method: str, *args) -> None:
        if method == "chdir":
            self._sigChdir.emit(str(args[0]))
        elif method == "list_dir":
            self._sigList.emit(str(args[0]))
        elif method == "list_local":
            self._sigListLocal.emit(str(args[0]))
        elif method == "mkdir":
            self._sigMkdir.emit(str(args[0]), str(args[1]))
        elif method == "remove":
            self._sigRemove.emit(str(args[0]), str(args[1]))
        elif method == "rename":
            self._sigRename.emit(str(args[0]), str(args[1]), str(args[2]))
        elif method == "download_to":
            self._sigDownload.emit(str(args[0]), str(args[1]), str(args[2]))
        elif method == "upload_to":
            self._sigUpload.emit(str(args[0]), str(args[1]), str(args[2]))
        elif method == "read_file":
            self._sigReadFile.emit(str(args[0]))
        elif method == "write_file":
            self._sigWriteFile.emit(str(args[0]), bytes(args[1]))

    def _refresh_all(self) -> None:
        self._call("list_dir", self.remote.path.text())
        self._call("list_local", self.local.path.text())

    def _toggle_hidden(self, checked: bool) -> None:
        self._render_remote_entries()
        self._render_local_entries()

    # -- listings ------------------------------------------------------------
    def _on_listed(self, path: str, entries: list[dict]) -> None:
        self.remote.path.setText(path)
        self._raw_remote_entries = entries
        self._render_remote_entries()

    def _render_remote_entries(self) -> None:
        self.remote.list.clear()
        show_hidden = self.chk_hidden.isChecked()
        for e in self._raw_remote_entries:
            if not show_hidden and e["name"].startswith(".") and e["name"] not in (".", ".."):
                continue
            item = QTreeWidgetItem(
                [
                    ("📁 " if e["is_dir"] else "📄 ") + e["name"],
                    "" if e["is_dir"] else format_bytes(e["size"]),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(e["mtime"])) if e["mtime"] else "",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, e)
            self.remote.list.addTopLevelItem(item)

    def _on_listed_local(self, path: str, entries: list[dict]) -> None:
        self.local.path.setText(path)
        self._raw_local_entries = entries
        self._render_local_entries()

    def _render_local_entries(self) -> None:
        self.local.list.clear()
        show_hidden = self.chk_hidden.isChecked()
        for e in self._raw_local_entries:
            if not show_hidden and e["name"].startswith("."):
                continue
            item = QTreeWidgetItem(
                [
                    ("📁 " if e["is_dir"] else "📄 ") + e["name"],
                    "" if e["is_dir"] else format_bytes(e["size"]),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(e["mtime"])) if e["mtime"] else "",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, e)
            self.local.list.addTopLevelItem(item)

    def _on_item_double_click(self, pane: _Pane, item: QTreeWidgetItem) -> None:
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if not entry:
            return
        if entry["is_dir"]:
            if pane.is_remote:
                new_path = posixpath.join(pane.path.text(), entry["name"])
                pane.path.setText(new_path)
                self._call("chdir", new_path)
            else:
                new_path = str(Path(pane.path.text()) / entry["name"])
                pane.path.setText(new_path)
                self._call("list_local", new_path)
        else:
            # File double click -> open in editor if text
            ext = Path(entry["name"]).suffix.lower()
            if ext in TEXT_EXTS or entry["size"] < 500_000:
                self._edit_file(pane, entry["name"])
            else:
                if pane.is_remote:
                    self._transfer("download", names=[entry["name"]])
                else:
                    self._transfer("upload", names=[entry["name"]])

    def _edit_file(self, pane: _Pane, filename: str) -> None:
        if pane.is_remote:
            full_path = posixpath.join(pane.path.text(), filename)
            toast(self, f"Loading {filename}…", "info")
            self._call("read_file", full_path)
        else:
            full_path = str(Path(pane.path.text()) / filename)
            try:
                content = Path(full_path).read_bytes()
                editor = FileEditorDialog(
                    full_path,
                    initial_content=content,
                    is_remote=False,
                    on_save=lambda p, raw: Path(p).write_bytes(raw),
                    parent=self,
                )
                editor.show()
            except Exception as exc:
                toast(self, f"Could not open file: {exc}", "bad")

    def _on_file_read(self, remote_path: str, data: bytes) -> None:
        def save_remote(p, raw_bytes):
            self._call("write_file", p, raw_bytes)

        editor = FileEditorDialog(
            remote_path,
            initial_content=data,
            is_remote=True,
            on_save=save_remote,
            parent=self,
        )
        self._open_editors[remote_path] = editor
        editor.show()

    def _on_file_written(self, remote_path: str, ok: bool, message: str) -> None:
        toast(self, f"{Path(remote_path).name}: {message}", "good" if ok else "bad")
        self._call("list_dir", self.remote.path.text())

    def _menu(self, pane: _Pane, pos) -> None:
        item = pane.list.itemAt(pos)
        if item is None:
            menu = QMenu(self)
            menu.addAction("New folder…", lambda: self._call("mkdir", pane.path.text(), self._prompt_name("Folder name")))
            menu.addAction("Refresh", lambda: pane._go())
            menu.exec(pane.list.viewport().mapToGlobal(pos))
            return

        entry = item.data(0, Qt.ItemDataRole.UserRole)
        name = entry["name"]
        menu = QMenu(self)

        if not entry["is_dir"]:
            menu.addAction("✎ Edit / View File", lambda: self._edit_file(pane, name))
            menu.addSeparator()

        if pane.is_remote:
            menu.addAction("⇩ Download…", lambda: self._transfer("download", names=[name]))
            menu.addSeparator()
            menu.addAction("New folder…", lambda: self._call("mkdir", pane.path.text(), self._prompt_name("Folder name")))
            menu.addAction("Rename…", lambda: self._call("rename", pane.path.text(), name, self._prompt_name("New name", name) or name))
            menu.addAction("Delete", lambda: self._call("remove", pane.path.text(), name))
        else:
            menu.addAction("⇧ Upload…", lambda: self._transfer("upload", names=[name]))
            menu.addSeparator()
            menu.addAction("Open in File Manager", lambda: self._reveal(pane.path.text()))
        menu.exec(pane.list.viewport().mapToGlobal(pos))

    def _reveal(self, path: str) -> None:
        import subprocess
        import sys

        if sys.platform == "win32":
            subprocess.Popen(["explorer", path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _prompt_name(self, title: str, preset: str = "") -> str:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, title, "Name:", text=preset)
        return name if ok else ""

    # -- transfers -------------------------------------------------------------
    def _selected_names(self, pane: _Pane) -> list[str]:
        names = []
        for item in pane.list.selectedItems():
            entry = item.data(0, Qt.ItemDataRole.UserRole)
            names.append(entry["name"])
        return names

    def _transfer(self, direction: str, names: list[str] | None = None) -> None:
        if direction == "download":
            names = names or self._selected_names(self.remote)
            if not names:
                toast(self, "Select remote files first", "warn")
                return
            dest = QFileDialog.getExistingDirectory(
                self, "Download to…", self.local.path.text() or str(Path.home())
            )
            if not dest:
                return
            op_id = uuid.uuid4().hex[:8]
            payload = self.remote.path.text() + "\n" + "\n".join(names)
            self._track(op_id, "download", names, dest)
            self._call("download_to", op_id, dest, payload)
        else:
            names = names or self._selected_names(self.local)
            if not names:
                toast(self, "Select local files first", "warn")
                return
            op_id = uuid.uuid4().hex[:8]
            payload = self.local.path.text() + "\n" + "\n".join(names)
            self._track(op_id, "upload", names, self.remote.path.text())
            self._call("upload_to", op_id, self.remote.path.text(), payload)

    def _track(self, op_id: str, direction: str, names: list[str], dest: str) -> None:
        arrow = "⇩ download" if direction == "download" else "⇧ upload"
        item = QTreeWidgetItem([arrow, f"{len(names)} item(s) → {dest}", "0 %", "", "running…"])
        self.queue.addTopLevelItem(item)
        self._ops[op_id] = {"item": item}

    def _on_progress(self, op_id, done, total, files, files_total, rate) -> None:
        op = self._ops.get(op_id)
        if not op:
            return
        item = op["item"]
        pct = int(done * 100 / total) if total else 0
        item.setText(2, f"{pct} %  ({format_bytes(done)} / {format_bytes(total)})")
        item.setText(3, f"{format_bytes(rate)}/s · {files}/{files_total} files")

    def _on_done(self, op_id, ok, message) -> None:
        op = self._ops.pop(op_id, None)
        if op:
            op["item"].setText(4, message)
        toast(self, message, "good" if ok else "bad")
        self._call("list_dir", self.remote.path.text())
        self._call("list_local", self.local.path.text())

    def _on_opdone(self, op, ok, message) -> None:
        if op in ("mkdir", "remove", "rename"):
            self._call("list_dir", self.remote.path.text())

    # -- close -----------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self.thread.quit()
        self.thread.wait(2000)
        super().closeEvent(event)
