"""Normalisierung der API-Antwort zu den Ausgabe-Objekten aus INTERFACE.md.

Wichtig (live verifiziert, siehe docs/ENDPOINTS.md):
* Die API liefert pro Zeitstempel einen eigenen UTC-Offset
  (z. B. `+02:00` für Stuttgart und `+01:00` für München am selben Tag,
  insbesondere rund um die Sommerzeitumstellung). Für die Ausgabe
  wird der Original-Offset beibehalten – es wird **nicht** auf einen
  festen Offset normalisiert. Dauer wird aus echten Instants berechnet.
* `intermediate_stations_count` fehlt bei manchen Ergebnissen.
* `trips[0].results` ist ein Dict, keine Liste.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo
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
    """Umrechnung in die Ziel-Zeitzone. Nur für Sortier-/Filterschlüssel.

    Für die *Ausgabe* wird der Original-Offset beibehalten (``iso(moment)``);
    diese Funktion ist ausschließlich für abgeleitete Werte gedacht.
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(tz) if tz is not None else moment


def iso(moment: datetime | None) -> str | None:
    """ISO-String mit Original-Offset des Zeitstempels (UTC falls naive)."""
    if moment is None:
        return None
    return moment.isoformat()


def instant_diff_minutes(start: datetime | None, end: datetime | None) -> int | None:
    """Differenz in Minuten aus echten aware-Instants.

    Beide Zeitstempel werden zuerst in UTC umgerechnet, damit
    Sommer-/Winterzeit-Sprünge und unterschiedliche Offsets
    (``+02:00`` vs ``+01:00`` am DST-Tag) korrekt verrechnet werden.
    Gibt ``None`` zurück, wenn mindestens ein Zeitstempel fehlt.
    """
    if start is None or end is None:
        return None
    s = start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
    e = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
    delta = e.astimezone(timezone.utc) - s.astimezone(timezone.utc)
    return int(delta.total_seconds() // 60)


def offset_seconds(moment: datetime | None) -> int | None:
    """UTC-Offset eines Zeitstempels in Sekunden (für interne Felder)."""
    if moment is None or moment.tzinfo is None:
        return None
    off = moment.utcoffset()
    return int(off.total_seconds()) if off is not None else 0


def offset_label(moment: datetime | None) -> str | None:
    """"+02:00" / "-05:30" für einen Zeitstempel mit Offset.

    Wird für Felder benutzt, die eine Zone *bezeichnen* (z. B. das
    ``timezone``-Feld von ``flix trip``). Der Offset muss aus dem
    Zeitstempel selbst stammen: ``timezone_offset_seconds`` der Stadt
    beschreibt den Offset *heute* und ist nach dem Ende der Sommerzeit
    um eine Stunde falsch – die Abfahrtszeit trägt dann ``+01:00``,
    während die Stadt noch ``+02:00`` meldet.
    """
    if moment is None or moment.tzinfo is None:
        return None
    off = moment.utcoffset()
    if off is None:
        return None
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def local_minutes(moment: datetime | None, tz: tzinfo | None = None) -> int | None:
    """Minuten seit Mitternacht für Filter (in der lokalen Zone ``tz``)."""
    if moment is None:
        return None
    target = moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
    if tz is not None:
        target = target.astimezone(tz)
    return target.hour * 60 + target.minute


def departs_on_day(moment: datetime | None, day: date, tz: tzinfo | None = None) -> bool:
    """True, wenn die Abfahrt am Kalendertag ``day`` in der Origin-Zeitzone liegt.

    Die Flix-Suche mit ``include_after_midnight_rides=1`` liefert auch Fahrten
    nach Mitternacht des Folgetags; die werden hier ausgeschlossen.
    """
    local = to_local(moment, tz)
    if local is None:
        return False
    return local.date() == day


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


def _station_name(stations: dict[str, Any] | None, station_id: Any) -> str:
    info = (stations or {}).get(str(station_id or "")) or {}
    return str(info.get("name") or station_id or "")


def _city_name(cities: dict[str, Any] | None, city_id: Any) -> str:
    info = (cities or {}).get(str(city_id or "")) or {}
    return str(info.get("name") or "")


def leg_dep_time(leg: dict[str, Any]) -> datetime | None:
    return parse_api_datetime((leg.get("departure") or {}).get("date"))


def leg_arr_time(leg: dict[str, Any]) -> datetime | None:
    return parse_api_datetime((leg.get("arrival") or {}).get("date"))


def trip_dep_time(raw: dict[str, Any]) -> datetime | None:
    return parse_api_datetime((raw.get("departure") or {}).get("date"))


def trip_arr_time(raw: dict[str, Any]) -> datetime | None:
    return parse_api_datetime((raw.get("arrival") or {}).get("date"))


def build_stops(
    raw: dict[str, Any],
    stations: dict[str, Any],
    cities: dict[str, Any],
    tz: tzinfo | None = None,
) -> list[dict[str, Any]]:
    """Haltfolge aus `legs`. Es gibt keinen anonymous Detail-Endpunkt.

    Jedes Leg liefert Abfahrts- und Ankunftshaltestelle mit Zeit. Die
    Ankunft eines Legs ist die Abfahrt des nächsten (Umstieg am selben
    Bahnhof), deshalb wird der Umstiegspunkt nur einmal ausgegeben.

    Die Zeiten werden mit dem von der API gelieferten Original-Offset
    ausgegeben – nicht auf einen festen Offset normalisiert. ``tz`` wird
    nur als Fallback benutzt, falls die API für einen Halt versehentlich
    keinen Offset liefert.
    """
    legs = [l for l in (raw.get("legs") or []) if isinstance(l, dict)]
    if not legs:
        return []

    def station_name(station_id: str | None) -> str:
        return _station_name(stations, station_id)

    def city_name(city_id: str | None) -> str:
        return _city_name(cities, city_id)

    stops: list[dict[str, Any]] = []
    dep0 = legs[0].get("departure") or {}
    dep0_moment = parse_api_datetime(dep0.get("date"))
    if dep0_moment is not None and dep0_moment.tzinfo is None and tz is not None:
        dep0_moment = dep0_moment.replace(tzinfo=tz)
    stops.append(
        {
            "type": "departure",
            "station": station_name(dep0.get("station_id")),
            "city": city_name(dep0.get("city_id")),
            "time": iso(dep0_moment),
            "means_of_transport": str(legs[0].get("means_of_transport") or ""),
        }
    )
    for leg in legs[1:]:
        arr = leg.get("departure") or {}
        arr_moment = parse_api_datetime(arr.get("date"))
        if arr_moment is not None and arr_moment.tzinfo is None and tz is not None:
            arr_moment = arr_moment.replace(tzinfo=tz)
        stops.append(
            {
                "type": "transfer",
                "station": station_name(arr.get("station_id")),
                "city": city_name(arr.get("city_id")),
                "time": iso(arr_moment),
                "means_of_transport": str(leg.get("means_of_transport") or ""),
            }
        )
    arr_last = legs[-1].get("arrival") or {}
    arr_last_moment = parse_api_datetime(arr_last.get("date"))
    if arr_last_moment is not None and arr_last_moment.tzinfo is None and tz is not None:
        arr_last_moment = arr_last_moment.replace(tzinfo=tz)
    stops.append(
        {
            "type": "arrival",
            "station": station_name(arr_last.get("station_id")),
            "city": city_name(arr_last.get("city_id")),
            "time": iso(arr_last_moment),
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
    """Normalisiert einen Roh-Trip.

    ``tz`` ist der Offset der Abfahrtsstadt. Er wird **nur** als Fallback
    für Zeitstempel ohne Offset und für abgeleitete Werte (Filter,
    Sortierung, Dauer) benutzt; ausgegeben werden die Original-Offsets
    der API.
    """
    dep_raw = raw.get("departure") or {}
    arr_raw = raw.get("arrival") or {}
    dep_moment = trip_dep_time(raw)
    arr_moment = trip_arr_time(raw)
    if dep_moment is not None and dep_moment.tzinfo is None and tz is not None:
        dep_moment = dep_moment.replace(tzinfo=tz)
    if arr_moment is not None and arr_moment.tzinfo is None and tz is not None:
        arr_moment = arr_moment.replace(tzinfo=tz)

    price = raw.get("price") or {}
    available = raw.get("available") or {}
    remaining = raw.get("remaining") or {}
    restrictions = raw.get("restrictions") or {}

    legs = raw.get("legs") or []
    modes = {str(l.get("means_of_transport") or "") for l in legs if isinstance(l, dict)}
    modes.discard("")
    if not modes or modes == {"bus"}:
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

    minutes = instant_diff_minutes(dep_moment, arr_moment)
    api_minutes = duration_minutes(raw.get("duration"))
    if minutes is None:
        minutes = api_minutes

    trip: dict[str, Any] = {
        "trip_id": uid,
        "status": str(raw.get("status") or ""),
        "direct": is_direct(raw),
        "transfers": transfer_count(raw),
        "provider": raw.get("provider"),
        "departure": iso(dep_moment),
        "arrival": iso(arr_moment),
        "departure_offset": offset_seconds(dep_moment),
        "arrival_offset": offset_seconds(arr_moment),
        "departure_station": _station_name(stations, dep_raw.get("station_id")),
        "arrival_station": _station_name(stations, arr_raw.get("station_id")),
        "departure_city": _city_name(cities, dep_city_id),
        "arrival_city": _city_name(cities, arr_city_id),
        "departure_station_id": dep_raw.get("station_id"),
        "arrival_station_id": arr_raw.get("station_id"),
        "duration_minutes": minutes,
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
    trip["_departure_minutes"] = local_minutes(dep_moment, tz=tz)
    trip["_sort_departure"] = dep_moment.timestamp() if dep_moment else 0.0
    return trip


def strip_internal(trip: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in trip.items() if not k.startswith("_")}


def duration_minutes(raw: Any) -> int | None:
    if not isinstance(raw, dict):
        return None
    try:
        return int(raw.get("hours") or 0) * 60 + int(raw.get("minutes") or 0)
    except (TypeError, ValueError):
        return None


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
