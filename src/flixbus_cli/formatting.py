"""Normalisierung der API-Antwort zu den Ausgabe-Objekten aus INTERFACE.md.

Wichtig (live verifiziert, siehe docs/ENDPOINTS.md):
* Die API liefert je Stadt einen eigenen UTC-Offset. Stuttgart +02:00,
  München +01:00 am selben Tag. Für die Anzeige wird deshalb alles auf den
  Offset der Abfahrtsstadt normalisiert.
* `intermediate_stations_count` fehlt bei manchen Ergebnissen.
* `trips[0].results` ist ein Dict, keine Liste.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any


def parse_api_datetime(value: str | None) -> datetime | None:
    """ISO-8601 mit Offset -> aware datetime. Ohne Offset -> Annahme +00:00."""
    if not value:
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def offset_from_seconds(seconds: Any) -> tzinfo | None:
    try:
        return timezone(timedelta(seconds=int(seconds)))
    except (TypeError, ValueError):
        return None


def to_local(moment: datetime | None, tz: tzinfo | None) -> datetime | None:
    """Umrechnung in die Zeitzone der Abfahrtsstadt."""
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(tz) if tz is not None else moment


def iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


def local_minutes(moment: datetime | None) -> int | None:
    """Abfahrtszeit als Minuten seit Mitternacht in lokaler Zeit."""
    if moment is None:
        return None
    return moment.hour * 60 + moment.minute


def duration_minutes(raw: Any) -> int | None:
    if not isinstance(raw, dict):
        return None
    try:
        return int(raw.get("hours") or 0) * 60 + int(raw.get("minutes") or 0)
    except (TypeError, ValueError):
        return None


def duration_text(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    return f"{minutes // 60}h{minutes % 60:02d}m"


def booking_url(from_id: str, to_id: str, day_iso: str, adults: int) -> str:
    from urllib.parse import quote

    return (
        "https://www.flixbus.de/suche?"
        f"departureCity={quote(from_id)}&arrivalCity={quote(to_id)}"
        f"&rideDate={quote(day_iso)}&adult={adults}"
    )


def is_direct(raw: dict[str, Any]) -> bool:
    key = str(raw.get("transfer_type_key") or "")
    if key == "direct":
        return True
    legs = raw.get("legs") or []
    return len(legs) == 1


def transfer_count(raw: dict[str, Any]) -> int:
    legs = raw.get("legs") or []
    return max(0, len(legs) - 1)


def build_stops(raw: dict[str, Any], stations: dict[str, Any], cities: dict[str, Any]) -> list[dict[str, Any]]:
    """Haltfolge aus `legs`. Es gibt keinen anonymous Detail-Endpunkt.

    Jedes Leg liefert Abfahrts- und Ankunftshaltestelle mit Zeit. Die
    Ankunft eines Legs ist die Abfahrt des nächsten (Umstieg am selben
    Bahnhof), deshalb wird nur der Umstiegspunkt einmal ausgegeben.
    """
    legs = [l for l in (raw.get("legs") or []) if isinstance(l, dict)]
    if not legs:
        return []
    tz = None
    first_dep = parse_api_datetime((legs[0].get("departure") or {}).get("date"))
    if first_dep is not None and first_dep.tzinfo is not None:
        tz = first_dep.tzinfo

    stops: list[dict[str, Any]] = []

    def station_name(station_id: str | None) -> str:
        info = (stations or {}).get(str(station_id or "")) or {}
        return str(info.get("name") or station_id or "")

    def city_name(city_id: str | None) -> str:
        info = (cities or {}).get(str(city_id or "")) or {}
        return str(info.get("name") or "")

    dep0 = legs[0].get("departure") or {}
    stops.append(
        {
            "type": "departure",
            "station": station_name(dep0.get("station_id")),
            "city": city_name(dep0.get("city_id")),
            "time": iso(to_local(parse_api_datetime(dep0.get("date")), tz)),
            "means_of_transport": str(legs[0].get("means_of_transport") or ""),
        }
    )
    for idx, leg in enumerate(legs[1:], start=1):
        arr = leg.get("departure") or {}
        stops.append(
            {
                "type": "transfer",
                "station": station_name(arr.get("station_id")),
                "city": city_name(arr.get("city_id")),
                "time": iso(to_local(parse_api_datetime(arr.get("date")), tz)),
                "means_of_transport": str(leg.get("means_of_transport") or ""),
            }
        )
    arr_last = legs[-1].get("arrival") or {}
    stops.append(
        {
            "type": "arrival",
            "station": station_name(arr_last.get("station_id")),
            "city": city_name(arr_last.get("city_id")),
            "time": iso(to_local(parse_api_datetime(arr_last.get("date")), tz)),
            "means_of_transport": str(legs[-1].get("means_of_transport") or ""),
        }
    )
    return stops


def normalise_trip(
    uid: str,
    raw: dict[str, Any],
    stations: dict[str, Any],
    cities: dict[str, Any],
    tz: tzinfo | None,
    *,
    from_id: str,
    to_id: str,
    day_iso: str,
    adults: int,
) -> dict[str, Any]:
    dep_raw = raw.get("departure") or {}
    arr_raw = raw.get("arrival") or {}
    dep = to_local(parse_api_datetime(dep_raw.get("date")), tz)
    arr = to_local(parse_api_datetime(arr_raw.get("date")), tz)

    price = raw.get("price") or {}
    available = raw.get("available") or {}
    remaining = raw.get("remaining") or {}
    restrictions = raw.get("restrictions") or {}

    legs = raw.get("legs") or []
    modes = {str(l.get("means_of_transport") or "") for l in legs if isinstance(l, dict)}
    modes.discard("")
    if not modes:
        service = "bus"
    elif modes == {"bus"}:
        service = "bus"
    elif modes == {"train"}:
        service = "train"
    elif "bus" in modes and "train" in modes:
        service = "mixed"
    else:
        service = "/".join(sorted(modes))

    seats = available.get("seats")
    if seats is None:
        seats = remaining.get("seats")
    total = price.get("total")

    dep_city_id = str(dep_raw.get("city_id") or from_id)
    arr_city_id = str(arr_raw.get("city_id") or to_id)

    trip: dict[str, Any] = {
        "trip_id": uid,
        "status": str(raw.get("status") or ""),
        "direct": is_direct(raw),
        "transfers": transfer_count(raw),
        "provider": raw.get("provider"),
        "departure": iso(dep),
        "arrival": iso(arr),
        "departure_station": str((stations or {}).get(str(dep_raw.get("station_id") or ""), {}).get("name") or ""),
        "arrival_station": str((stations or {}).get(str(arr_raw.get("station_id") or ""), {}).get("name") or ""),
        "departure_city": str((cities or {}).get(dep_city_id, {}).get("name") or ""),
        "arrival_city": str((cities or {}).get(arr_city_id, {}).get("name") or ""),
        "departure_station_id": dep_raw.get("station_id"),
        "arrival_station_id": arr_raw.get("station_id"),
        "duration_minutes": duration_minutes(raw.get("duration")),
        "price": total,
        "price_with_platform_fee": price.get("total_with_platform_fee"),
        "seats_available": seats,
        "bike_slots": available.get("bike_slots", remaining.get("bike_slots")),
        "capacity": remaining.get("capacity"),
        "means_of_transport": service,
        "bikes_allowed": restrictions.get("bikes_allowed"),
        "intermediate_stations_count": raw.get("intermediate_stations_count"),
        "booking_url": booking_url(from_id, to_id, day_iso, adults),
    }
    trip["duration_text"] = duration_text(trip["duration_minutes"])
    # Sortierschlüssel werden nicht ausgegeben.
    trip["_departure_minutes"] = local_minutes(dep)
    trip["_sort_departure"] = dep.timestamp() if dep else 0.0
    return trip


def strip_internal(trip: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in trip.items() if not k.startswith("_")}


def apply_filters(
    trips: list[dict[str, Any]],
    *,
    max_price: float | None = None,
    direct_only: bool = False,
    after: tuple[int, int] | None = None,
    before: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    after_m = after[0] * 60 + after[1] if after else None
    before_m = before[0] * 60 + before[1] if before else None
    for t in trips:
        price = t.get("price")
        if max_price is not None and (price is None or float(price) > max_price):
            continue
        if direct_only and not t.get("direct"):
            continue
        minutes = t.get("_departure_minutes")
        if (after_m is not None or before_m is not None) and minutes is None:
            continue
        if after_m is not None and minutes is not None and minutes < after_m:
            continue
        if before_m is not None and minutes is not None and minutes > before_m:
            continue
        out.append(t)
    return out


_SORT_KEYS = {
    "price": lambda t: (t.get("price") is None, t.get("price") or 0.0),
    "departure": lambda t: t.get("_sort_departure", 0.0),
    "duration": lambda t: (t.get("duration_minutes") is None, t.get("duration_minutes") or 0),
}


def sort_trips(trips: list[dict[str, Any]], order: str) -> list[dict[str, Any]]:
    key = _SORT_KEYS.get(order)
    if key is None:
        raise ValueError(f"Unbekannte Sortierung {order!r}.")
    return sorted(trips, key=key)