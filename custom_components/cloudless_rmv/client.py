"""Minimal async client for the RMV HAFAS ReST API (no HA imports).

Security notes
--------------
* The API key travels as the ``accessId`` query parameter (that is how the RMV
  API works). aiohttp exceptions contain the full request URL, so every
  exception is caught and re-raised *without* the original as context.
  Nothing in this module logs URLs or parameters.
* ``repr()`` of the client never contains the key.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .budget import BudgetExceeded, RequestBudget
from .const import API_BASE


class RmvError(Exception):
    """Base error. Messages never contain the API key or URLs."""


class AuthError(RmvError):
    """The access key was rejected."""


class QuotaError(RmvError):
    """The RMV rate limit was hit."""


class ConnectError(RmvError):
    """Network problem or unusable response."""


class ApiError(RmvError):
    """The API answered with an error code."""

    def __init__(self, code: str, text: str = "") -> None:
        super().__init__(f"{code}: {text}" if text else code)
        self.code = code
        self.text = text


class RmvClient:
    """Thin wrapper around the endpoints we need."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        budget: RequestBudget,
        *,
        base_url: str = API_BASE,
        timeout: float = 20,
    ) -> None:
        self._session = session
        self._key = api_key
        self._budget = budget
        self._base = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    def __repr__(self) -> str:  # never leak the key
        return "RmvClient(<redacted>)"

    @property
    def budget(self) -> RequestBudget:
        return self._budget

    async def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        self._budget.check(1)
        query = {k: v for k, v in params.items() if v is not None}
        query["accessId"] = self._key
        query["format"] = "json"
        url = f"{self._base}/{endpoint}"
        status: int | None = None
        payload: Any = None
        try:
            self._budget.record()
            async with self._session.get(
                url, params=query, timeout=self._timeout
            ) as resp:
                status = resp.status
                payload = await resp.json(content_type=None)
        except BudgetExceeded:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            if status in (401, 403):
                raise AuthError("access denied") from None
            if status is not None and status >= 500:
                raise ApiError(f"HTTP_{status}") from None
            raise ConnectError("connection problem") from None

        if isinstance(payload, dict) and payload.get("errorCode"):
            code = str(payload["errorCode"])
            text = str(payload.get("errorText") or "")
            if code == "API_AUTH":
                raise AuthError("access denied")
            if code == "API_QUOTA":
                raise QuotaError("quota exceeded")
            if code in ("SVC_NO_RESULT", "SVC_NO_MATCH"):
                return {}
            raise ApiError(code, text)
        if status in (401, 403):
            raise AuthError("access denied")
        if status is not None and status >= 500:
            raise ApiError(f"HTTP_{status}")
        if not isinstance(payload, dict):
            raise ConnectError("unexpected response")
        return payload

    async def search_stops(self, query: str, max_no: int = 12) -> list[dict[str, str]]:
        """Search stops by name. Returns [{'id': extId, 'name': name}]."""
        data = await self._get(
            "location.name", {"input": query, "type": "S", "maxNo": max_no}
        )
        raw = data.get("stopLocationOrCoordLocation")
        if raw is None:
            raw = [{"StopLocation": s} for s in _as_list(data.get("StopLocation"))]
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in _as_list(raw):
            stop = item.get("StopLocation") if isinstance(item, dict) else None
            if not isinstance(stop, dict):
                continue
            ext = str(stop.get("extId") or "")
            name = str(stop.get("name") or "")
            if ext and name and ext not in seen:
                seen.add(ext)
                out.append({"id": ext, "name": name})
        return out

    async def departure_board(
        self,
        stop_id: str,
        *,
        direction: str | None = None,
        duration: int = 90,
        max_journeys: int = 20,
        passlist: bool = True,
        date: str | None = None,
        time: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a departure board (with the list of passed stops by default)."""
        params: dict[str, Any] = {
            "extId": stop_id,
            "direction": direction,
            "duration": duration,
            "maxJourneys": max_journeys,
            "date": date,
            "time": time,
        }
        if passlist:
            params["passlist"] = 1
        try:
            return await self._get("departureBoard", params)
        except ApiError as err:
            # Be tolerant if this server version rejects `passlist`.
            if passlist and err.code == "API_PARAM" and "passlist" in err.text.lower():
                params.pop("passlist", None)
                return await self._get("departureBoard", params)
            raise

    async def journey_detail(self, ref: str) -> dict[str, Any]:
        """Fetch the stop list of one journey (fallback if the board has none)."""
        return await self._get("journeyDetail", {"id": ref})


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]
