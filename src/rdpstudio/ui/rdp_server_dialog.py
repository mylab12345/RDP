"""RDP server manager: local machine's RDP listener status + controls."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..protocols.rdp import servermgr
from .theme import icon


class RdpServerDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("RDP server manager")
        self.setModal(True)
        self.resize(640, 420)

        self.setMinimumSize(560, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        from .widgets import DialogActionBar, DialogHeader, SectionCard

        layout.addWidget(
            DialogHeader(
                "Local RDP server",
                "Share this machine's desktop over RDP. Enabling or disabling "
                "the service needs administrator rights.",
                icon_name="windows",
            )
        )

        status_card = SectionCard("Service status", "live")
        self.status = QPlainTextEdit()
        self.status.setObjectName("readout")
        self.status.setReadOnly(True)
        self.status.setMinimumHeight(120)
        status_card.fields.addWidget(self.status)
        layout.addWidget(status_card, 1)

        bar = DialogActionBar()
        self.btn_refresh = QPushButton(icon("clock"), "Refresh")
        self.btn_refresh.setObjectName("subtle")
        self.btn_refresh.clicked.connect(self.refresh)
        bar.add_left(self.btn_refresh)

        self.btn_enable = QPushButton(icon("connect"), "Enable…")
        self.btn_enable.setObjectName("primary")
        self.btn_enable.setToolTip("Start the RDP listener (requires elevation)")
        self.btn_enable.clicked.connect(lambda: self._apply("enable"))
        bar.add(self.btn_enable, primary=True)

        self.btn_disable = QPushButton(icon("stop"), "Disable…")
        self.btn_disable.setObjectName("subtle")
        self.btn_disable.setToolTip("Stop the RDP listener (requires elevation)")
        self.btn_disable.clicked.connect(lambda: self._apply("disable"))
        bar.add(self.btn_disable)

        close = QPushButton("Close")
        close.setObjectName("subtle")
        close.clicked.connect(self.accept)
        bar.add(close)
        layout.addWidget(bar)

        self.refresh()

    def refresh(self) -> None:
        self.st = servermgr.status()
        lines = [
            f"Platform supported : {'yes' if self.st.supported else 'no'}",
            f"Service present    : {'yes' if self.st.service_present else 'no'}",
            f"Enabled            : {'yes' if self.st.enabled else 'no'}",
            f"Port {self.st.port:<14}: {'listening' if self.st.listening else 'not listening'}",
            "",
            self.st.detail,
        ]
        self.status.setPlainText("\n".join(lines))
        has_cmds = bool(self.st.commands)
        self.btn_enable.setEnabled(has_cmds)
        self.btn_disable.setEnabled(has_cmds)

    def _apply(self, which: str) -> None:
        if not self.st or not self.st.commands:
            return
        command = self.st.commands[which]
        btn = QMessageBox.question(
            self,
            "Apply privileged change",
            f"Run the following command now?\n\n{command}\n\n"
            "This requires administrator/sudo rights.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if btn != QMessageBox.StandardButton.Yes:
            return
        import subprocess
        import sys

        try:
            if sys.platform == "win32":
                # elevate via ShellExecute runas
                import ctypes

                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", "cmd.exe", f"/c {command}", None, 0  # type: ignore[arg-type]
                )
            else:
                import shutil as _sh

                if _sh.which("pkexec"):
                    cmd = command.replace("sudo ", "")
                    proc = subprocess.run(
                        ["pkexec", "sh", "-c", cmd],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        check=False,
                    )
                else:
                    proc = subprocess.run(
                        ["sh", "-c", command],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        check=False,
                    )
                if proc.returncode != 0:
                    QMessageBox.warning(
                        self, "Failed", proc.stderr or proc.stdout or "unknown error"
                    )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Failed", str(exc))
        self.refresh()
