"""A tiny synchronous pub/sub event bus.

Used to decouple protocol backends from UI concerns: any component may publish
``("session/connected", {...})`` and unrelated components (status bar, tray,
metrics) may subscribe without holding references.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

Subscriber = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Subscriber]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, topic: str, fn: Subscriber) -> Callable[[], None]:
        """Subscribe; returns an unsubscribe callable."""
        with self._lock:
            self._subs[topic].append(fn)

        def _unsub() -> None:
            with self._lock:
                try:
                    self._subs[topic].remove(fn)
                except ValueError:
                    pass

        return _unsub

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        """Deliver ``payload`` to subscribers of ``topic`` and ``'*'``."""
        payload = payload or {}
        with self._lock:
            targets = list(self._subs.get(topic, ())) + list(self._subs.get("*", ()))
        for fn in targets:
            try:
                fn(payload)
            except Exception:  # noqa: BLE001 - subscribers must never break publishers
                import logging

                logging.getLogger("rdpstudio.events").exception("subscriber error on %s", topic)
