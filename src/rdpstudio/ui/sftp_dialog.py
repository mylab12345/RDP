"""SFTP browser: dual-pane remote/local with transfer queue and progress."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
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

from ..core import paths
from ..core.plugin import SessionContext
from ..protocols.ssh.sftp import SftpEngine
from .widgets import format_bytes, toast


class _Pane(QWidget):
    """One side of the browser: path bar + list."""

    def __init__(self, title: str, is_remote: bool, parent=None) -> None:
        super().__init__(parent)
        self.is_remote = is_remote
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        head = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setObjectName("muted")
        self.path = QLineEdit()
        self.path.returnPressed.connect(self._go)
        self.up = QPushButton("↑")
        self.up.setFixedWidth(34)
        self.up.clicked.connect(self._go_up)
        head.addWidget(self.title)
        head.addWidget(self.path, 1)
        head.addWidget(self.up)
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
        self.on_navigate(self.path.text().strip())

    def _go_up(self) -> None:
        p = self.path.text().strip()
        if not p:
            return
        if self.is_remote:
            parent = p.rsplit("/", 1)[0] or "/"
        else:
            parent = str(Path(p).parent)
        self.path.setText(parent)
        self.on_navigate(parent)

    on_navigate = None  # set by owner


class SftpDialog(QDialog):
    # cross-thread bridges to the engine (auto → queued connections)
    _sigChdir = Signal(str)
    _sigList = Signal(str)
    _sigListLocal = Signal(str)
    _sigMkdir = Signal(str, str)
    _sigRemove = Signal(str, str)
    _sigRename = Signal(str, str, str)
    _sigDownload = Signal(str, str, str)
    _sigUpload = Signal(str, str, str)

    def __init__(self, ctx: SessionContext, controller, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.controller = controller
        self.setWindowTitle(f"Files — {controller.definition.display_name()}")
        self.resize(1080, 640)

        self.engine = SftpEngine(controller.transport_provider())
        self.thread = QThread(self)
        self.thread.setObjectName("sftp")
        self.engine.moveToThread(self.thread)
        self.thread.start()

        self._ops: dict[str, dict] = {}

        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.remote = _Pane("REMOTE (SFTP)", True)
        self.local = _Pane("LOCAL", False)
        self.remote.on_navigate = lambda p: self._call("chdir", p)
        self.local.on_navigate = lambda p: self._call("list_local", p)
        splitter.addWidget(self.remote)
        splitter.addWidget(self.local)
        splitter.setSizes([540, 540])
        layout.addWidget(splitter, 1)

        # transfer buttons
        actions = QHBoxLayout()
        download = QPushButton("⇩  Download selected")
        upload = QPushButton("⇧  Upload selected")
        actions.addWidget(download)
        actions.addWidget(upload)
        actions.addStretch(1)
        layout.addLayout(actions)

        # transfer queue
        self.queue = QTreeWidget()
        self.queue.setHeaderLabels(["Direction", "Files", "Progress", "Speed", "Status"])
        self.queue.setRootIsDecorated(False)
        self.queue.setMaximumHeight(150)
        layout.addWidget(self.queue)

        # wire engine signals
        self.engine.listed.connect(self._on_listed)
        self.engine.listedLocal.connect(self._on_listed_local)
        self.engine.transferProgress.connect(self._on_progress)
        self.engine.transferDone.connect(self._on_done)
        self.engine.opDone.connect(self._on_opdone)
        self.engine.failed.connect(lambda msg: toast(self, msg, "bad"))

        # bridge signals → engine slots
        self._sigChdir.connect(self.engine.chdir)
        self._sigList.connect(self.engine.list_dir)
        self._sigListLocal.connect(self.engine.list_local)
        self._sigMkdir.connect(self.engine.mkdir)
        self._sigRemove.connect(self.engine.remove)
        self._sigRename.connect(self.engine.rename)
        self._sigDownload.connect(self.engine.download_to)
        self._sigUpload.connect(self.engine.upload_to)

        # context menus
        self.remote.list.customContextMenuRequested.connect(lambda pos: self._menu(self.remote, pos))
        self.local.list.customContextMenuRequested.connect(lambda pos: self._menu(self.local, pos))

        download.clicked.connect(lambda: self._transfer("download"))
        upload.clicked.connect(lambda: self._transfer("upload"))

        # initial listings
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

    # -- listings ------------------------------------------------------------
    def _on_listed(self, path: str, entries: list[dict]) -> None:
        self.remote.path.setText(path)
        self.remote.list.clear()
        for e in entries:
            item = QTreeWidgetItem(
                [
                    ("📁 " if e["is_dir"] else "   ") + e["name"],
                    "" if e["is_dir"] else format_bytes(e["size"]),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(e["mtime"])) if e["mtime"] else "",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, e)
            self.remote.list.addTopLevelItem(item)

    def _on_listed_local(self, path: str, entries: list[dict]) -> None:
        self.local.path.setText(path)
        self.local.list.clear()
        for e in entries:
            item = QTreeWidgetItem(
                [
                    ("📁 " if e["is_dir"] else "   ") + e["name"],
                    "" if e["is_dir"] else format_bytes(e["size"]),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(e["mtime"])) if e["mtime"] else "",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, e)
            self.local.list.addTopLevelItem(item)

    def _menu(self, pane: _Pane, pos) -> None:
        item = pane.list.itemAt(pos)
        if item is None:
            return
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        name = entry["name"]
        menu = QMenu(self)
        if pane.is_remote:
            menu.addAction("Download…", lambda: self._transfer("download", names=[name]))
            menu.addAction("New folder", lambda: self._call("mkdir", pane.path.text(), self._prompt_name("Folder name")))
            menu.addAction("Rename", lambda: self._call("rename", pane.path.text(), name, self._prompt_name("New name", name) or name))
            menu.addAction("Delete", lambda: self._call("remove", pane.path.text(), name))
        else:
            menu.addAction("Upload…", lambda: self._transfer("upload", names=[name]))
            menu.addAction("Open in file manager", lambda: paths and self._reveal(pane.path.text()))
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
        item = QTreeWidgetItem([arrow, f"{len(names)} → {dest}", "0 %", "", "running…"])
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
        if op == "mkdir":
            self._call("list_dir", self.remote.path.text())

    # -- close -----------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self.thread.quit()
        self.thread.wait(2000)
        super().closeEvent(event)
