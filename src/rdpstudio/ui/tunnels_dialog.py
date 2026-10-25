"""Port forwarding manager for a live SSH session."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ..core.models import Forward
from ..core.plugin import SessionContext
from .forward_editor import ForwardDialog
from .widgets import toast


class TunnelsDialog(QDialog):
    """Runtime view + control of forwards on one SSH controller."""

    def __init__(self, ctx: SessionContext, controller, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.controller = controller
        self.setWindowTitle(f"Port forwarding — {controller.definition.display_name()}")
        self.resize(760, 420)

        self.setMinimumSize(720, 400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        from .widgets import DialogActionBar, DialogHeader, SectionCard

        layout.addWidget(
            DialogHeader(
                "Port forwarding",
                controller.definition.display_name(),
                icon_name="transfer",
            )
        )

        hint = QLabel(
            "Local: your machine listens, traffic exits at the remote host.  "
            "Remote: the server listens, traffic bridges back here.  "
            "Dynamic: a SOCKS5 proxy on this machine."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        table_card = SectionCard("Forwards")
        table_card.fields.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["State", "Type", "Listen", "Destination"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(160)
        table_card.fields.addWidget(self.tree)
        layout.addWidget(table_card, 1)

        bar = DialogActionBar()
        add = QPushButton("Add forward…")
        add.setObjectName("primary")
        bar.add_left(add)

        start = QPushButton("Start")
        start.setObjectName("subtle")
        stop = QPushButton("Stop")
        stop.setObjectName("subtle")
        remove = QPushButton("Remove")
        remove.setObjectName("danger")
        bar.add(start)
        bar.add(stop)
        bar.add(remove)

        close = QPushButton("Close")
        close.setObjectName("subtle")
        close.clicked.connect(self.accept)
        bar.add(close)
        layout.addWidget(bar)

        add.clicked.connect(self._add)
        start.clicked.connect(self._start_selected)
        stop.clicked.connect(self._stop_selected)
        remove.clicked.connect(self._remove_selected)

        # live events
        controller.statusInfo.connect(self._on_status)

        self._definitions: dict[str, Forward] = {}
        self._runtime_ports: set[int] = set()
        self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> None:
        self.tree.clear()
        self._definitions = {}
        live_fn = getattr(self.controller, "live_forwards", None)
        live = {entry["port"]: entry for entry in live_fn()} if callable(live_fn) else {}
        for fwd in self.controller.definition.forwards:
            key = f"{fwd.kind}:{fwd.listen_host}:{fwd.listen_port}"
            self._definitions[key] = fwd
            self._row(fwd, running=fwd.listen_port in live)
        # Ad-hoc runtime forwards (bound to auto ports, no saved definition)
        known_ports = {f.listen_port for f in self.controller.definition.forwards}
        for port in sorted(live):
            if port in known_ports:
                continue
            entry = live[port]
            item = QTreeWidgetItem(["● active", entry.get("kind", "?"), str(port), entry.get("label", ""), ""])
            item.setForeground(0, Qt.GlobalColor.green)
            self.tree.addTopLevelItem(item)

    def _row(self, fwd: Forward, running: bool) -> None:
        state = "● active" if running else "○ idle"
        item = QTreeWidgetItem(
            [state, fwd.kind, f"{fwd.listen_host}:{fwd.listen_port}", fwd.dest_label(), fwd.name]
        )
        item.setData(0, Qt.ItemDataRole.UserRole, fwd)
        self.tree.addTopLevelItem(item)

    def _selected_forward(self) -> Forward | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.ItemDataRole.UserRole)

    # ------------------------------------------------------------------
    def _add(self) -> None:
        dlg = ForwardDialog(parent=self)
        if not dlg.exec():
            return
        fwd = dlg.forward()
        self.controller.definition.forwards.append(fwd)
        self.ctx.store.upsert(self.controller.definition)
        self._launch(fwd)
        self.reload()

    def _start_selected(self) -> None:
        fwd = self._selected_forward()
        if fwd:
            self._launch(fwd)

    def _stop_selected(self) -> None:
        fwd = self._selected_forward()
        if fwd and fwd.listen_port:
            self.controller.stop_forward(fwd.listen_port)
            toast(self, f"Stopped {fwd.label()}", "info")
            self.reload()

    def _remove_selected(self) -> None:
        fwd = self._selected_forward()
        if fwd is None:
            return
        if fwd.listen_port:
            self.controller.stop_forward(fwd.listen_port)
        try:
            self.controller.definition.forwards.remove(fwd)
        except ValueError:
            pass
        self.ctx.store.upsert(self.controller.definition)
        self.reload()

    def _launch(self, fwd: Forward) -> None:
        self.controller.start_forward(fwd.to_dict())
        toast(self, f"Starting {fwd.label()}", "info")

    def _on_status(self, info: dict) -> None:
        ev = info.get("forward")
        if not ev:
            return
        if ev.get("event") in ("started", "bound"):
            toast(self, f"Forward active: {ev.get('label') or ev.get('port')}", "good")
        elif ev.get("event") == "error":
            toast(self, f"Forward error: {ev.get('error')}", "bad")
        elif ev.get("event") == "stopped":
            toast(self, "Forward stopped", "info")
