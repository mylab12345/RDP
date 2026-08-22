"""In-app text file editor & viewer with direct SFTP save-and-upload."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .theme import palette
from .widgets import format_bytes, toast


class FileEditorDialog(QDialog):
    """In-app monospaced text editor for local and remote files."""

    saveRequested = Signal(str, bytes)  # remote_path, utf8_content_bytes

    def __init__(
        self,
        file_path: str,
        initial_content: bytes | str = b"",
        is_remote: bool = True,
        on_save: Callable[[str, bytes], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self.is_remote = is_remote
        self.on_save = on_save
        self._dirty = False

        filename = Path(file_path).name or "Untitled"
        self.setWindowTitle(f"{'Remote' if is_remote else 'Local'} File — {filename}")
        self.resize(880, 600)
        self.setMinimumSize(600, 400)

        pal = palette()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        # Header bar
        header = QHBoxLayout()
        header.setSpacing(10)

        file_icon = QLabel("📄")
        file_icon.setStyleSheet("font-size: 16px;")
        header.addWidget(file_icon)

        path_lbl = QLabel(f"<b>{filename}</b>  <span style='color: {pal['fg_dim']}; font-size: 11px;'>({file_path})</span>")
        header.addWidget(path_lbl, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("caption")
        header.addWidget(self.lbl_status)

        layout.addLayout(header)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.btn_save = QPushButton("💾 Save & Upload" if is_remote else "💾 Save")
        self.btn_save.setObjectName("primary")
        self.btn_save.setToolTip("Save changes and upload to server (Ctrl+S)")
        self.btn_save.setShortcut(QKeySequence("Ctrl+S"))
        self.btn_save.clicked.connect(self._on_save_clicked)
        toolbar.addWidget(self.btn_save)

        self.chk_wrap = QCheckBox("Word Wrap")
        self.chk_wrap.setChecked(False)
        self.chk_wrap.toggled.connect(self._toggle_wrap)
        toolbar.addWidget(self.chk_wrap)

        toolbar.addSpacing(10)

        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Find in file… (Enter/F3)")
        self.find_input.setObjectName("search")
        self.find_input.setClearButtonEnabled(True)
        self.find_input.setMaximumWidth(220)
        self.find_input.returnPressed.connect(self._find_next)
        toolbar.addWidget(self.find_input)

        btn_find_next = QPushButton("▼")
        btn_find_next.setObjectName("subtle")
        btn_find_next.setFixedWidth(30)
        btn_find_next.clicked.connect(self._find_next)
        toolbar.addWidget(btn_find_next)

        toolbar.addStretch(1)

        btn_close = QPushButton("Close")
        btn_close.setObjectName("subtle")
        btn_close.clicked.connect(self.close)
        toolbar.addWidget(btn_close)

        layout.addLayout(toolbar)

        # Editor area
        self.editor = QPlainTextEdit()
        mono_font = QFont("JetBrains Mono")
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        mono_font.setPointSize(11)
        self.editor.setFont(mono_font)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)

        if isinstance(initial_content, bytes):
            try:
                text = initial_content.decode("utf-8")
            except UnicodeDecodeError:
                text = initial_content.decode("latin1", "replace")
        else:
            text = initial_content

        self.editor.setPlainText(text)
        self.editor.textChanged.connect(self._on_content_modified)
        self.editor.cursorPositionChanged.connect(self._update_cursor_info)
        layout.addWidget(self.editor, 1)

        # Footer
        footer = QHBoxLayout()
        self.lbl_cursor = QLabel("Ln 1, Col 1")
        self.lbl_cursor.setObjectName("caption")
        self.lbl_size = QLabel(f"Size: {format_bytes(len(text.encode('utf-8')))}")
        self.lbl_size.setObjectName("caption")
        footer.addWidget(self.lbl_cursor)
        footer.addSpacing(16)
        footer.addWidget(self.lbl_size)
        footer.addStretch(1)
        layout.addLayout(footer)

    def _toggle_wrap(self, enabled: bool) -> None:
        mode = QPlainTextEdit.LineWrapMode.WidgetWidth if enabled else QPlainTextEdit.LineWrapMode.NoWrap
        self.editor.setLineWrapMode(mode)

    def _update_cursor_info(self) -> None:
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.lbl_cursor.setText(f"Ln {line}, Col {col}")

    def _on_content_modified(self) -> None:
        self._dirty = True
        self.lbl_status.setText("● Modified (unsaved)")

    def _on_save_clicked(self) -> None:
        text = self.editor.toPlainText()
        raw = text.encode("utf-8")
        self.lbl_status.setText("Saving…")
        if self.on_save:
            try:
                self.on_save(self.file_path, raw)
                self._dirty = False
                self.lbl_status.setText("✓ Saved & Uploaded")
                self.lbl_size.setText(f"Size: {format_bytes(len(raw))}")
                toast(self, f"Saved {Path(self.file_path).name}", "good")
            except Exception as e:
                self.lbl_status.setText("✕ Save failed")
                toast(self, f"Save failed: {e}", "bad")
        else:
            self.saveRequested.emit(self.file_path, raw)
            self._dirty = False
            self.lbl_status.setText("✓ Saved")
            toast(self, f"Saved {Path(self.file_path).name}", "good")

    def _find_next(self) -> None:
        query = self.find_input.text()
        if not query:
            return
        found = self.editor.find(query)
        if not found:
            # Wrap around to start of document
            cursor = self.editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
            self.editor.find(query)
