"""Request budget that keeps us below the RMV rate limits (no HA imports)."""

from __future__ import annotations

from collections import deque
import time
from typing import Callable

from .const import BUDGET_SAFETY, DAILY_LIMIT, HOURLY_LIMIT


class BudgetExceeded(Exception):
    """Raised when another request would exceed the safe request budget."""

    def __init__(self, window: str) -> None:
        super().__init__(f"request budget exceeded ({window})")
        self.window = window


class RequestBudget:
    """Rolling-window counter shared by all entries that use the same key.

    The 24 h window is rolling, which is always at least as strict as a
    calendar day, so the daily limit can never be hit by accident.
    """

    def __init__(
        self,
        hourly: int = HOURLY_LIMIT,
        daily: int = DAILY_LIMIT,
        safety: float = BUDGET_SAFETY,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.hourly = hourly
        self.daily = daily
        self.safety = safety
        self._clock = clock
        self._stamps: deque[float] = deque()

    def _prune(self, now: float) -> None:
        while self._stamps and self._stamps[0] < now - 86400:
            self._stamps.popleft()

    def used(self) -> tuple[int, int]:
        """Return (requests in last hour, requests in last 24 h)."""
        now = self._clock()
        self._prune(now)
        hour = sum(1 for s in self._stamps if s >= now - 3600)
        return hour, len(self._stamps)

    def check(self, needed: int = 1) -> None:
        """Raise BudgetExceeded if `needed` more requests would be unsafe."""
        hour, day = self.used()
        if hour + needed > self.hourly * self.safety:
            raise BudgetExceeded("hour")
        if day + needed > self.daily * self.safety:
            raise BudgetExceeded("day")

    def record(self) -> None:
        """Count one request."""
        now = self._clock()
        self._prune(now)
        self._stamps.append(now)

    def export(self) -> list[float]:
        """Return timestamps for persistence."""
        self._prune(self._clock())
        return list(self._stamps)

    def load(self, stamps: list[float]) -> None:
        """Restore persisted timestamps."""
        now = self._clock()
        self._stamps = deque(
            sorted(s for s in stamps if isinstance(s, (int, float)) and s >= now - 86400)
        )

    def stats(self) -> dict[str, int]:
        """Return counters for diagnostics."""
        hour, day = self.used()
        return {
            "last_hour": hour,
            "last_24h": day,
            "hourly_limit": self.hourly,
            "daily_limit": self.daily,
            "safe_hourly_limit": int(self.hourly * self.safety),
            "safe_daily_limit": int(self.daily * self.safety),
        }
