"""Data coordinator: no background polling, refresh on demand only."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .budget import BudgetExceeded
from .client import ApiError, AuthError, ConnectError, QuotaError, RmvClient, RmvError
from .const import (
    CONF_API_KEY,
    CONF_CONNECTIONS,
    CONF_DIRECTION,
    CONF_DURATION,
    CONF_MAX_ROWS,
    CONF_STOP,
    CONF_TRANSFER_BUFFER,
    CONF_WALK_MIN,
    CONF_WATCH,
    DEFAULT_DURATION,
    DEFAULT_MAX_ROWS,
    DEFAULT_TRANSFER_BUFFER,
    DEFAULT_WALK_MIN,
    DOMAIN,
    REFRESH_COOLDOWN,
)
from .parser import build_snapshot, connection_query_time, refs_for_detail
from .shared import schedule_budget_save

_LOGGER = logging.getLogger(__name__)
RMV_TZ = ZoneInfo("Europe/Berlin")  # RMV delivers local German times without offset

type RmvConfigEntry = ConfigEntry[RmvCoordinator]


class RmvCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches on request (card/dashboard, service call), never on a timer.

    `update_interval=None` keeps the integration silent while nobody looks at
    the dashboard. The card asks for an update every 2 minutes while it is
    visible and on tap; requests are debounced.
    """

    config_entry: RmvConfigEntry

    def __init__(self, hass: HomeAssistant, entry: RmvConfigEntry, client: RmvClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            config_entry=entry,
            update_interval=None,
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=REFRESH_COOLDOWN, immediate=True
            ),
        )
        self.client = client
        self.last_error: str | None = None

    # -- helpers
    def _opt(self, key: str, default: int) -> int:
        return int(self.config_entry.options.get(key, default))

    async def _async_update_data(self) -> dict[str, Any]:
        data = self.config_entry.data
        stop = data[CONF_STOP]
        direction = data.get(CONF_DIRECTION)
        watch = data.get(CONF_WATCH, [])
        connections = data.get(CONF_CONNECTIONS, [])
        walk_min = self._opt(CONF_WALK_MIN, DEFAULT_WALK_MIN)
        max_rows = self._opt(CONF_MAX_ROWS, DEFAULT_MAX_ROWS)
        duration = self._opt(CONF_DURATION, DEFAULT_DURATION)
        buffer = self._opt(CONF_TRANSFER_BUFFER, DEFAULT_TRANSFER_BUFFER)

        now = datetime.now(RMV_TZ)
        common: dict[str, Any] = {
            "stop": stop,
            "watch": watch,
            "connections": connections,
            "now": now,
            "tz": RMV_TZ,
            "walk_min": walk_min,
            "max_rows": max_rows,
        }
        try:
            self.client.budget.check(1 + len(connections))
            board = await self.client.departure_board(
                stop["id"],
                direction=direction["id"] if direction else None,
                duration=duration,
                max_journeys=max_rows * 4 + 8,
            )
            pre = build_snapshot(board=board, connection_boards={}, **common)

            details: dict[str, dict[str, Any]] = {}
            if (watch or connections) and board and not pre["has_stop_data"]:
                for ref in refs_for_detail(board, stop["id"], RMV_TZ, now, walk_min, max_rows):
                    details[ref] = await self.client.journey_detail(ref)
                if details:
                    pre = build_snapshot(
                        board=board, connection_boards={}, journey_details=details, **common
                    )

            times: dict[str, datetime] = {}
            conn_boards: dict[str, dict[str, Any] | None] = {}
            for cfg in connections:
                tid = cfg["transfer_id"]
                times[tid] = connection_query_time(pre, tid, now, buffer, walk_min)
                at = times[tid].astimezone(RMV_TZ)
                try:
                    conn_boards[tid] = await self.client.departure_board(
                        tid,
                        duration=40,
                        max_journeys=40,
                        date=at.strftime("%Y-%m-%d"),
                        time=at.strftime("%H:%M"),
                    )
                except (ApiError, ConnectError) as err:
                    _LOGGER.warning("Connection lookup failed: %s", type(err).__name__)
                    conn_boards[tid] = None

            snapshot = build_snapshot(
                board=board,
                connection_boards=conn_boards,
                connection_times=times,
                journey_details=details or None,
                **common,
            )
        except AuthError as err:
            raise ConfigEntryAuthFailed("RMV access key rejected") from None
        except (BudgetExceeded, QuotaError, ApiError, ConnectError, RmvError) as err:
            return self._stale_or_fail(err)
        finally:
            schedule_budget_save(self.hass, self.config_entry.data[CONF_API_KEY])

        snapshot["stats"] = self.client.budget.stats()
        snapshot["error"] = None
        self.last_error = None
        return snapshot

    def _stale_or_fail(self, err: Exception) -> dict[str, Any]:
        """Keep showing the last data (marked as stale) instead of going unavailable."""
        if isinstance(err, BudgetExceeded):
            code = f"budget_{err.window}"
        elif isinstance(err, QuotaError):
            code = "quota"
        elif isinstance(err, ApiError):
            code = err.code
        else:
            code = "connection"
        self.last_error = code
        _LOGGER.warning("RMV update failed (%s)", code)
        if self.data:
            stale = dict(self.data)
            stale["error"] = code
            stale["stats"] = self.client.budget.stats()
            return stale
        raise UpdateFailed(f"RMV update failed ({code})")
