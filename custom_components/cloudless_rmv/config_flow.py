"""Graphical setup: key -> stop -> (direction) -> stations to check -> tram connections."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client, selector

from .client import ApiError, AuthError, ConnectError, QuotaError, RmvClient
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
    OPEN_DATA_URL,
)
from .shared import async_get_budget

_LOGGER = logging.getLogger(__name__)

QUERY = "query"
PICK = "pick"
NONE_ID = "__none__"


def _text(**kw: Any) -> selector.TextSelector:
    return selector.TextSelector(selector.TextSelectorConfig(**kw))


def _number(lo: int, hi: int, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=lo, max=hi, step=1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement=unit
        )
    )


class CloudlessRmvConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._key: str = ""
        self._stop: dict[str, str] | None = None
        self._direction: dict[str, str] | None = None
        self._watch: list[dict[str, str]] = []
        self._connections: list[dict[str, Any]] = []
        self._results: list[dict[str, str]] = []
        self._pending_target: dict[str, str] | None = None
        self._client: RmvClient | None = None

    # ---- helpers
    async def _client_for(self, key: str) -> RmvClient:
        budget = await async_get_budget(self.hass, key)
        return RmvClient(aiohttp_client.async_get_clientsession(self.hass), key, budget)

    async def _search(self, query: str) -> tuple[list[dict[str, str]], str | None]:
        assert self._client is not None
        try:
            return await self._client.search_stops(query), None
        except AuthError:
            return [], "invalid_auth"
        except QuotaError:
            return [], "quota"
        except (ConnectError, ApiError):
            return [], "cannot_connect"
        except Exception:  # noqa: BLE001 - never leak details (could contain the key)
            _LOGGER.error("Unexpected error during stop search")
            return [], "unknown"

    def _pick_schema(self, allow_none: bool = False) -> vol.Schema:
        opts = [selector.SelectOptionDict(value=r["id"], label=r["name"]) for r in self._results]
        if allow_none:
            opts.insert(0, selector.SelectOptionDict(value=NONE_ID, label="—"))
        return vol.Schema(
            {
                vol.Required(PICK): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=opts, mode=selector.SelectSelectorMode.LIST
                    )
                )
            }
        )

    def _picked(self, pick: str) -> dict[str, str] | None:
        return next((r for r in self._results if r["id"] == pick), None)

    # ---- step 1: key
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            self._client = await self._client_for(key)
            _, err = await self._search("Frankfurt")
            if err:
                errors["base"] = err
            else:
                self._key = key
                return await self.async_step_stop()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): _text(type=selector.TextSelectorType.PASSWORD)}),
            errors=errors,
            description_placeholders={"open_data_url": OPEN_DATA_URL},
        )

    # ---- reauth
    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            self._client = await self._client_for(key)
            _, err = await self._search("Frankfurt")
            if err:
                errors["base"] = err
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_API_KEY: key}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): _text(type=selector.TextSelectorType.PASSWORD)}),
            errors=errors,
            description_placeholders={"open_data_url": OPEN_DATA_URL},
        )

    # ---- step 2: stop
    async def async_step_stop(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._results, err = await self._search(user_input[QUERY])
            if err:
                errors["base"] = err
            elif not self._results:
                errors["base"] = "no_results"
            else:
                return await self.async_step_stop_pick()
        return self.async_show_form(
            step_id="stop", data_schema=vol.Schema({vol.Required(QUERY): _text()}), errors=errors
        )

    async def async_step_stop_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._stop = self._picked(user_input[PICK])
            return await self.async_step_direction()
        return self.async_show_form(step_id="stop_pick", data_schema=self._pick_schema())

    # ---- step 3: optional direction filter
    async def async_step_direction(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            query = (user_input.get(QUERY) or "").strip()
            if not query:
                return await self.async_step_watch()
            self._results, err = await self._search(query)
            if err:
                errors["base"] = err
            elif not self._results:
                errors["base"] = "no_results"
            else:
                return await self.async_step_direction_pick()
        return self.async_show_form(
            step_id="direction",
            data_schema=vol.Schema({vol.Optional(QUERY, default=""): _text()}),
            errors=errors,
        )

    async def async_step_direction_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._direction = None if user_input[PICK] == NONE_ID else self._picked(user_input[PICK])
            return await self.async_step_watch()
        return self.async_show_form(step_id="direction_pick", data_schema=self._pick_schema(True))

    # ---- step 4: stations to check (repeatable)
    async def async_step_watch(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            query = (user_input.get(QUERY) or "").strip()
            if not query:
                return await self.async_step_connection()
            self._results, err = await self._search(query)
            if err:
                errors["base"] = err
            elif not self._results:
                errors["base"] = "no_results"
            else:
                return await self.async_step_watch_pick()
        return self.async_show_form(
            step_id="watch",
            data_schema=vol.Schema({vol.Optional(QUERY, default=""): _text()}),
            errors=errors,
            description_placeholders={"added": ", ".join(s["name"] for s in self._watch) or "—"},
        )

    async def async_step_watch_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            st = self._picked(user_input[PICK])
            if st and all(w["id"] != st["id"] for w in self._watch):
                self._watch.append(st)
            return await self.async_step_watch()
        return self.async_show_form(step_id="watch_pick", data_schema=self._pick_schema())

    # ---- step 5: onward connections (repeatable; transfer must be a watched station)
    async def async_step_connection(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._watch:
            return await self._finish()
        errors: dict[str, str] = {}
        if user_input is not None:
            query = (user_input.get(QUERY) or "").strip()
            if not query:
                return await self._finish()
            self._results, err = await self._search(query)
            if err:
                errors["base"] = err
            elif not self._results:
                errors["base"] = "no_results"
            else:
                return await self.async_step_connection_pick()
        return self.async_show_form(
            step_id="connection",
            data_schema=vol.Schema({vol.Optional(QUERY, default=""): _text()}),
            errors=errors,
            description_placeholders={
                "added": ", ".join(f"{c['transfer_name']} → {c['target']['name']}" for c in self._connections) or "—"
            },
        )

    async def async_step_connection_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._pending_target = self._picked(user_input[PICK])
            return await self.async_step_connection_transfer()
        return self.async_show_form(step_id="connection_pick", data_schema=self._pick_schema())

    async def async_step_connection_transfer(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None and self._pending_target:
            tr = next(w for w in self._watch if w["id"] == user_input["transfer"])
            self._connections.append(
                {"transfer_id": tr["id"], "transfer_name": tr["name"], "target": self._pending_target}
            )
            self._pending_target = None
            return await self.async_step_connection()
        opts = [selector.SelectOptionDict(value=w["id"], label=w["name"]) for w in self._watch]
        return self.async_show_form(
            step_id="connection_transfer",
            data_schema=vol.Schema(
                {
                    vol.Required("transfer"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=opts, mode=selector.SelectSelectorMode.LIST)
                    )
                }
            ),
            description_placeholders={"target": (self._pending_target or {}).get("name", "")},
        )

    async def _finish(self) -> ConfigFlowResult:
        assert self._stop is not None
        unique = f"{self._stop['id']}|{(self._direction or {}).get('id', '')}"
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured()
        title = self._stop["name"] + (f" → {self._direction['name']}" if self._direction else "")
        return self.async_create_entry(
            title=title,
            data={
                CONF_API_KEY: self._key,
                CONF_STOP: self._stop,
                CONF_DIRECTION: self._direction,
                CONF_WATCH: self._watch,
                CONF_CONNECTIONS: self._connections,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        return RmvOptionsFlow()


class RmvOptionsFlow(OptionsFlow):
    """Tunable numbers; stations are changed by re-adding the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={k: int(v) for k, v in user_input.items()})
        o = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_WALK_MIN, default=o.get(CONF_WALK_MIN, DEFAULT_WALK_MIN)): _number(0, 60, "min"),
                    vol.Required(CONF_MAX_ROWS, default=o.get(CONF_MAX_ROWS, DEFAULT_MAX_ROWS)): _number(1, 20, ""),
                    vol.Required(CONF_DURATION, default=o.get(CONF_DURATION, DEFAULT_DURATION)): _number(30, 720, "min"),
                    vol.Required(CONF_TRANSFER_BUFFER, default=o.get(CONF_TRANSFER_BUFFER, DEFAULT_TRANSFER_BUFFER)): _number(0, 30, "min"),
                }
            ),
        )
