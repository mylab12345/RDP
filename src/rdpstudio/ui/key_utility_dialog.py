"""SSH key utility dialog: key generator, randomart visualizer, and PuTTY PPK converter."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import paths
from ..core.plugin import SessionContext
from ..protocols.ssh import keys
from ..tools.key_converter import openssh_to_ppk, parse_key_details
from .widgets import toast


class KeyUtilityDialog(QDialog):
    """Key generator, inspector, randomart viewer, and PPK converter."""

    def __init__(self, ctx: SessionContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("SSH Key Utility & Converter")
        self.resize(840, 560)
        self.setMinimumSize(680, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("SSH Key Management & Utilities")
        title.setObjectName("h1")
        head.addWidget(title)
        head.addStretch(1)
        layout.addLayout(head)

        tabs = QTabWidget()
        tabs.addTab(self._build_inspector_tab(), "Key Inspector & Randomart")
        tabs.addTab(self._build_generator_tab(), "Key Generator")
        tabs.addTab(self._build_converter_tab(), "PuTTY PPK Converter")
        layout.addWidget(tabs, 1)

    # ------------------------------------------------------------------
    # TAB 1: Inspector & Randomart
    # ------------------------------------------------------------------
    def _build_inspector_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        ctrl = QWidget()
        ctrl.setObjectName("card")
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(8)

        self.key_path_input = QLineEdit()
        self.key_path_input.setPlaceholderText("Select private or public key file…")
        cl.addWidget(self.key_path_input, 1)

        btn_browse = QPushButton("Browse…")
        btn_browse.setObjectName("subtle")
        btn_browse.clicked.connect(self._browse_inspect_key)
        cl.addWidget(btn_browse)

        btn_inspect = QPushButton("Inspect")
        btn_inspect.setObjectName("primary")
        btn_inspect.clicked.connect(self._run_inspect)
        cl.addWidget(btn_inspect)
        layout.addWidget(ctrl)

        # Split info + randomart
        content = QHBoxLayout()

        # Left info
        info_card = QWidget()
        info_card.setObjectName("card")
        il = QFormLayout(info_card)
        il.setContentsMargins(14, 12, 14, 12)
        il.setSpacing(8)

        self.lbl_algo = QLabel("—")
        self.lbl_sha256 = QLabel("—")
        self.lbl_sha256.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_md5 = QLabel("—")
        self.lbl_md5.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.pub_key_view = QPlainTextEdit()
        self.pub_key_view.setReadOnly(True)
        self.pub_key_view.setFixedHeight(90)
        mono_font = QFont("JetBrains Mono")
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        mono_font.setPointSize(9.5)
        self.pub_key_view.setFont(mono_font)

        btn_copy_pub = QPushButton("Copy Public Key (authorized_keys)")
        btn_copy_pub.setObjectName("subtle")
        btn_copy_pub.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.pub_key_view.toPlainText()) or toast(self, "Copied public key", "good"))

        il.addRow("Algorithm:", self.lbl_algo)
        il.addRow("SHA-256:", self.lbl_sha256)
        il.addRow("MD5:", self.lbl_md5)
        il.addRow("Public Key:", self.pub_key_view)
        il.addRow("", btn_copy_pub)
        content.addWidget(info_card, 3)

        # Right randomart
        art_card = QWidget()
        art_card.setObjectName("card")
        al = QVBoxLayout(art_card)
        al.setContentsMargins(14, 12, 14, 12)
        al.setSpacing(6)
        al.addWidget(QLabel("<b>Visual Randomart:</b>"))
        self.art_view = QPlainTextEdit()
        self.art_view.setReadOnly(True)
        self.art_view.setFont(mono_font)
        al.addWidget(self.art_view, 1)
        content.addWidget(art_card, 2)

        layout.addLayout(content, 1)
        return page

    def _browse_inspect_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Key File", str(paths.keys_dir()), "All Files (*)")
        if path:
            self.key_path_input.setText(path)
            self._run_inspect()

    def _run_inspect(self) -> None:
        path = self.key_path_input.text().strip()
        if not path or not Path(path).exists():
            toast(self, "Key file not found", "warn")
            return
        try:
            details = parse_key_details(path)
            self.lbl_algo.setText(f"{details['algorithm']} ({details['bits']} bits)")
            self.lbl_sha256.setText(details["sha256"])
            self.lbl_md5.setText(details["md5"])
            self.pub_key_view.setPlainText(details["public_key"])
            self.art_view.setPlainText(details["randomart"])
            toast(self, "Key inspected successfully", "good")
        except Exception as exc:
            toast(self, f"Could not inspect key: {exc}", "bad")

    # ------------------------------------------------------------------
    # TAB 2: Generator
    # ------------------------------------------------------------------
    def _build_generator_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        card = QWidget()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        self.gen_type = QComboBox()
        self.gen_type.addItem("Ed25519 (Recommended — fast, compact, modern)", "ed25519")
        self.gen_type.addItem("RSA 4096-bit (Legacy compatibility)", "rsa")
        self.gen_type.addItem("ECDSA (NIST P-256)", "ecdsa")
        form.addRow("Key Type:", self.gen_type)

        self.gen_name = QLineEdit("id_ed25519_rdpstudio")
        form.addRow("Key Name:", self.gen_name)

        self.gen_pass = QLineEdit()
        self.gen_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.gen_pass.setPlaceholderText("Optional passphrase to encrypt private key")
        form.addRow("Passphrase:", self.gen_pass)

        btn_gen = QPushButton("⚡ Generate Key Pair")
        btn_gen.setObjectName("primary")
        btn_gen.clicked.connect(self._run_generate)
        form.addRow("", btn_gen)

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _run_generate(self) -> None:
        key_type = self.gen_type.currentData()
        name = self.gen_name.text().strip()
        passphrase = self.gen_pass.text()

        if not name:
            toast(self, "Please provide a key name", "warn")
            return

        target_path = str(paths.keys_dir() / name)
        try:
            info = keys.generate(
                target_path,
                key_type=key_type,
                bits=4096,
                passphrase=passphrase,
            )
            toast(self, f"Generated {info.key_type} key pair in {target_path}", "good")
            self.key_path_input.setText(target_path)
            self._run_inspect()
        except Exception as exc:
            toast(self, f"Generation failed: {exc}", "bad")

    # ------------------------------------------------------------------
    # TAB 3: PPK Converter
    # ------------------------------------------------------------------
    def _build_converter_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        card = QWidget()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        desc = QLabel(
            "Convert OpenSSH private keys to PuTTY's <code>.ppk</code> format for use with PuTTY, WinSCP, or FileZilla."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        form.addRow(desc)

        self.conv_src = QLineEdit()
        self.conv_src.setPlaceholderText("Source OpenSSH private key file…")
        btn_src = QPushButton("Browse…")
        btn_src.setObjectName("subtle")
        btn_src.clicked.connect(self._browse_conv_key)
        src_row = QHBoxLayout()
        src_row.addWidget(self.conv_src, 1)
        src_row.addWidget(btn_src)
        form.addRow("OpenSSH Key:", src_row)

        self.conv_comment = QLineEdit("rdpstudio-imported-key")
        form.addRow("PPK Comment:", self.conv_comment)

        btn_convert = QPushButton("Convert to .PPK & Save…")
        btn_convert.setObjectName("primary")
        btn_convert.clicked.connect(self._run_convert_ppk)
        form.addRow("", btn_convert)

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _browse_conv_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select OpenSSH Private Key", str(paths.keys_dir()), "All Files (*)")
        if path:
            self.conv_src.setText(path)

    def _run_convert_ppk(self) -> None:
        src = self.conv_src.text().strip()
        if not src or not Path(src).exists():
            toast(self, "Source key file not found", "warn")
            return
        try:
            raw_bytes = Path(src).read_bytes()
            ppk_text = openssh_to_ppk(raw_bytes, comment=self.conv_comment.text().strip() or "rdpstudio-key")
            dest, _ = QFileDialog.getSaveFileName(self, "Save PuTTY PPK File", str(Path(src).with_suffix(".ppk")), "PuTTY Private Key (*.ppk)")
            if dest:
                Path(dest).write_text(ppk_text, encoding="utf-8")
                toast(self, f"Saved PPK to {Path(dest).name}", "good")
        except Exception as exc:
            toast(self, f"Conversion failed: {exc}", "bad")
