"""Diagnostics download with the key and personal data removed."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY
from .coordinator import RmvConfigEntry

TO_REDACT = {CONF_API_KEY, "accessId", "access_id", "api_key"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RmvConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "budget": coordinator.client.budget.stats(),
        "last_error": coordinator.last_error,
        "data": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
