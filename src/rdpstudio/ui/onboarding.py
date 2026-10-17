"""Interactive tooltips and step-by-step onboarding guide for new users."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import badge_icon, palette
from .widgets import PillBadge, toast


@dataclass(frozen=True)
class OnboardingStep:
    """One step in the interactive onboarding walkthrough."""

    id: str
    title: str
    subtitle: str
    icon_name: str
    tone: str
    highlights: tuple[str, ...]
    shortcut_hint: str
    try_label: str = ""
    try_action_attr: str = ""


ONBOARDING_STEPS: tuple[OnboardingStep, ...] = (
    OnboardingStep(
        id="dashboard_rdp",
        title="1. Simplified Dashboard & One-Click RDP Access",
        subtitle=(
            "The home dashboard gives you immediate access to RDP desktops, SSH shells, "
            "SFTP transfers, and saved server workspaces."
        ),
        icon_name="windows",
        tone="accent",
        highlights=(
            "Use the RDP Quick Feature Bar at the top of the dashboard to launch a Windows/Linux RDP desktop, scan for RDP hosts on your LAN, or open a local shell.",
            "Click any Quick Connect protocol pill (SSH, RDP, SFTP, Mosh) to pre-fill the target box and connect with Enter.",
            "Customise which sections and launcher tiles appear via the 'Customise' button.",
        ),
        shortcut_hint="Ctrl+Shift+R — New RDP Session",
        try_label="Open RDP Session Dialog",
        try_action_attr="new_rdp_session",
    ),
    OnboardingStep(
        id="quick_connect",
        title="2. Quick-Connect Panel & Frequent Servers",
        subtitle=(
            "Connect to your favourite and most-visited servers in a single click from "
            "both the dashboard and the sidebar."
        ),
        icon_name="connect",
        tone="good",
        highlights=(
            "Frequent & Pinned Servers appear as one-click chips in the sidebar and on the home dashboard, ranked automatically by how often you connect.",
            "Right-click any session in the sidebar or dashboard to Pin/Unpin, Duplicate, Copy Host, Launch SFTP, or Reconnect.",
            "Filter saved sessions instantly by name, hostname, protocol, or tag using Ctrl+F.",
        ),
        shortcut_hint="Ctrl+K — Command Palette",
        try_label="Open Command Palette",
        try_action_attr="open_command_palette",
    ),
    OnboardingStep(
        id="file_transfer",
        title="3. Seamless Drag-and-Drop File Transfer",
        subtitle=(
            "Drop files or folders from your desktop directly onto a session tab or the "
            "dual-pane SFTP browser with live visual progress bars."
        ),
        icon_name="folder",
        tone="info",
        highlights=(
            "Drag local files onto any SSH/SFTP session tab to upload them immediately with a visual progress bar, byte rate, and ETA.",
            "In the SFTP Browser, drag files between Local and Remote panes or drop files from your OS file manager onto the drop zone banner.",
            "Cancel or inspect any transfer in real time from the transfer progress bar.",
        ),
        shortcut_hint="Drag & Drop files onto any session",
        try_label="View Activity & Transfers",
        try_action_attr="open_activity_log",
    ),
    OnboardingStep(
        id="themes_accessibility",
        title="4. Customisable Themes (Dark/Light) & Font Scaling",
        subtitle=(
            "Switch between Dark and Light modes or scale terminal and UI fonts on the "
            "fly for optimal readability and accessibility."
        ),
        icon_name="star",
        tone="accent",
        highlights=(
            "Click the Theme toggle in the toolbar or status bar (Ctrl+Alt+T) to switch between Dark and Light themes at any time.",
            "Adjust font size with Ctrl++ / Ctrl+- / Ctrl+0 or the A- / A+ controls in the status bar.",
            "Choose from 7 curated colour palettes and custom accent colours in Settings (Ctrl+,).",
        ),
        shortcut_hint="Ctrl+Alt+T — Toggle Dark/Light Mode",
        try_label="Toggle Dark / Light Theme",
        try_action_attr="toggle_dark_light_theme",
    ),
    OnboardingStep(
        id="shortcuts_mobile",
        title="5. Keyboard Shortcuts, Context Menus & Mobile Mode",
        subtitle=(
            "Speed up daily workflows with keyboard shortcuts, rich right-click context "
            "menus, and responsive tablet/smartphone touch layout."
        ),
        icon_name="key",
        tone="warn",
        highlights=(
            "Right-click anywhere on the dashboard, session tabs, or sidebar for context-aware actions.",
            "When resizing to compact tablet/phone dimensions (or toggling Mobile/Touch Mode with Ctrl+Shift+M), the sidebar auto-collapses and touch-friendly controls appear.",
            "Press F1 at any time to browse the Keyboard Shortcuts reference.",
        ),
        shortcut_hint="F1 — Keyboard Shortcuts Reference",
        try_label="Browse Keyboard Shortcuts",
        try_action_attr="open_shortcuts",
    ),
    OnboardingStep(
        id="support_feedback",
        title="6. Live Activity Logs, In-Session Support Chat & Feedback",
        subtitle=(
            "Monitor real-time connection health, troubleshoot issues with the built-in "
            "support assistant, and share feedback directly from the UI."
        ),
        icon_name="shield",
        tone="good",
        highlights=(
            "Click the live status indicator or Activity badge in the status bar (Ctrl+Shift+A) to inspect real-time connection events.",
            "Use the In-Session Support & Chat assistant (Ctrl+Shift+H) for instant RDP/SSH troubleshooting, port checks, and one-click auto-remediation.",
            "Click the Feedback button in the toolbar or status bar (Ctrl+Shift+I) to suggest improvements.",
        ),
        shortcut_hint="Ctrl+Shift+H — Support Chat · Ctrl+Shift+I — Feedback",
        try_label="Open Support Assistant",
        try_action_attr="open_support_chat",
    ),
)


def format_interactive_tooltip(
    title: str,
    description: str,
    *,
    shortcut: str = "",
    tip: str = "",
) -> str:
    """Build a rich, accessible HTML tooltip with optional shortcut and pro-tip."""
    pal = palette()
    parts = [f"<b>{title}</b>"]
    if shortcut:
        parts[0] += (
            f" &nbsp;<span style='color:{pal['accent']}; font-family:monospace;'>"
            f"[{shortcut}]</span>"
        )
    if description:
        parts.append(f"<div style='margin-top:3px;'>{description}</div>")
    if tip:
        parts.append(
            f"<div style='margin-top:4px; color:{pal['fg_dim']}; font-size:9pt;'>"
            f"💡 <i>Tip: {tip}</i></div>"
        )
    return "".join(parts)


def set_interactive_tooltip(
    widget: QWidget,
    title: str,
    description: str,
    *,
    shortcut: str = "",
    tip: str = "",
    enabled: bool = True,
) -> None:
    """Attach an interactive rich tooltip and statusTip to *widget*."""
    plain = f"{title} ({shortcut}) — {description}" if shortcut else f"{title} — {description}"
    widget.setStatusTip(plain)
    if enabled:
        widget.setToolTip(
            format_interactive_tooltip(title, description, shortcut=shortcut, tip=tip)
        )
    else:
        widget.setToolTip(f"{title} ({shortcut})" if shortcut else title)


class OnboardingGuideDialog(QDialog):
    """Interactive step-by-step onboarding walkthrough for new and returning users."""

    def __init__(self, main_window=None, parent=None) -> None:
        super().__init__(parent or main_window)
        self.main = main_window
        self._step_index = 0
        self.setWindowTitle("Welcome to KB-Remote — Interactive Tour")
        self.setObjectName("onboardingDialog")
        self.resize(680, 500)
        self.setMinimumSize(520, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        # ── Top header with step pill & progress bar ──
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        self.step_badge = PillBadge("Step 1 of 6", "accent")
        self.step_badge.setObjectName("onboardingStepBadge")
        top_row.addWidget(self.step_badge)
        top_row.addStretch(1)

        self.shortcut_badge = PillBadge("", "default")
        self.shortcut_badge.setObjectName("onboardingShortcutBadge")
        top_row.addWidget(self.shortcut_badge)
        root.addLayout(top_row)

        self.progress = QProgressBar()
        self.progress.setObjectName("onboardingProgress")
        self.progress.setRange(1, len(ONBOARDING_STEPS))
        self.progress.setValue(1)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        root.addWidget(self.progress)

        # ── Main step content card ──
        self.card = QFrame()
        self.card.setObjectName("card")
        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(18, 16, 18, 16)
        card_lay.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(40, 40)
        title_row.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        self.title_label = QLabel()
        self.title_label.setObjectName("h1")
        self.title_label.setWordWrap(True)
        title_col.addWidget(self.title_label)

        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("caption")
        self.subtitle_label.setWordWrap(True)
        title_col.addWidget(self.subtitle_label)
        title_row.addLayout(title_col, 1)
        card_lay.addLayout(title_row)

        self.highlights_box = QVBoxLayout()
        self.highlights_box.setSpacing(8)
        self._highlight_labels: list[QLabel] = []
        for _ in range(3):
            lbl = QLabel()
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            self._highlight_labels.append(lbl)
            self.highlights_box.addWidget(lbl)
        card_lay.addLayout(self.highlights_box)

        card_lay.addStretch(1)

        try_row = QHBoxLayout()
        try_row.setSpacing(8)
        self.btn_try = QPushButton("Try it now")
        self.btn_try.setObjectName("subtle")
        self.btn_try.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_try.clicked.connect(self._trigger_try_action)
        try_row.addWidget(self.btn_try)
        try_row.addStretch(1)
        card_lay.addLayout(try_row)
        root.addWidget(self.card, 1)

        # ── Step jump buttons ──
        dots_row = QHBoxLayout()
        dots_row.setSpacing(6)
        self._step_buttons: list[QPushButton] = []
        for idx, step in enumerate(ONBOARDING_STEPS):
            b = QPushButton(str(idx + 1))
            b.setObjectName("subtle")
            b.setFixedSize(28, 26)
            b.setToolTip(step.title)
            b.clicked.connect(lambda _=False, i=idx: self.go_to_step(i))
            self._step_buttons.append(b)
            dots_row.addWidget(b)
        dots_row.addStretch(1)

        self.chk_tooltips = QCheckBox("Enable interactive tooltips with shortcuts & tips")
        self.chk_tooltips.setObjectName("onboardingTooltipsCheck")
        settings = getattr(getattr(self.main, "ctx", None), "settings", None)
        self.chk_tooltips.setChecked(
            bool(getattr(settings, "interactive_tooltips", True)) if settings else True
        )
        self.chk_tooltips.toggled.connect(self._on_tooltips_toggled)
        dots_row.addWidget(self.chk_tooltips)
        root.addLayout(dots_row)

        # ── Footer navigation ──
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.chk_completed = QCheckBox("Don't show automatically on startup")
        self.chk_completed.setObjectName("onboardingCompletedCheck")
        self.chk_completed.setChecked(True)
        footer.addWidget(self.chk_completed)
        footer.addStretch(1)

        self.btn_prev = QPushButton("Previous")
        self.btn_prev.setObjectName("subtle")
        self.btn_prev.clicked.connect(self.prev_step)
        footer.addWidget(self.btn_prev)

        self.btn_next = QPushButton("Next")
        self.btn_next.setObjectName("primary")
        self.btn_next.clicked.connect(self.next_step)
        footer.addWidget(self.btn_next)

        self.btn_finish = QPushButton("Finish Tour")
        self.btn_finish.setObjectName("primary")
        self.btn_finish.clicked.connect(self.finish_tour)
        footer.addWidget(self.btn_finish)
        root.addLayout(footer)

        self._render_step()

    @property
    def step_index(self) -> int:
        return self._step_index

    def go_to_step(self, index: int) -> None:
        self._step_index = max(0, min(int(index), len(ONBOARDING_STEPS) - 1))
        self._render_step()

    def prev_step(self) -> None:
        if self._step_index > 0:
            self._step_index -= 1
            self._render_step()

    def next_step(self) -> None:
        if self._step_index < len(ONBOARDING_STEPS) - 1:
            self._step_index += 1
            self._render_step()
        else:
            self.finish_tour()

    def _render_step(self) -> None:
        step = ONBOARDING_STEPS[self._step_index]
        pal = palette()
        total = len(ONBOARDING_STEPS)
        self.step_badge.setText(f"Step {self._step_index + 1} of {total}")
        self.shortcut_badge.setText(step.shortcut_hint)
        self.progress.setValue(self._step_index + 1)

        ic = badge_icon(step.icon_name, 38)
        self.icon_label.setPixmap(ic.pixmap(38, 38))
        self.title_label.setText(step.title)
        self.subtitle_label.setText(step.subtitle)

        for i, lbl in enumerate(self._highlight_labels):
            if i < len(step.highlights):
                lbl.setVisible(True)
                lbl.setText(
                    f"<span style='color:{pal['accent']}; font-weight:700;'>•</span> "
                    f"{step.highlights[i]}"
                )
            else:
                lbl.setVisible(False)

        if step.try_label and step.try_action_attr:
            self.btn_try.setVisible(True)
            self.btn_try.setText(f"✦ {step.try_label}")
        else:
            self.btn_try.setVisible(False)

        for idx, b in enumerate(self._step_buttons):
            b.setObjectName("primary" if idx == self._step_index else "subtle")
            b.style().unpolish(b)
            b.style().polish(b)

        self.btn_prev.setEnabled(self._step_index > 0)
        is_last = self._step_index >= total - 1
        self.btn_next.setVisible(not is_last)
        self.btn_finish.setVisible(is_last)

    def _trigger_try_action(self) -> None:
        step = ONBOARDING_STEPS[self._step_index]
        if self.main is None or not step.try_action_attr:
            return
        fn: Callable | None = getattr(self.main, step.try_action_attr, None)
        if callable(fn):
            fn()

    def _on_tooltips_toggled(self, checked: bool) -> None:
        if self.main is not None and hasattr(self.main, "set_interactive_tooltips"):
            self.main.set_interactive_tooltips(bool(checked))

    def finish_tour(self) -> None:
        if self.main is not None and hasattr(self.main, "ctx"):
            settings = self.main.ctx.settings
            settings.onboarding_completed = bool(self.chk_completed.isChecked())
            settings.interactive_tooltips = bool(self.chk_tooltips.isChecked())
            if hasattr(self.main, "_save_settings"):
                self.main._save_settings()
            toast(self.main, "Onboarding tour complete — press F1 anytime for shortcuts", "good")
        self.accept()
