"""Per-tab command line (history recall + send bar), from main_window.py.

Moved verbatim (ARCH-02); ``main_window.py`` re-exports both names.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget


class _HistoryLineEdit(QLineEdit):
    """QLineEdit with MobaXterm-style Up/Down command-history recall."""

    _HISTORY_MAX = 100

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.history: list[str] = []
        self._hist_idx = -1
        self._draft = ""

    def remember(self, text: str) -> None:
        if not self.history or self.history[-1] != text:
            self.history.append(text)
            if len(self.history) > self._HISTORY_MAX:
                self.history.pop(0)
        self._hist_idx = -1
        self._draft = ""

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Up and self.history:
            if self._hist_idx == -1:
                self._draft = self.text()
                self._hist_idx = len(self.history) - 1
            elif self._hist_idx > 0:
                self._hist_idx -= 1
            self.setText(self.history[self._hist_idx])
            self.setCursorPosition(len(self.text()))
            event.accept()
            return
        if event.key() == Qt.Key.Key_Down and self._hist_idx != -1:
            if self._hist_idx < len(self.history) - 1:
                self._hist_idx += 1
                self.setText(self.history[self._hist_idx])
            else:
                self._hist_idx = -1
                self.setText(self._draft)
            self.setCursorPosition(len(self.text()))
            event.accept()
            return
        super().keyPressEvent(event)


class CommandBar(QWidget):
    """Per-tab command line (MobaXterm: plain \"Command:\" strip under the terminal)."""

    commandSent = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("commandBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        prompt = QLabel("Command:")
        prompt.setObjectName("commandPrompt")
        layout.addWidget(prompt)

        self.line = _HistoryLineEdit()
        self.line.setObjectName("commandLine")
        self.line.setPlaceholderText("Type a command and press Enter  (Up/Down: history)")
        self.line.setClearButtonEnabled(True)
        self.line.returnPressed.connect(self._on_return)
        layout.addWidget(self.line, 1)

    def _on_return(self) -> None:
        text = self.line.text().strip()
        if not text:
            return
        self.line.remember(text)
        self.line.clear()
        self.commandSent.emit(text)

    @property
    def history(self) -> list[str]:
        return self.line.history
