"""Request budgets shared by every entry that uses the same API key."""

from __future__ import annotations

import hashlib
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .budget import RequestBudget
from .const import DOMAIN


def _key_id(api_key: str) -> str:
    # Only used to name a storage file; the key itself is never stored here.
    return hashlib.sha256(api_key.encode()).hexdigest()[:12]


async def async_get_budget(hass: HomeAssistant, api_key: str) -> RequestBudget:
    """Return the (persisted) budget for this key."""
    budgets: dict[str, dict[str, Any]] = hass.data.setdefault(DOMAIN, {}).setdefault(
        "budgets", {}
    )
    kid = _key_id(api_key)
    if kid not in budgets:
        store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.budget_{kid}")
        budget = RequestBudget()
        data = await store.async_load()
        if isinstance(data, dict):
            budget.load(data.get("stamps", []))
        budgets[kid] = {"budget": budget, "store": store}
    return budgets[kid]["budget"]


def schedule_budget_save(hass: HomeAssistant, api_key: str) -> None:
    """Persist the counters soon (debounced)."""
    entry = hass.data.get(DOMAIN, {}).get("budgets", {}).get(_key_id(api_key))
    if entry:
        budget: RequestBudget = entry["budget"]
        entry["store"].async_delay_save(lambda: {"stamps": budget.export()}, 30)
