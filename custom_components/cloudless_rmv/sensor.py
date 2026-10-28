"""Main departure sensor and per-station sensors."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_WATCH
from .coordinator import RmvConfigEntry, RmvCoordinator
from .entity import RmvEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: RmvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [RmvDeparturesSensor(coordinator)]
    entities += [RmvStationSensor(coordinator, st) for st in entry.data.get(CONF_WATCH, [])]
    async_add_entities(entities)


class RmvDeparturesSensor(RmvEntity, SensorEntity):
    """Next usable departure; all details in the attributes (used by the card)."""

    _attr_translation_key = "next_departure"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    # Large and constantly changing: keep out of the recorder database.
    _unrecorded_attributes = frozenset(
        {"stop", "walk_min", "max_rows", "departures", "stations", "connections",
         "messages", "fetched_at", "error", "stats", "has_stop_data"}
    )

    def __init__(self, coordinator: RmvCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_next"

    def _next(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        limit = dt_util.now().timestamp() + data.get("walk_min", 0) * 60
        for dep in data.get("departures", []):
            if dep["cancelled"] or not dep["eff"]:
                continue
            if datetime.fromisoformat(dep["eff"]).timestamp() >= limit:
                return dep
        return None

    @property
    def native_value(self) -> datetime | None:
        dep = self._next()
        return datetime.fromisoformat(dep["eff"]) if dep else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self.coordinator.data or {})


class RmvStationSensor(RmvEntity, SensorEntity):
    """Is this station served? ok / none / unknown."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ok", "none", "unknown"]
    _attr_translation_key = "station"
    _unrecorded_attributes = frozenset({"next", "served", "not_served", "total"})

    def __init__(self, coordinator: RmvCoordinator, station: dict[str, str]) -> None:
        super().__init__(coordinator)
        self._sid = str(station["id"])
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_station_{self._sid}"
        self._attr_translation_placeholders = {"station": station["name"]}

    def _summary(self) -> dict[str, Any] | None:
        for s in (self.coordinator.data or {}).get("stations", []):
            if s["id"] == self._sid:
                return s
        return None

    @property
    def native_value(self) -> str:
        s = self._summary()
        return s["state"] if s else "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self._summary() or {}
        return {k: v for k, v in s.items() if k not in ("id", "name", "short", "state")}
