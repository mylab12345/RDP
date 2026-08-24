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
        try:
            attempt = int(attempt)
        except (TypeError, ValueError):
            attempt = 1
        attempt = max(1, attempt)
        # Cap the exponent so a huge attempt number cannot overflow.
        exp = min(attempt - 1, 20)
        base = self.base_delay if self.base_delay > 0 else 1.5
        cap = self.max_delay if self.max_delay > 0 else 60.0
        delay = min(base * (2 ** exp), cap)
        jitter_frac = self.jitter if 0 <= self.jitter <= 1 else 0.25
        jitter = delay * jitter_frac * random.uniform(-1, 1)
        return max(0.2, delay + jitter)

    def should_retry(self, attempt: int) -> bool:
        try:
            attempt = int(attempt)
        except (TypeError, ValueError):
            return False
        return 1 <= attempt <= max(0, int(self.max_attempts))

    @classmethod
    def from_settings(cls, settings) -> ReconnectPolicy:
        return cls(
            max_attempts=settings.reconnect_max_attempts,
            base_delay=settings.reconnect_base_delay,
            max_delay=settings.reconnect_max_delay,
        )
