import asyncio

import pytest

from cloudless_rmv_pure.budget import BudgetExceeded, RequestBudget
from cloudless_rmv_pure.client import AuthError, ConnectError, RmvClient

SECRET = "SUPER-SECRET-KEY-123"


def test_budget_hour_and_day():
    t = [1000.0]
    b = RequestBudget(hourly=10, daily=20, safety=0.5, clock=lambda: t[0])
    for _ in range(5):
        b.record()
    with pytest.raises(BudgetExceeded) as e:
        b.check(1)
    assert e.value.window == "hour"
    t[0] += 3601
    b.check(1)
    assert b.used() == (0, 5)
    b.load(b.export())
    assert b.used()[1] == 5


class Resp:
    def __init__(self, status, payload):
        self.status, self._p = status, payload
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def json(self, content_type=None): return self._p


class Session:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, []
    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        if self.exc:
            raise self.exc
        return self.resp


def client(session):
    return RmvClient(session, SECRET, RequestBudget())


def test_auth_error_and_no_key_leak():
    c = client(Session(Resp(200, {"errorCode": "API_AUTH", "errorText": "x"})))
    with pytest.raises(AuthError) as e:
        asyncio.run(c.departure_board("1"))
    assert SECRET not in str(e.value) and SECRET not in repr(c)


def test_exception_does_not_leak_url():
    import aiohttp
    c = client(Session(exc=aiohttp.ClientConnectionError(f"https://x?accessId={SECRET}")))
    with pytest.raises(ConnectError) as e:
        asyncio.run(c.departure_board("1"))
    assert SECRET not in str(e.value) and e.value.__cause__ is None and e.value.__suppress_context__


def test_params_include_duration_and_passlist():
    s = Session(Resp(200, {"Departure": []}))
    asyncio.run(client(s).departure_board("42", duration=90, max_journeys=30))
    p = s.calls[0]
    assert p["duration"] == 90 and p["passlist"] == 1 and p["extId"] == "42" and p["format"] == "json"


def test_search_stops():
    payload = {"stopLocationOrCoordLocation": [{"StopLocation": {"extId": "1", "name": "A"}},
                                               {"StopLocation": {"extId": "1", "name": "A"}}]}
    assert asyncio.run(client(Session(Resp(200, payload))).search_stops("a")) == [{"id": "1", "name": "A"}]


def test_no_result_is_empty():
    c = client(Session(Resp(200, {"errorCode": "SVC_NO_RESULT"})))
    assert asyncio.run(c.departure_board("1")) == {}
