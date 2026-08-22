"""RDP server manager: local machine's RDP listener status + controls."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
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

        layout = QVBoxLayout(self)
        head = QLabel("<b>Local RDP server</b>")
        layout.addWidget(head)

        self.status = QPlainTextEdit()
        self.status.setReadOnly(True)
        layout.addWidget(self.status, 1)

        buttons = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_enable = QPushButton(icon("connect"), "Enable (elevated)")
        self.btn_enable.clicked.connect(lambda: self._apply("enable"))
        self.btn_disable = QPushButton(icon("stop"), "Disable (elevated)")
        self.btn_disable.clicked.connect(lambda: self._apply("disable"))
        buttons.addWidget(self.btn_refresh)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_enable)
        buttons.addWidget(self.btn_disable)
        layout.addLayout(buttons)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.clicked.connect(self.accept)
        layout.addWidget(close)

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
                        ["pkexec", "sh", "-c", cmd], capture_output=True, text=True, timeout=120
                    )
                else:
                    proc = subprocess.run(
                        ["sh", "-c", command], capture_output=True, text=True, timeout=120
                    )
                if proc.returncode != 0:
                    QMessageBox.warning(
                        self, "Failed", proc.stderr or proc.stdout or "unknown error"
                    )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Failed", str(exc))
        self.refresh()
