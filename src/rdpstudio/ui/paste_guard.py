"""The multi-line paste confirmation shared by both terminal renderers.

Pasting several lines into a shell executes every one of them the moment the
newline lands, so an accidental paste is destructive.  Both the portable
pyte/Qt terminal and the native QTermWidget backend therefore gate pastes
behind the same prompt; it lives here so the wording, the thresholds and the
"user said no" semantics can only ever be changed in one place.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

__all__ = ["PASTE_PREVIEW_CHARS", "PASTE_WARN_CHARS", "confirm_multiline_paste"]

#: Pastes longer than this are treated as "bulk" and prompt even on one line.
PASTE_WARN_CHARS = 200
#: How much of the payload the prompt shows before eliding.
PASTE_PREVIEW_CHARS = 400


def needs_paste_confirmation(text: str) -> bool:
    """True when ``text`` is multi-line or long enough to warrant a prompt."""
    return "\n" in text or "\r" in text or len(text) > PASTE_WARN_CHARS


def confirm_multiline_paste(parent: QWidget, text: str, *, enabled: bool = True) -> bool:
    """Ask before pasting ``text``; return True when the paste may proceed.

    ``enabled`` carries the user's ``confirm_multiline_paste`` setting. When it
    is off, or the payload is a harmless single short line, no prompt is shown
    and the paste is approved immediately.
    """
    if not enabled or not needs_paste_confirmation(text):
        return True
    preview = text if len(text) < PASTE_PREVIEW_CHARS else text[:PASTE_PREVIEW_CHARS] + "…"
    answer = QMessageBox.question(
        parent,
        "Paste multiple lines?",
        f"Paste the following to the remote host?\n\n{preview}",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


class ClipboardPasteMixin:
    """Clipboard-to-terminal paste gestures, shared by both renderers.

    Hosts supply ``paste_text(text, confirm=...)`` and ``_middle_click_text``;
    everything else — which clipboard a gesture reads and whether the
    multi-line guard applies — is defined once, here.
    """

    def _middle_click_text(self) -> str:
        """The text a middle-click should paste.

        Overridden per renderer so each module keeps its own reference to
        :func:`rdpstudio.ui.terminal.middle_click_text`.
        """
        raise NotImplementedError

    def paste_clipboard(self, confirm: bool = True) -> None:
        """Ctrl+Shift+V / context menu: the regular clipboard, guarded."""
        from PySide6.QtGui import QGuiApplication

        text = QGuiApplication.clipboard().text()
        if text:
            self.paste_text(text, confirm=confirm)

    def paste_middle_click(self) -> None:
        """Middle-click paste: PRIMARY-selection-first, never confirmed.

        Middle-click is an explicit paste gesture, so the multi-line guard
        stays off here (it still protects Ctrl+Shift+V and the context
        menu). The text source follows the platform convention — see
        :func:`rdpstudio.ui.terminal.middle_click_text`.
        """
        text = self._middle_click_text()
        if text:
            self.paste_text(text, confirm=False)
