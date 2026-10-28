from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "cloudless_rmv"
STOP = {"id": "3011265", "name": "Offenbach (Main) Marktplatz"}
HBF = {"id": "3000010", "name": "Frankfurt (Main) Hauptbahnhof"}
KEY = "SECRET-KEY-XYZ"


async def test_flow_creates_entry(hass):
    results = [STOP]

    async def search(self, q, max_no=12):
        return results

    with patch("custom_components.cloudless_rmv.client.RmvClient.search_stops", search), patch(
        "custom_components.cloudless_rmv.async_setup_entry", return_value=True
    ):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        assert r["step_id"] == "user"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"api_key": KEY})
        assert r["step_id"] == "stop"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"query": "Offenbach"})
        assert r["step_id"] == "stop_pick"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"pick": STOP["id"]})
        assert r["step_id"] == "direction"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"query": ""})
        assert r["step_id"] == "watch"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"query": "x"})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"pick": STOP["id"]})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"query": ""})
        assert r["step_id"] == "connection"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"query": ""})
        assert r["type"] is FlowResultType.CREATE_ENTRY
        assert r["data"]["api_key"] == KEY and r["data"]["stop"]["id"] == STOP["id"]


async def test_flow_invalid_auth(hass):
    from custom_components.cloudless_rmv.client import AuthError

    async def search(self, q, max_no=12):
        raise AuthError("x")

    with patch("custom_components.cloudless_rmv.client.RmvClient.search_stops", search):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"api_key": KEY})
        assert r["errors"] == {"base": "invalid_auth"}


async def test_setup_sensor_and_diagnostics(hass, hass_client):
    board = {"Departure": [{
        "date": "2099-01-01", "time": "10:00:00", "rtDate": "2099-01-01", "rtTime": "10:04:00",
        "direction": "Frankfurt Hbf", "stop": STOP["name"],
        "ProductAtStop": {"displayNumber": "S1", "catOutL": "S-Bahn"},
        "Stops": {"Stop": [
            {"extId": STOP["id"], "name": STOP["name"], "depDate": "2099-01-01", "depTime": "10:00:00"},
            {"extId": HBF["id"], "name": HBF["name"], "arrDate": "2099-01-01", "arrTime": "10:20:00"},
        ]},
    }]}

    async def dboard(self, *a, **k):
        return board

    entry = MockConfigEntry(
        domain=DOMAIN, title="Test", unique_id="u",
        data={"api_key": KEY, "stop": STOP, "direction": None, "watch": [HBF],
              "connections": []},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.cloudless_rmv.client.RmvClient.departure_board", dboard), patch(
        "custom_components.cloudless_rmv.async_setup", return_value=True
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        states = hass.states.async_all("sensor")
        assert len(states) == 2
        main = next(s for s in states if "departures" in s.attributes)
        assert main.attributes["departures"][0]["delay"] == 4
        station = next(s for s in states if s.state in ("ok", "none", "unknown") and "departures" not in s.attributes)
        assert station.state == "ok"

        from custom_components.cloudless_rmv.diagnostics import async_get_config_entry_diagnostics
        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert KEY not in str(diag)
