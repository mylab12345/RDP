"""In-session support chat & instant troubleshooting assistant.

Provides both an embeddable :class:`SupportChatPanel` (used inside any
:class:`SessionTab` for live in-session troubleshooting and operator chat notes)
and a standalone :class:`SupportChatDialog` accessible from the toolbar, menu,
dashboard, or shortcut (``Ctrl+Shift+H``).
"""

from __future__ import annotations

import html
import socket
import time
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..core.activity import log_activity
from .theme import icon, palette
from .widgets import PillBadge, toast


@dataclass
class ChatMessage:
    """Single message in the in-session support / troubleshooting stream."""

    sender: str  # "user" | "support" | "system"
    text: str
    ts: float = 0.0

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = time.time()


QUICK_SUPPORT_TOPICS: tuple[tuple[str, str], ...] = (
    ("diagnose", "Diagnose Connection"),
    ("rdp_help", "RDP Display / Black Screen"),
    ("auth_help", "Auth / Host Key Error"),
    ("transfer_help", "File Transfer / Drag & Drop"),
    ("reconnect", "Reconnect Session"),
)


def generate_support_reply(
    query: str,
    *,
    protocol: str = "ssh",
    host: str = "",
    port: int = 0,
    state: str = "standby",
) -> str:
    """Instant built-in troubleshooting responder for RDP, SSH, SFTP, and UI questions."""
    q = (query or "").strip().lower()
    proto = (protocol or "ssh").upper()
    target = f"{host}:{port}" if host and port else (host or "local workspace")

    if not q or "diagnose" in q or "status" in q or "check" in q:
        lines = [
            f"Live Session Diagnostics for {proto} ({target}):",
            f"• Current state: {state.upper()}",
        ]
        if host and port > 0:
            lines.append(
                f"• Tip: Click 'Ping Port' to test TCP reachability to {host}:{port}, or "
                "use Tools → Network Tools for DNS/traceroute inspection."
            )
        if proto == "RDP":
            lines.append(
                "• RDP check: Ensure TCP 3389 is reachable, NLA credentials include any "
                "DOMAIN\\username prefix if required, and Settings → RDP Display is set to "
                "'Auto' or 'External' if embedded X11 embedding is unsupported on Wayland."
            )
        else:
            lines.append(
                "• SSH/SFTP check: Verify port 22 reachability, check SSH Key Utility for "
                "loaded keys, or click Reconnect to retry."
            )
        return "\n".join(lines)

    if "rdp" in q or "black" in q or "display" in q or "resolution" in q or "freerdp" in q:
        return (
            "RDP Troubleshooting Guide:\n"
            "1. Black or blank embedded surface: Switch Settings → RDP → Client Mode to "
            "'External window' (especially on Wayland compositors without Xwayland).\n"
            "2. Certificate / NLA prompt failure: Verify username/domain format "
            "(DOMAIN\\user or user@domain) and check that FreeRDP (xfreerdp3 / xfreerdp) is installed.\n"
            "3. Dynamic resize: Enable 'Dynamic resolution' in the session's RDP options so the "
            "remote desktop adapts when you resize the tab."
        )

    if (
        "auth" in q
        or "password" in q
        or "key" in q
        or "host key" in q
        or "permission" in q
        or "refused" in q
    ):
        return (
            "Authentication & Host Key Troubleshooting:\n"
            "1. Host key changed warning: Check Settings → Security → Host Key Policy "
            "('accept-new' uses TOFU; 'strict' requires pre-trusted keys).\n"
            "2. Public key rejected: Open Tools → SSH Key Utility to generate or inspect "
            "your Ed25519/RSA key and copy the public key to ~/.ssh/authorized_keys.\n"
            "3. Connection refused / timeout: Confirm the target port and firewall rules "
            "using 'Ping Port' or Tools → Network Tools."
        )

    if "transfer" in q or "sftp" in q or "drag" in q or "drop" in q or "upload" in q or "file" in q:
        return (
            "File Transfer & Drag-and-Drop Help:\n"
            "• Direct drop: Drag files or folders from your desktop file manager directly "
            "onto an open SSH/SFTP tab or into the SFTP Browser drop zone.\n"
            "• Visual progress: Active uploads/downloads display a real-time progress bar "
            "with byte rate and Cancel button.\n"
            "• Engine fallback: If a host lacks an SFTP subsystem, switch Settings → Files → "
            "Transfer Protocol to 'SCP'."
        )

    if "theme" in q or "dark" in q or "light" in q or "font" in q or "zoom" in q:
        return (
            "Themes & Font Accessibility:\n"
            "• Press Ctrl+Shift+L (or click the Theme button in the toolbar/status bar) "
            "to toggle between Dark and Light mode instantly.\n"
            "• Press Ctrl++ / Ctrl+- / Ctrl+0 (or use A- / A+ in the status bar) to adjust "
            "font sizes across terminals and UI controls."
        )

    if "mobile" in q or "tablet" in q or "touch" in q or "small" in q or "responsive" in q:
        return (
            "Mobile & Tablet Touch Mode:\n"
            "• Press Ctrl+Shift+M (or View → Mobile / Touch Mode) to enable larger touch "
            "targets, compact icon-first toolbars, and auto-collapsed side panels."
        )

    if "feedback" in q or "bug" in q or "suggest" in q or "feature" in q:
        return (
            "You can submit a feature request or bug report directly from this panel using "
            "the 'Send as Feedback…' button below, or press Ctrl+Shift+F at any time."
        )

    return (
        f"Recorded note for {proto} ({target}).\n"
        "• Need connection diagnostics? Click 'Diagnose Connection' or 'Ping Port'.\n"
        "• Having display/auth/transfer issues? Use the quick topic chips above or click "
        "'Send as Feedback…' to share this transcript with your improvement suggestion."
    )


class SupportChatPanel(QFrame):
    """Interactive in-session chat and instant troubleshooting panel."""

    feedbackRequested = Signal(str)
    reconnectRequested = Signal()
    closeRequested = Signal()

    def __init__(
        self,
        *,
        session_name: str = "Workspace",
        protocol: str = "ssh",
        host: str = "",
        port: int = 0,
        state: str = "standby",
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("supportChatPanel")
        self.session_name = session_name
        self.protocol = protocol
        self.host = host
        self.port = port
        self.state = state
        self.messages: list[ChatMessage] = []

        root = QVBoxLayout(self)
        pad = 10 if compact else 14
        root.setContentsMargins(pad, pad, pad, pad)
        root.setSpacing(8)

        # ── Header bar ──
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        title = QLabel("In-Session Support & Troubleshooting Chat")
        title.setObjectName("h2")
        hdr.addWidget(title)

        self.context_badge = PillBadge(self._context_label(), "accent")
        self.context_badge.setObjectName("supportContextBadge")
        hdr.addWidget(self.context_badge)
        hdr.addStretch(1)

        self.btn_ping = QPushButton("Ping Port")
        self.btn_ping.setObjectName("subtle")
        self.btn_ping.setToolTip("Test TCP reachability to the current session host:port")
        self.btn_ping.clicked.connect(self.run_port_check)
        self.btn_ping.setVisible(bool(self.host))
        hdr.addWidget(self.btn_ping)

        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setObjectName("subtle")
        self.btn_copy.setToolTip("Copy troubleshooting transcript to clipboard")
        self.btn_copy.clicked.connect(self.copy_transcript)
        hdr.addWidget(self.btn_copy)

        if compact:
            self.btn_hide = QPushButton("×")
            self.btn_hide.setObjectName("subtle")
            self.btn_hide.setFixedWidth(28)
            self.btn_hide.setToolTip("Hide in-session support panel")
            self.btn_hide.clicked.connect(self.closeRequested.emit)
            hdr.addWidget(self.btn_hide)
        root.addLayout(hdr)

        # ── Quick Topic Chips ──
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        self.topic_buttons: dict[str, QPushButton] = {}
        for topic_id, label in QUICK_SUPPORT_TOPICS:
            btn = QPushButton(label)
            btn.setObjectName("subtle")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, tid=topic_id, lbl=label: self._on_quick_topic(tid, lbl))
            self.topic_buttons[topic_id] = btn
            chips_row.addWidget(btn)
        chips_row.addStretch(1)
        root.addLayout(chips_row)

        # ── Transcript view ──
        self.transcript = QTextBrowser()
        self.transcript.setObjectName("supportTranscript")
        self.transcript.setOpenExternalLinks(False)
        if compact:
            self.transcript.setMinimumHeight(130)
            self.transcript.setMaximumHeight(200)
        else:
            self.transcript.setMinimumHeight(240)
        root.addWidget(self.transcript, 1)

        # ── Input row ──
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setObjectName("supportChatInput")
        self.input.setPlaceholderText(
            "Ask a troubleshooting question (e.g. 'RDP black screen', 'auth error') or log a session note…"
        )
        self.input.returnPressed.connect(self.send_current_message)
        input_row.addWidget(self.input, 1)

        self.btn_send = QPushButton("Send")
        self.btn_send.setObjectName("primary")
        self.btn_send.clicked.connect(self.send_current_message)
        input_row.addWidget(self.btn_send)

        self.btn_feedback = QPushButton("Send as Feedback…")
        self.btn_feedback.setObjectName("subtle")
        self.btn_feedback.setToolTip("Open the Feedback dialog pre-filled with your latest message")
        self.btn_feedback.clicked.connect(self._emit_feedback)
        input_row.addWidget(self.btn_feedback)
        root.addLayout(input_row)

        self._append_message(
            "support",
            f"Hi! I'm your in-session support assistant for {self._context_label()}. "
            "Ask any question below or click a quick troubleshooting chip above.",
        )

    def _context_label(self) -> str:
        proto = (self.protocol or "ssh").upper()
        if self.host:
            return f"{proto} · {self.host}" + (f":{self.port}" if self.port else "")
        return f"{proto} · {self.session_name}"

    def update_session_context(
        self,
        *,
        session_name: str | None = None,
        protocol: str | None = None,
        host: str | None = None,
        port: int | None = None,
        state: str | None = None,
    ) -> None:
        if session_name is not None:
            self.session_name = session_name
        if protocol is not None:
            self.protocol = protocol
        if host is not None:
            self.host = host
        if port is not None:
            self.port = port
        if state is not None:
            self.state = state
        self.context_badge.setText(self._context_label())
        self.btn_ping.setVisible(bool(self.host))

    def _append_message(self, sender: str, text: str) -> ChatMessage:
        msg = ChatMessage(sender=sender, text=text)
        self.messages.append(msg)
        self._render_messages()
        return msg

    def _render_messages(self) -> None:
        pal = palette()
        blocks: list[str] = []
        for msg in self.messages:
            stamp = time.strftime("%H:%M:%S", time.localtime(msg.ts))
            if msg.sender == "user":
                who = "You"
                color = pal["accent"]
                bg = pal.get("bg3", pal["bg"])
            elif msg.sender == "system":
                who = "Diagnostics"
                color = pal["info"]
                bg = pal.get("bg2", pal["bg"])
            else:
                who = "Support Assistant"
                color = pal["good"]
                bg = pal.get("bg2", pal["bg"])
            safe = html.escape(msg.text).replace("\n", "<br>")
            blocks.append(
                f"<div style='background:{bg}; border-radius:6px; padding:8px 10px; margin-bottom:6px;'>"
                f"<div style='font-size:8.5pt; color:{pal['fg_dim']};'>"
                f"<b style='color:{color};'>{who}</b> &nbsp;·&nbsp; {stamp}</div>"
                f"<div style='margin-top:3px; color:{pal['fg']};'>{safe}</div>"
                f"</div>"
            )
        self.transcript.setHtml("".join(blocks))
        sb = self.transcript.verticalScrollBar()
        sb.setValue(sb.maximum())

    def send_message(self, text: str) -> str:
        clean = (text or "").strip()
        if not clean:
            return ""
        self._append_message("user", clean)
        log_activity(
            "support",
            "In-session support message",
            clean[:200],
            level="info",
            session=self.session_name,
            protocol=self.protocol,
        )
        reply = generate_support_reply(
            clean,
            protocol=self.protocol,
            host=self.host,
            port=self.port,
            state=self.state,
        )
        self._append_message("support", reply)
        return reply

    def send_current_message(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.send_message(text)

    def _on_quick_topic(self, topic_id: str, label: str) -> None:
        if topic_id == "reconnect":
            self._append_message("system", "Triggering session reconnect…")
            self.reconnectRequested.emit()
            return
        query_map = {
            "diagnose": "diagnose connection status",
            "rdp_help": "rdp display black screen help",
            "auth_help": "authentication or host key error",
            "transfer_help": "file transfer sftp drag and drop",
        }
        self.send_message(query_map.get(topic_id, label))

    def run_port_check(self) -> bool:
        """Run a quick non-blocking TCP reachability probe on ``self.host:self.port``."""
        if not self.host:
            self._append_message("system", "No remote host is associated with this session.")
            return False
        default_port = 3389 if (self.protocol or "").lower() == "rdp" else 22
        target_port = self.port or default_port
        t0 = time.monotonic()
        ok = False
        detail = ""
        try:
            with socket.create_connection((self.host, target_port), timeout=1.5):
                ok = True
                ms = int((time.monotonic() - t0) * 1000)
                detail = f"TCP {self.host}:{target_port} is REACHABLE ({ms} ms)."
        except OSError as exc:
            detail = f"TCP {self.host}:{target_port} is UNREACHABLE ({exc})."
        self._append_message("system", detail)
        log_activity(
            "support",
            f"Port probe {'succeeded' if ok else 'failed'}",
            detail,
            level="good" if ok else "warn",
            session=self.session_name,
            protocol=self.protocol,
        )
        return ok

    def copy_transcript(self) -> None:
        lines = [
            f"[{time.strftime('%H:%M:%S', time.localtime(m.ts))}] {m.sender.upper()}: {m.text}"
            for m in self.messages
        ]
        QGuiApplication.clipboard().setText("\n".join(lines))
        toast(self, "Support chat transcript copied", "info")

    def _emit_feedback(self) -> None:
        user_msgs = [m.text for m in self.messages if m.sender == "user"]
        prefill = user_msgs[-1] if user_msgs else ""
        self.feedbackRequested.emit(prefill)


class SupportChatDialog(QDialog):
    """Standalone dialog wrapper around :class:`SupportChatPanel`."""

    def __init__(self, main_window=None, parent=None) -> None:
        super().__init__(parent or main_window)
        self.main = main_window
        self.setWindowTitle("In-Session Support & Troubleshooting Chat")
        self.setObjectName("supportChatDialog")
        self.resize(680, 520)
        self.setMinimumSize(480, 380)

        session_name = "Workspace"
        protocol = "ssh"
        host = ""
        port = 0
        state = "standby"
        if main_window is not None and hasattr(main_window, "_current_session_tab"):
            tab = main_window._current_session_tab()
            if tab is not None:
                defn = tab.controller.definition
                session_name = defn.display_name()
                protocol = defn.protocol
                host = defn.host
                port = defn.port
                state = tab.controller.state()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)

        self.panel = SupportChatPanel(
            session_name=session_name,
            protocol=protocol,
            host=host,
            port=port,
            state=state,
            compact=False,
            parent=self,
        )
        self.panel.feedbackRequested.connect(self._on_feedback)
        self.panel.reconnectRequested.connect(self._on_reconnect)
        root.addWidget(self.panel, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.setObjectName("subtle")
        btn_close.setIcon(icon("close"))
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        root.addLayout(footer)

    def _on_feedback(self, prefill: str) -> None:
        if self.main is not None and hasattr(self.main, "open_feedback_dialog"):
            self.main.open_feedback_dialog(prefill_description=prefill, category="bug")

    def _on_reconnect(self) -> None:
        if self.main is not None and hasattr(self.main, "_reconnect_current"):
            self.main._reconnect_current()
            toast(self, "Reconnecting current session…", "info")
