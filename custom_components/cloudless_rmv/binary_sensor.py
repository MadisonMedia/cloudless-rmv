"""Problem sensors: tram connection down / station not served."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CONNECTIONS
from .coordinator import RmvConfigEntry, RmvCoordinator
from .entity import RmvEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: RmvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        RmvConnectionProblem(coordinator, c) for c in entry.data.get(CONF_CONNECTIONS, [])
    )


class RmvConnectionProblem(RmvEntity, BinarySensorEntity):
    """On when the onward connection has no service or is disrupted."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "connection"
    _unrecorded_attributes = frozenset({"lines", "next", "next_min", "next_delay", "checked_for"})

    def __init__(self, coordinator: RmvCoordinator, cfg: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._tid = cfg["transfer_id"]
        self._target = cfg["target"]["name"]
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_conn_{self._tid}_{cfg['target']['id']}"
        )
        self._attr_translation_placeholders = {
            "transfer": cfg["transfer_name"],
            "target": cfg["target"]["name"],
        }

    def _summary(self) -> dict[str, Any] | None:
        for c in (self.coordinator.data or {}).get("connections", []):
            if c["transfer_id"] == self._tid and c["target"] == self._target:
                return c
        return None

    @property
    def available(self) -> bool:
        s = self._summary()
        return super().available and s is not None and s["status"] != "unknown"

    @property
    def is_on(self) -> bool | None:
        s = self._summary()
        return None if s is None else s["status"] in ("none", "disrupted")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self._summary() or {}
        return {k: s[k] for k in ("status", "count", "cancelled", "lines", "next", "next_min",
                                  "next_delay", "checked_for") if k in s}
