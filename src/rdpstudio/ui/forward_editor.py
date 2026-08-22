"""Editor widgets for port-forward definitions — modern."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Forward


class ForwardDialog(QDialog):
    def __init__(self, fwd: Forward | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Port forward")
        self.setModal(True)
        self.setMinimumWidth(480)
        fwd = fwd or Forward()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(16)

        title = QLabel("Port Forward")
        title.setObjectName("h1")
        layout.addWidget(title)

        subtitle = QLabel("Expose a local port through SSH or forward a remote port back.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setSpacing(12)

        self.kind = QComboBox()
        self.kind.addItem("Local  (local → remote)", "local")
        self.kind.addItem("Remote  (remote → local)", "remote")
        self.kind.addItem("Dynamic (SOCKS5 proxy)", "dynamic")
        ki = self.kind.findData(fwd.kind)
        self.kind.setCurrentIndex(ki if ki >= 0 else 0)
        form.addRow("Type", self.kind)

        self.name = QLineEdit(fwd.name)
        self.name.setPlaceholderText("e.g. Web server, Database")
        form.addRow("Label", self.name)
        self.listen_host = QLineEdit(fwd.listen_host or "127.0.0.1")
        form.addRow("Listen address", self.listen_host)
        self.listen_port = QSpinBox()
        self.listen_port.setRange(0, 65535)
        self.listen_port.setSpecialValueText("auto")
        self.listen_port.setValue(fwd.listen_port)
        form.addRow("Listen port", self.listen_port)
        self.dest_host = QLineEdit(fwd.dest_host)
        self.dest_host.setPlaceholderText("e.g. localhost or 10.0.0.5")
        self.dest_port = QSpinBox()
        self.dest_port.setRange(0, 65535)
        self.dest_port.setValue(fwd.dest_port)
        dest = QHBoxLayout()
        dest.setSpacing(8)
        dest.addWidget(self.dest_host, 3)
        dest.addWidget(self.dest_port, 1)
        form.addRow("Destination", dest)
        self.enabled = QCheckBox("Enabled on connect")
        self.enabled.setChecked(fwd.enabled)
        form.addRow("", self.enabled)

        self.kind.currentIndexChanged.connect(self._on_kind)
        self._on_kind()

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_kind(self) -> None:
        dynamic = self.kind.currentData() == "dynamic"
        self.dest_host.setEnabled(not dynamic)
        self.dest_port.setEnabled(not dynamic)
        if dynamic:
            self.dest_host.setPlaceholderText("(per-connection, SOCKS5)")
        else:
            self.dest_host.setPlaceholderText("e.g. localhost or 10.0.0.5")

    def _save(self) -> None:
        if self.kind.currentData() != "dynamic" and not self.dest_host.text().strip():
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Missing destination", "A destination host is required.")
            return
        self.accept()

    def forward(self) -> Forward:
        return Forward(
            kind=self.kind.currentData(),
            name=self.name.text().strip(),
            listen_host=self.listen_host.text().strip() or "127.0.0.1",
            listen_port=self.listen_port.value(),
            dest_host=self.dest_host.text().strip(),
            dest_port=self.dest_port.value(),
            enabled=self.enabled.isChecked(),
        )


class ForwardListEditor(QWidget):
    """Table of forwards with add/edit/remove — modern."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "Forward", "Destination", "Label"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self.tree.setColumnWidth(0, 32)
        self.tree.setMinimumHeight(120)
        layout.addWidget(self.tree)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        add = QPushButton("＋ Add")
        add.setObjectName("primary")
        edit = QPushButton("Edit…")
        edit.setObjectName("subtle")
        remove = QPushButton("Remove")
        remove.setObjectName("ghost")
        toggle = QPushButton("Toggle")
        toggle.setObjectName("ghost")
        for b in (add, edit, remove, toggle):
            b.setMinimumHeight(32)
            buttons.addWidget(b)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        add.clicked.connect(self._add)
        edit.clicked.connect(self._edit)
        remove.clicked.connect(self._remove)
        toggle.clicked.connect(self._toggle)
        self.tree.itemDoubleClicked.connect(lambda *_: self._edit())

    def set_forwards(self, forwards: list[Forward]) -> None:
        self.tree.clear()
        for f in forwards:
            self._append(f)

    def get_forwards(self) -> list[Forward]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            out.append(self.tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole))
        return out

    def _append(self, f: Forward) -> None:
        icon = "●" if f.enabled else "○"
        item = QTreeWidgetItem(
            [icon, f"{f.listen_host}:{f.listen_port or 'auto'}", f.dest_label(), f.name]
        )
        item.setData(0, Qt.ItemDataRole.UserRole, f)
        self.tree.addTopLevelItem(item)

    def _current(self) -> tuple[int, Forward] | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        return self.tree.indexOfTopLevelItem(item), item.data(0, Qt.ItemDataRole.UserRole)

    def _add(self) -> None:
        dlg = ForwardDialog(parent=self)
        if dlg.exec():
            self._append(dlg.forward())

    def _edit(self) -> None:
        current = self._current()
        if not current:
            return
        idx, fwd = current
        dlg = ForwardDialog(fwd, self)
        if dlg.exec():
            self.tree.topLevelItem(idx).setData(0, Qt.ItemDataRole.UserRole, dlg.forward())
            self.set_forwards(self.get_forwards())

    def _remove(self) -> None:
        current = self._current()
        if current:
            self.tree.takeTopLevelItem(current[0])

    def _toggle(self) -> None:
        current = self._current()
        if not current:
            return
        idx, fwd = current
        fwd.enabled = not fwd.enabled
        self.set_forwards(self.get_forwards())
