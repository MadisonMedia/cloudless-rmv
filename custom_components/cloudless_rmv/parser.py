"""Turn raw RMV (HAFAS) responses into a compact, JSON-friendly snapshot.

No Home Assistant imports, so this module is unit-testable on its own.

Why this exists: a raw board repeats every service message for every
departure and can reach hundreds of kilobytes. The snapshot keeps only what a
dashboard needs and de-duplicates messages. It is also deliberately *not* a
copy of the timetable (the RMV terms forbid storing a substantial part of it).
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
import html
import re
from typing import Any

# ---------------------------------------------------------------- helpers


def as_list(value: Any) -> list[Any]:
    """HAFAS JSON returns single items as dict and several as list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _dt(date: str | None, time: str | None, tz: tzinfo) -> datetime | None:
    if not date or not time:
        return None
    try:
        return datetime.fromisoformat(f"{date}T{time}").replace(tzinfo=tz)
    except ValueError:
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def norm(name: str | None) -> str:
    """Normalise a stop name for comparison."""
    return re.sub(r"[^0-9a-zäöüß]", "", (name or "").casefold())


_PREFIXES = (
    "Frankfurt (Main)-",
    "Frankfurt (Main) ",
    "Frankfurt am Main ",
    "Offenbach (Main)-",
    "Offenbach (Main) ",
)


def short_name(name: str) -> str:
    """Shorten typical RMV prefixes for display."""
    for prefix in _PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix) + 2:
            return name[len(prefix) :].strip()
    return name


def html_to_text(value: str | None, limit: int = 700) -> str:
    """Convert the small HTML subset RMV uses in messages to plain text."""
    if not value:
        return ""
    text = re.sub(r"<\s*br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"</\s*(li|p|ul)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*li[^>]*>", "• ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _color(icon: dict[str, Any], key: str, default: str) -> str:
    hexval = ((icon.get(key) or {}).get("hex") or "").lstrip("#")
    if len(hexval) in (6, 8):
        return "#" + hexval[-6:].upper()
    return default


# ------------------------------------------------------------- departures


def _norm_stop(stop: dict[str, Any], tz: tzinfo) -> dict[str, Any]:
    cancelled = bool(stop.get("cancelled"))
    cancelled_dep = bool(stop.get("cancelledDeparture"))
    cancelled_arr = bool(stop.get("cancelledArrival"))
    arr_cancelled = cancelled_arr or (cancelled and not cancelled_dep)
    rt_alighting = stop.get("rtAlighting")
    alighting = stop.get("alighting", True)
    no_alighting = (rt_alighting is False) or (rt_alighting is None and alighting is False)
    arr_planned = _dt(stop.get("arrDate"), stop.get("arrTime"), tz) or _dt(
        stop.get("depDate"), stop.get("depTime"), tz
    )
    arr_real = _dt(stop.get("rtArrDate") or stop.get("arrDate"), stop.get("rtArrTime"), tz) or _dt(
        stop.get("rtDepDate") or stop.get("depDate"), stop.get("rtDepTime"), tz
    )
    return {
        "ext_id": str(stop.get("extId") or ""),
        "name_norm": norm(stop.get("name")),
        "route_idx": stop.get("routeIdx"),
        "arr_cancelled": arr_cancelled,
        "no_alighting": no_alighting,
        "arr_planned": arr_planned,
        "arr_real": arr_real,
    }


def parse_departure(dep: dict[str, Any], tz: tzinfo, board_stop_id: str) -> dict[str, Any]:
    """Parse one Departure. Keys starting with '_' are internal."""
    planned = _dt(dep.get("date"), dep.get("time"), tz)
    real = (
        _dt(dep.get("rtDate") or dep.get("date"), dep.get("rtTime"), tz)
        if dep.get("rtTime")
        else None
    )
    eff = real or planned
    delay = round((real - planned).total_seconds() / 60) if real and planned else 0

    products = as_list(dep.get("Product"))
    prod = dep.get("ProductAtStop") or (products[0] if products else {})
    icon = prod.get("icon") or {}
    platform = (dep.get("rtPlatform") or {}).get("text") or dep.get("rtTrack")
    planned_platform = (dep.get("platform") or {}).get("text") or dep.get("track")

    stops = [_norm_stop(s, tz) for s in as_list((dep.get("Stops") or {}).get("Stop"))]
    here_name = norm(dep.get("stop"))
    start = None
    for i, s in enumerate(stops):
        if s["ext_id"] == board_stop_id or (here_name and s["name_norm"] == here_name):
            start = i
            break
    after: list[dict[str, Any]] = []
    if stops:
        if start is not None:
            after = stops[start + 1 :]
        elif planned:
            after = [s for s in stops if s["arr_planned"] and s["arr_planned"] > planned]

    return {
        "line": str(prod.get("displayNumber") or prod.get("line") or prod.get("name") or "?").strip(),
        "product": prod.get("catOutL") or prod.get("catOut") or "",
        "direction": dep.get("direction") or "",
        "color": _color(icon, "backgroundColor", "#666666"),
        "fg": _color(icon, "foregroundColor", "#FFFFFF"),
        "planned": _iso(planned),
        "real": _iso(real),
        "eff": _iso(eff),
        "delay": delay,
        "cancelled": bool(dep.get("cancelled")),
        "part_cancelled": bool(dep.get("partCancelled")),
        "redirected": bool(dep.get("redirected")),
        "platform": platform or planned_platform or "",
        "platform_changed": bool(platform and planned_platform and platform != planned_platform),
        "_eff": eff,
        "_after": after,
        "_has_stops": bool(stops),
        "_raw_messages": [m for m in as_list((dep.get("Messages") or {}).get("Message")) if isinstance(m, dict)],
        "_ref": (dep.get("JourneyDetailRef") or {}).get("ref"),
    }


def apply_journey_detail(parsed: dict[str, Any], detail: dict[str, Any], tz: tzinfo, board_stop_id: str) -> None:
    """Fill the stop list of a parsed departure from a journeyDetail response."""
    stops = [_norm_stop(s, tz) for s in as_list((detail.get("Stops") or {}).get("Stop"))]
    if not stops:
        return
    start = next((i for i, s in enumerate(stops) if s["ext_id"] == board_stop_id), None)
    parsed["_after"] = stops[start + 1 :] if start is not None else stops
    parsed["_has_stops"] = True
    if detail.get("cancelled"):
        parsed["cancelled"] = True
    if detail.get("partCancelled"):
        parsed["part_cancelled"] = True


# --------------------------------------------------------------- stations


def make_station(stop: dict[str, str]) -> dict[str, Any]:
    """Station config -> matching info."""
    return {
        "id": str(stop["id"]),
        "name": stop["name"],
        "short": short_name(stop["name"]),
        "name_norm": norm(stop["name"]),
    }


def evaluate_station(dep: dict[str, Any], station: dict[str, Any]) -> dict[str, Any]:
    """Is `station` served by this departure?

    state: served | not_served | unknown
    reason (for not_served): journey_cancelled | not_on_route | stop_cancelled | no_alighting
    """
    match = next(
        (
            s
            for s in dep["_after"]
            if s["ext_id"] == station["id"] or s["name_norm"] == station["name_norm"]
        ),
        None,
    )
    if dep["cancelled"]:
        if dep["_has_stops"] and match is None:
            return {"state": "not_served", "reason": "not_on_route"}
        return {"state": "not_served", "reason": "journey_cancelled"}
    if not dep["_has_stops"]:
        return {"state": "unknown"}
    if match is None:
        return {"state": "not_served", "reason": "not_on_route"}
    if match["arr_cancelled"]:
        return {"state": "not_served", "reason": "stop_cancelled"}
    if match["no_alighting"]:
        return {"state": "not_served", "reason": "no_alighting"}
    planned, real = match["arr_planned"], match["arr_real"]
    delay = round((real - planned).total_seconds() / 60) if planned and real else 0
    return {
        "state": "served",
        "arr": _iso(real or planned),
        "arr_planned": _iso(planned),
        "arr_delay": delay,
    }


def summarize_stations(deps: list[dict[str, Any]], stations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One summary per watched station across the given departures."""
    out = []
    for st in stations:
        results = [(d, d["stations"].get(st["id"], {"state": "unknown"})) for d in deps]
        known = [(d, r) for d, r in results if r["state"] != "unknown"]
        served = [(d, r) for d, r in known if r["state"] == "served"]
        if not deps or not known:
            state = "unknown"
        elif served:
            state = "ok"
        else:
            state = "none"
        entry: dict[str, Any] = {
            "id": st["id"],
            "name": st["name"],
            "short": st["short"],
            "state": state,
            "served": len(served),
            "not_served": len(known) - len(served),
            "total": len(deps),
        }
        if served:
            d, r = served[0]
            entry["next"] = {
                "line": d["line"],
                "arr": r.get("arr"),
                "arr_delay": r.get("arr_delay", 0),
            }
        out.append(entry)
    return out


# --------------------------------------------------------------- messages


def _msg_window_ok(msg: dict[str, Any], now: datetime, tz: tzinfo) -> bool:
    if msg.get("act") is False:
        return False
    start = _dt(msg.get("sDate"), msg.get("sTime"), tz)
    end = _dt(msg.get("eDate"), msg.get("eTime"), tz)
    if start and start > now + timedelta(hours=1):
        return False
    return not (end and end < now)


def _msg_kind(msg: dict[str, Any]) -> str:
    category = str(msg.get("category") or "")
    if not category:
        cats = as_list(msg.get("messageCategory"))
        category = str(cats[0].get("id")) if cats and isinstance(cats[0], dict) else ""
    icon = str(msg.get("icon") or "")
    if category == "2" or "disturb" in icon:
        return "disruption"
    if category == "1" or "constr" in icon:
        return "construction"
    return "info"


def collect_messages(
    deps: list[dict[str, Any]], now: datetime, tz: tzinfo, scope: str
) -> list[dict[str, Any]]:
    """De-duplicate messages across departures; write `messages` ids onto deps."""
    registry: dict[str, dict[str, Any]] = {}
    for dep in deps:
        ids: list[str] = []
        for msg in dep["_raw_messages"]:
            if not _msg_window_ok(msg, now, tz):
                continue
            mid = f"{scope}:{msg.get('id')}"
            ids.append(mid)
            entry = registry.get(mid)
            if entry is None:
                end = _dt(msg.get("eDate"), msg.get("eTime"), tz)
                entry = registry[mid] = {
                    "id": mid,
                    "kind": _msg_kind(msg),
                    "scope": scope,
                    "head": html_to_text(msg.get("head"), 200),
                    "lead": html_to_text(msg.get("lead"), 300),
                    "text": html_to_text(msg.get("text")),
                    "priority": msg.get("priority", 100),
                    "until": _iso(end),
                    "until_text": str(msg.get("altEnd") or "").strip(),
                    "lines": [],
                }
            if dep["line"] not in entry["lines"]:
                entry["lines"].append(dep["line"])
        dep["messages"] = ids
    order = {"disruption": 0, "construction": 1, "info": 2}
    return sorted(registry.values(), key=lambda m: (order[m["kind"]], m["priority"], m["id"]))


# ------------------------------------------------------------ connections


def evaluate_connection(
    board: dict[str, Any] | None,
    *,
    transfer: dict[str, str],
    target: dict[str, Any],
    query_time: datetime,
    now: datetime,
    tz: tzinfo,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Is there a service from `transfer` that reaches `target`?

    Returns (summary, parsed departures for message collection).
    status: ok | disrupted | none | unknown
    """
    base: dict[str, Any] = {
        "transfer_id": transfer["id"],
        "transfer": transfer["name"],
        "transfer_short": short_name(transfer["name"]),
        "target": target["name"],
        "target_short": target["short"],
        "checked_for": _iso(query_time),
    }
    if not board:
        return {**base, "status": "unknown", "count": 0, "cancelled": 0, "lines": []}, []

    parsed = [
        parse_departure(d, tz, transfer["id"])
        for d in as_list(board.get("Departure"))
        if isinstance(d, dict)
    ]
    parsed = [d for d in parsed if d["_eff"] and d["_eff"] >= query_time - timedelta(minutes=1)]
    parsed.sort(key=lambda d: d["_eff"])
    for d in parsed:
        d["_r"] = evaluate_station(d, target)

    if not any(d["_has_stops"] for d in parsed):
        return {**base, "status": "unknown", "count": 0, "cancelled": 0, "lines": []}, parsed

    candidates = [d for d in parsed if d["_r"]["state"] == "served" or d["_r"].get("reason") in ("journey_cancelled", "stop_cancelled")]
    running = [d for d in candidates if d["_r"]["state"] == "served"]
    cancelled = len(candidates) - len(running)
    summary: dict[str, Any] = {
        **base,
        "count": len(running),
        "cancelled": cancelled,
        "lines": sorted({d["line"] for d in running}),
    }
    if not running:
        summary["status"] = "none"
        return summary, parsed
    first = running[0]
    summary["next"] = first["eff"]
    summary["next_min"] = max(0, int((first["_eff"] - now).total_seconds() // 60))
    summary["next_delay"] = first["delay"]
    summary["status"] = "ok"
    summary["_running"] = running
    return summary, parsed


# --------------------------------------------------------------- snapshot


def build_snapshot(
    *,
    board: dict[str, Any],
    stop: dict[str, str],
    watch: list[dict[str, str]],
    connections: list[dict[str, Any]],
    connection_boards: dict[str, dict[str, Any] | None],
    now: datetime,
    tz: tzinfo,
    walk_min: int,
    max_rows: int,
    journey_details: dict[str, dict[str, Any]] | None = None,
    connection_times: dict[str, datetime] | None = None,
) -> dict[str, Any]:
    """Build the attribute payload for the main sensor."""
    stations = [make_station(s) for s in watch]
    parsed = [
        parse_departure(d, tz, stop["id"])
        for d in as_list(board.get("Departure"))
        if isinstance(d, dict)
    ]
    parsed = [d for d in parsed if d["_eff"] and d["_eff"] >= now - timedelta(seconds=30)]
    parsed.sort(key=lambda d: d["_eff"])

    for d in parsed:
        detail = (journey_details or {}).get(d["_ref"] or "")
        if detail:
            apply_journey_detail(d, detail, tz, stop["id"])

    cap = max_rows + 6
    parsed = parsed[:cap]
    for d in parsed:
        d["stations"] = {st["id"]: evaluate_station(d, st) for st in stations}

    walk_limit = now + timedelta(minutes=walk_min)
    shown = [d for d in parsed if d["_eff"] >= walk_limit][:max_rows]
    station_summary = summarize_stations(shown, stations)

    messages = collect_messages(parsed, now, tz, "main")

    connection_out: list[dict[str, Any]] = []
    for cfg in connections:
        transfer = {"id": cfg["transfer_id"], "name": cfg["transfer_name"]}
        target = make_station(cfg["target"])
        query_time = (connection_times or {}).get(cfg["transfer_id"], now)
        summary, c_parsed = evaluate_connection(
            connection_boards.get(cfg["transfer_id"]),
            transfer=transfer,
            target=target,
            query_time=max(query_time, now),
            now=now,
            tz=tz,
        )
        running = summary.pop("_running", [])
        c_messages = collect_messages(running or c_parsed, now, tz, f"conn{len(connection_out)}")
        summary["messages"] = [m["id"] for m in c_messages]
        if running and any(m["kind"] == "disruption" for m in c_messages) and summary["status"] == "ok":
            summary["status"] = "disrupted"
        elif summary["status"] == "ok" and summary["cancelled"]:
            summary["status"] = "disrupted"
        messages.extend(c_messages)
        connection_out.append(summary)

    departures_out = []
    for d in parsed:
        departures_out.append({k: v for k, v in d.items() if not k.startswith("_")})

    return {
        "stop": {"id": stop["id"], "name": stop["name"], "short": short_name(stop["name"])},
        "walk_min": walk_min,
        "max_rows": max_rows,
        "departures": departures_out,
        "stations": station_summary,
        "connections": connection_out,
        "messages": messages,
        "has_stop_data": any(d["_has_stops"] for d in parsed),
        "fetched_at": now.isoformat(),
    }


def connection_query_time(
    snapshot: dict[str, Any], transfer_id: str, now: datetime, buffer_min: int, walk_min: int
) -> datetime:
    """When will we be at `transfer_id`? (arrival of the first reachable service + buffer)."""
    limit = (now + timedelta(minutes=walk_min)).isoformat()
    for dep in snapshot["departures"]:
        if (dep["eff"] or "") < limit or dep["cancelled"]:
            continue
        st = dep["stations"].get(transfer_id, {})
        if st.get("state") == "served" and st.get("arr"):
            return max(now, datetime.fromisoformat(st["arr"]) + timedelta(minutes=buffer_min))
    return now


def refs_for_detail(
    board: dict[str, Any], stop_id: str, tz: tzinfo, now: datetime, walk_min: int, max_rows: int
) -> list[str]:
    """Journey refs worth a journeyDetail call (only used if the board has no stop lists)."""
    parsed = [
        parse_departure(d, tz, stop_id) for d in as_list(board.get("Departure")) if isinstance(d, dict)
    ]
    limit = now + timedelta(minutes=walk_min)
    parsed = sorted((d for d in parsed if d["_eff"] and d["_eff"] >= limit), key=lambda d: d["_eff"])
    return [d["_ref"] for d in parsed[:max_rows] if d["_ref"]]
