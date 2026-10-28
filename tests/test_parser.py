from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

import cloudless_rmv_pure.parser as P  # noqa: E402 (conftest sets it up)

TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 10, 28, 20, 30, tzinfo=TZ)
STOP = {"id": "3011265", "name": "Offenbach (Main) Marktplatz"}


def real_board():
    f = Path(__file__).parent / "fixtures" / "real_board_sample.yaml"
    if not f.exists():
        pytest.skip("local real-data fixture not included in the repository")
    return yaml.safe_load(f.read_text())


def stop(ext, name, arr, rt=None, **kw):
    s = {"extId": ext, "name": name, "arrDate": "2026-10-28", "arrTime": arr + ":00",
         "depDate": "2026-10-28", "depTime": arr + ":00"}
    if rt:
        s["rtArrDate"] = "2026-10-28"; s["rtArrTime"] = rt + ":00"
    s.update(kw)
    return s


def dep(line, time, rt=None, stops=(), **kw):
    d = {"date": "2026-10-28", "time": time + ":00", "direction": "Frankfurt Hbf",
         "stop": STOP["name"], "ProductAtStop": {"displayNumber": line, "catOutL": "S-Bahn"},
         "Stops": {"Stop": list(stops)}}
    if rt:
        d["rtDate"] = "2026-10-28"; d["rtTime"] = rt + ":00"
    d.update(kw)
    return d


def snap(deps, watch=(), connections=(), conn_boards=None, **kw):
    return P.build_snapshot(
        board={"Departure": deps}, stop=STOP, watch=list(watch), connections=list(connections),
        connection_boards=conn_boards or {}, now=NOW, tz=TZ, walk_min=kw.pop("walk_min", 0),
        max_rows=kw.pop("max_rows", 6), **kw)


def test_real_board_parses_and_has_messages():
    s = snap(real_board()["Departure"] if False else real_board()["Departure"], max_rows=7)
    assert s["departures"], "no departures parsed"
    assert all(d["eff"] for d in s["departures"])
    assert s["departures"] == sorted(s["departures"], key=lambda d: d["eff"])
    assert s["has_stop_data"] is False
    assert any(m["kind"] == "disruption" for m in s["messages"])


def test_more_than_five_rows_available():
    deps = [dep("S1", f"20:{31 + i}") for i in range(9)]
    s = snap(deps, max_rows=7)
    assert len(s["departures"]) >= 7


def test_delay_and_cancel():
    s = snap([dep("S1", "20:40", rt="20:47"), dep("S2", "20:45", cancelled=True)])
    by = {d["line"]: d for d in s["departures"]}
    a, b = by["S1"], by["S2"]
    assert a["delay"] == 7 and a["planned"] != a["eff"]
    assert b["cancelled"] and b["delay"] == 0


def stations():
    return [{"id": "A", "name": "Mühlberg"}, {"id": "B", "name": "Konstablerwache"},
            {"id": "C", "name": "Frankfurt (Main) Hauptbahnhof"}]


def route(skip=(), cancel=()):
    stops = [stop("3011265", STOP["name"], "20:40")]
    for i, (ext, name) in enumerate([("A", "Mühlberg"), ("B", "Konstablerwache"), ("C", "Frankfurt (Main) Hauptbahnhof")]):
        if ext in skip:
            continue
        kw = {"cancelled": True} if ext in cancel else {}
        stops.append(stop(ext, name, f"20:{45 + 3 * i}", rt=f"20:{47 + 3 * i}", **kw))
    return stops


def test_station_served_and_not_served():
    s = snap([dep("S1", "20:40", stops=route(skip={"B"}))], watch=stations())
    by = {x["id"]: x for x in s["stations"]}
    assert by["A"]["state"] == "ok" and by["C"]["state"] == "ok"
    assert by["B"]["state"] == "none"
    r = s["departures"][0]["stations"]
    assert r["B"] == {"state": "not_served", "reason": "not_on_route"}
    assert r["A"]["arr_delay"] == 2


def test_stop_cancelled_and_journey_cancelled():
    s = snap([dep("S1", "20:40", stops=route(cancel={"A"})),
              dep("S2", "20:50", stops=route(), cancelled=True)], watch=stations())
    r = s["departures"][0]["stations"]
    assert r["A"]["reason"] == "stop_cancelled"
    assert s["departures"][1]["stations"]["C"]["reason"] == "journey_cancelled"
    assert {x["id"]: x["state"] for x in s["stations"]}["C"] == "ok"  # still served by trip 1


def test_unknown_without_stop_list():
    s = snap([dep("S1", "20:40")], watch=stations())
    assert all(x["state"] == "unknown" for x in s["stations"])


def test_connection_ok_none_disrupted():
    cfg = {"transfer_id": "A", "transfer_name": "Mühlberg", "target": {"id": "F", "name": "Friedensbrücke"}}

    def tram(time, with_target=True, **kw):
        stops = [stop("A", "Mühlberg", time)]
        if with_target:
            stops.append(stop("F", "Friedensbrücke", "20:59"))
        return dep("16", time, stops=stops, **{**{"stop": "Mühlberg"}, **kw})

    def run(deps):
        return snap([dep("S1", "20:40", stops=route())], connections=[cfg],
                    conn_boards={"A": {"Departure": deps}})["connections"][0]

    assert run([tram("20:55")])["status"] == "ok"
    assert run([tram("20:55", with_target=False)])["status"] == "none"
    assert run([tram("20:55", cancelled=True)])["status"] == "none"
    assert run([tram("20:55"), tram("21:05", cancelled=True)])["status"] == "disrupted"
    assert snap([dep("S1", "20:40")], connections=[cfg], conn_boards={"A": None})["connections"][0]["status"] == "unknown"


def test_html_to_text():
    assert P.html_to_text("<p>A &amp; B<br>C</p>").replace("\n", " ").split() == ["A", "&", "B", "C"]
