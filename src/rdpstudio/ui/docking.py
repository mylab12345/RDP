"""Mouse-driven docking: drag a panel or the session tab strip to an edge.

MobaXterm toggles its side panel with keystrokes; this app lets you *move*
things with the mouse instead. Two surfaces are dockable and share one
implementation here:

* the **Sessions panel** — left edge or right edge of the window, and
* the **session tab strip** — top edge, or a vertical strip on the left or
  right edge.

Both gestures are identical from the user's point of view: grab the ⠿ grip
(or, for the tab strip, any empty part of the tab bar) and shove it at the
edge you want. Once the pointer passes :data:`DRAG_THRESHOLD` the window
dims and the candidate regions light up; releasing inside one docks there,
releasing in the middle changes nothing.

Everything is drawn from palette colours, so the indicator follows the active
theme (and its live switches) for free.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .theme import palette, palette_color

# A plain click must stay a click: only a real drag starts docking.
DRAG_THRESHOLD = 8
# How much of the window counts as an "edge band" (the drop target).
EDGE_FRACTION = 0.28
MIN_EDGE_BAND = 90
MAX_EDGE_BAND = 260

# Zone ids are plain strings so they can travel through signals untouched.
ZONES = ("left", "right", "top", "bottom")

ZONE_LABELS = {
    "left": "Dock left",
    "right": "Dock right",
    "top": "Tabs on top",
    "bottom": "Dock bottom",
}


def edge_band(size: int) -> int:
    """Thickness of the drop band along one axis of a window of ``size`` px."""
    return max(MIN_EDGE_BAND, min(MAX_EDGE_BAND, int(size * EDGE_FRACTION)))


def zone_rect(zone: str, rect: QRect) -> QRect:
    """The on-screen region a drop in ``zone`` would occupy (window coords)."""
    band_x = edge_band(rect.width())
    band_y = edge_band(rect.height())
    if zone == "left":
        return QRect(rect.left(), rect.top(), band_x, rect.height())
    if zone == "right":
        return QRect(rect.right() - band_x + 1, rect.top(), band_x, rect.height())
    if zone == "top":
        return QRect(rect.left(), rect.top(), rect.width(), band_y)
    if zone == "bottom":
        return QRect(rect.left(), rect.bottom() - band_y + 1, rect.width(), band_y)
    return QRect()


def zone_at(pos: QPoint, rect: QRect, zones) -> str | None:
    """Nearest allowed edge ``zone`` for ``pos``, or ``None``.

    The pointer decides: the zone whose edge it is closest to wins, and only
    if it is inside that zone's band. Returning ``None`` is the cancel case —
    dropping in the middle of the work area leaves the layout alone.
    """
    if not rect.contains(pos):
        return None
    best: str | None = None
    best_distance: int | None = None
    for zone in zones:
        if zone == "left":
            distance, limit = pos.x() - rect.left(), edge_band(rect.width())
        elif zone == "right":
            distance, limit = rect.right() - pos.x(), edge_band(rect.width())
        elif zone == "top":
            distance, limit = pos.y() - rect.top(), edge_band(rect.height())
        elif zone == "bottom":
            distance, limit = rect.bottom() - pos.y(), edge_band(rect.height())
        else:
            continue
        if distance > limit:
            continue
        if best_distance is None or distance < best_distance:
            best, best_distance = zone, distance
    return best


class DockOverlay(QWidget):
    """Translucent drop indicator laid over the whole window during a drag."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setObjectName("dockOverlay")
        # Purely decorative: the drag filter keeps receiving the mouse events.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._zones: tuple[str, ...] = ()
        self._active: str | None = None
        self._labels: dict[str, str] = {}
        self.hide()

    # -- lifecycle -----------------------------------------------------
    def begin(self, zones, labels: dict[str, str] | None = None) -> None:
        self._zones = tuple(zones)
        self._labels = dict(labels or {})
        self._active = None
        self._sync_geometry()
        self.show()
        self.raise_()
        self.update()

    def set_active(self, zone: str | None) -> None:
        if zone != self._active:
            self._active = zone
            self.update()

    def end(self) -> None:
        self._zones = ()
        self._active = None
        self.hide()

    def _sync_geometry(self) -> None:
        host = self.parentWidget()
        if host is not None:
            self.setGeometry(0, 0, host.width(), host.height())

    # -- painting ------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 — Qt naming
        if not self._zones:
            return
        pal = palette()
        rect = self.rect()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        scrim = palette_color(pal["bg"])
        scrim.setAlpha(150)
        painter.fillRect(rect, scrim)

        accent = palette_color(pal["accent"])
        inactive_border = palette_color(pal["border_strong"])
        radius = 10
        for zone in self._zones:
            region = zone_rect(zone, rect).adjusted(8, 8, -8, -8)
            active = zone == self._active
            fill = QColor(accent)
            fill.setAlpha(90 if active else 28)
            painter.setBrush(fill)
            pen = QPen(accent if active else inactive_border)
            pen.setWidth(2 if active else 1)
            pen.setStyle(Qt.PenStyle.SolidLine if active else Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRoundedRect(region, radius, radius)

            label = self._labels.get(zone) or ZONE_LABELS.get(zone, zone)
            font = QFont(painter.font())
            font.setBold(True)
            font.setPointSizeF(11.0)
            painter.setFont(font)
            text_color = palette_color(pal["accent_text"] if active else pal["fg"])
            painter.setPen(QPen(text_color))
            # Word-wrap: the edge bands are narrow, and a clipped label
            # ("Sessions panel → right edge") reads worse than two lines.
            painter.drawText(
                region.adjusted(6, 0, -6, 0),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                label,
            )
        painter.end()


class DockDragFilter(QObject):
    """Turns press → drag → release on a grip into a :class:`dockRequested`.

    Install on the widget that should act as the handle. ``can_start`` lets
    the owner veto a press (the tab bar uses it to keep dragging a *tab*
    meaning "reorder", while an empty stretch of bar means "move the strip").

    The filter watches without consuming events until a drag actually starts,
    so a plain click still reaches the button underneath.
    """

    dockRequested = Signal(str)  # zone id

    def __init__(
        self,
        source: QWidget,
        host: QWidget,
        zones,
        labels: dict[str, str] | None = None,
        can_start=None,
    ) -> None:
        super().__init__(source)
        self._host = host
        self._zones = tuple(zones)
        self._can_start = can_start
        self._press: QPoint | None = None
        self._dragging = False
        self.overlay = DockOverlay(host)
        self._labels = dict(labels or {})
        source.installEventFilter(self)

    # -- helpers -------------------------------------------------------
    def dragging(self) -> bool:
        return self._dragging

    def _zone_for_global(self, global_pos: QPoint) -> str | None:
        return zone_at(self._host.mapFromGlobal(global_pos), self._host.rect(), self._zones)

    def _cancel(self) -> None:
        self.overlay.end()
        self._press = None
        self._dragging = False

    # -- event filter --------------------------------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — Qt naming
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and self._allows(event):
                self._press = event.globalPosition().toPoint()
                self._dragging = False
            else:
                self._press = None
                self._dragging = False
            return False
        if kind == QEvent.Type.MouseMove:
            if self._press is None:
                return False
            pos = event.globalPosition().toPoint()
            delta = pos - self._press
            if not self._dragging:
                if abs(delta.x()) + abs(delta.y()) < DRAG_THRESHOLD:
                    return False
                self._dragging = True
                self.overlay.begin(self._zones, self._labels)
            self.overlay.set_active(self._zone_for_global(pos))
            return False
        if kind == QEvent.Type.MouseButtonRelease:
            if self._press is None:
                return False
            if not self._dragging:
                self._press = None
                return False
            zone = self._zone_for_global(event.globalPosition().toPoint())
            self._cancel()
            if zone:
                self.dockRequested.emit(zone)
            return True  # swallow it: the grip must not also "click"
        if kind == QEvent.Type.KeyPress and self._dragging:
            if event.key() == Qt.Key.Key_Escape:
                self._cancel()
                return True
        return False

    def _allows(self, event) -> bool:
        if self._can_start is None:
            return True
        widget = self.parent()
        pos = widget.mapFromGlobal(event.globalPosition().toPoint()) if widget else None
        try:
            return bool(self._can_start(pos))
        except RuntimeError:  # grip went away mid-press
            return False
