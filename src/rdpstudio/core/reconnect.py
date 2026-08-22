"""Reconnect scheduling with exponential backoff + jitter."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class ReconnectPolicy:
    max_attempts: int = 12
    base_delay: float = 1.5
    max_delay: float = 60.0
    jitter: float = 0.25

    def delay_for_attempt(self, attempt: int) -> float:
        """Delay before ``attempt`` (1-based) in seconds."""
        delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        jitter = delay * self.jitter * random.uniform(-1, 1)
        return max(0.2, delay + jitter)

    def should_retry(self, attempt: int) -> bool:
        return attempt <= self.max_attempts

    @classmethod
    def from_settings(cls, settings) -> ReconnectPolicy:
        return cls(
            max_attempts=settings.reconnect_max_attempts,
            base_delay=settings.reconnect_base_delay,
            max_delay=settings.reconnect_max_delay,
        )
