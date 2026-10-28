"""Cloudless RMV: departures, disruptions and station checks for the RMV area.

Unofficial integration, not affiliated with or endorsed by the RMV.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .client import RmvClient
from .const import CARD_URL, LOGO_URL, CARD_VERSION, CONF_API_KEY, DOMAIN, PLATFORMS
from .coordinator import RmvConfigEntry, RmvCoordinator
from .shared import async_get_budget

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the bundled Lovelace card and load it in the frontend."""
    card = Path(__file__).parent / "www" / "cloudless-rmv-card.js"
    paths = [StaticPathConfig(CARD_URL, str(card), cache_headers=False)]
    # Optional: the RMV logo (required attribution) if the user placed it here.
    logo = Path(__file__).parent / "www" / "rmv-logo.png"
    if await hass.async_add_executor_job(logo.is_file):
        paths.append(StaticPathConfig(LOGO_URL, str(logo), cache_headers=True))
    await hass.http.async_register_static_paths(paths)
    add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RmvConfigEntry) -> bool:
    """Set up one stop."""
    budget = await async_get_budget(hass, entry.data[CONF_API_KEY])
    client = RmvClient(aiohttp_client.async_get_clientsession(hass), entry.data[CONF_API_KEY], budget)
    coordinator = RmvCoordinator(hass, entry, client)
    # Raises ConfigEntryAuthFailed / ConfigEntryNotReady on problems.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RmvConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: RmvConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
