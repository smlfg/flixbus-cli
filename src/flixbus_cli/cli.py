"""CLI-Entry: Parser, Handler, zentrale Ausgabe- und Fehlerbehandlung.

Verbindlich ist INTERFACE.md. Kurzfassung der Regeln, die hier durchgesetzt
werden:

* Exit-Codes: 0 ok, 1 Usage, 2 Auth, 3 Netzwerk/HTTP, 4 Parse, 5 Forbidden.
* Mit `--json` steht auf stdout genau ein JSON-Objekt – auch bei Fehlern und
  auch bei Argumentfehlern.
* Nie ein Traceback auf stdout; Meldungen ohne `--json` gehen nach stderr.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from datetime import date, timedelta
from typing import Any, Callable

from . import __version__, api, formatting, watch
from .api import HttpError, ParseError

LOG = logging.getLogger("flixbus_cli")

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_AUTH = 2
EXIT_NETWORK = 3
EXIT_PARSE = 4
EXIT_FORBIDDEN = 5

_KIND_BY_EXIT = {
    EXIT_USAGE: "usage",
    EXIT_AUTH: "auth",
    EXIT_NETWORK: "network",
    EXIT_PARSE: "parse",
    EXIT_FORBIDDEN: "forbidden",
}

BOOK_MESSAGE = (
    "Buchen wird nicht unterstützt. Diese CLI liefert Suchergebnisse, "
    "Live-Preise, freie Plätze und Buchungs-Links – sie bucht nichts."
)

# Cache der zuletzt geladenen Trips im Prozess (für `flix trip`).
_TRIP_CACHE: dict[str, dict[str, Any]] = {}


# ---------- Zentrale Ausgabe ----------


def emit(payload: dict[str, Any], as_json: bool, text: str | None = None) -> int:
    if as_json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write((text if text is not None else _to_text(payload)) + "\n")
    return EXIT_OK


def fail(code: int, message: str, *, as_json: bool, kind: str | None = None) -> int:
    payload = {
        "error": {
            "code": code,
            "kind": kind or _KIND_BY_EXIT.get(code, "internal"),
            "message": message,
        }
    }
    if as_json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stderr.write(f"[{payload['error']['kind']}] exit {code}: {message}\n")
    return code


def _to_text(payload: dict[str, Any]) -> str:
    """Lesbare Darstellung für den Non-JSON-Modus."""
    lines: list[str] = []

    def render(value: Any, indent: int = 0) -> None:
        pad = "  " * indent
        if isinstance(value, dict):
            if isinstance(value.get("error"), dict):
                lines.append(f"{pad}Fehler: {value['error'].get('message')}")
                return
            for key, item in value.items():
                if isinstance(item, (dict, list)) and item:
                    lines.append(f"{pad}{key}:")
                    render(item, indent + 1)
                elif not isinstance(item, (dict, list)):
                    lines.append(f"{pad}{key}: {item}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    head = ", ".join(
                        f"{k}={item[k]}" for k in list(item)[:4] if not isinstance(item[k], (dict, list))
                    )
                    lines.append(f"{pad}- {head}")
                else:
                    lines.append(f"{pad}- {item}")
        else:
            lines.append(f"{pad}{value}")

    render(payload)
    return "\n".join(lines) if lines else ""


# ---------- cities ----------


def cmd_cities(args: argparse.Namespace, as_json: bool) -> int:
    query = (args.query or "").strip()
    limit = api.parse_positive_int(args.limit, "--limit", minimum=1, maximum=50)
    cities = api.find_cities(query)
    cities.sort(key=lambda c: (c["name"].strip().lower() != query.lower(), c["name"].strip().lower()))
    selected = cities[:limit]
    return emit({"query": query, "cities": selected, "count": len(selected)}, as_json)


# ---------- search ----------


def _resolve_pair(args: argparse.Namespace):
    day = api.parse_iso_date(args.date)
    adults = api.parse_positive_int(args.adults, "--adults", minimum=1, maximum=9)
    max_price = api.parse_amount(args.max_price, "--max-price") if args.max_price is not None else None
    after = api.parse_clock(args.after) if args.after else None
    before = api.parse_clock(args.before) if args.before else None
    if after is not None and before is not None and after > before:
        raise ValueError("--after darf nicht später als --before sein.")
    origin = api.resolve_city(args.origin)
    dest = api.resolve_city(args.destination)
    if origin["id"] == dest["id"]:
        raise ValueError("Abfahrts- und Zielstadt sind identisch.")
    return origin, dest, day, adults, max_price, after, before


def _run_search(
    origin: dict[str, Any],
    dest: dict[str, Any],
    day: date,
    adults: int,
    *,
    max_price: float | None = None,
    direct_only: bool = False,
    after: tuple[int, int] | None = None,
    before: tuple[int, int] | None = None,
    order: str = "departure",
    limit: int = 20,
    cache: bool = True,
) -> dict[str, Any]:
    """Sucht und normalisiert. Wird von search/cheapest/watch check benutzt."""
    sess = api.session()
    raw = api.search_trips(origin["id"], dest["id"], day, adults=adults, sess=sess)
    results = api.extract_results(raw)
    stations = raw.get("stations") or {}
    cities_map = raw.get("cities") or {}

    tz = formatting.offset_from_seconds(origin.get("timezone_offset_seconds"))
    if tz is None:
        for candidate in results.values():
            first_dep = formatting.parse_api_datetime((candidate.get("departure") or {}).get("date"))
            if first_dep is not None and first_dep.tzinfo is not None:
                tz = first_dep.tzinfo
                break

    day_iso = day.isoformat()
    trips = [
        formatting.normalise_trip(
            uid, raw_trip, stations, cities_map, tz,
            from_id=origin["id"], to_id=dest["id"], day_iso=day_iso, adults=adults,
        )
        for uid, raw_trip in results.items()
    ]

    if cache:
        for uid, raw_trip in results.items():
            _TRIP_CACHE[uid] = {
                "raw": raw_trip,
                "stations": stations,
                "cities": cities_map,
                "tz": tz,
                "origin": origin,
            }

    trips = formatting.apply_filters(
        trips, max_price=max_price, direct_only=direct_only, after=after, before=before
    )
    trips = formatting.sort_trips(trips, order)
    return {"trips": trips[:limit], "total": len(trips), "stations": stations, "cities": cities_map}


def _city_name(city: dict[str, Any], cities_map: dict[str, Any]) -> str:
    if city.get("name"):
        return city["name"]
    info = cities_map.get(city["id"]) or {}
    return str(info.get("name") or "")


def cmd_search(args: argparse.Namespace, as_json: bool) -> int:
    origin, dest, day, adults, max_price, after, before = _resolve_pair(args)
    order = str(args.sort or "departure")
    if order not in ("price", "departure", "duration"):
        raise ValueError(f"Unbekanntes --sort {order!r}; erlaubt: price, departure, duration.")
    limit = api.parse_positive_int(args.limit, "--limit", minimum=1, maximum=200)

    result = _run_search(
        origin, dest, day, adults,
        max_price=max_price, direct_only=bool(args.direct),
        after=after, before=before, order=order, limit=limit,
    )
    trips = [formatting.strip_internal(t) for t in result["trips"]]
    payload = {
        "from": {
            "query": args.origin,
            "id": origin["id"],
            "name": _city_name(origin, result["cities"]),
            "country": origin.get("country") or "",
            "timezone_offset_seconds": origin.get("timezone_offset_seconds"),
        },
        "to": {
            "query": args.destination,
            "id": dest["id"],
            "name": _city_name(dest, result["cities"]),
            "country": dest.get("country") or "",
            "timezone_offset_seconds": dest.get("timezone_offset_seconds"),
        },
        "date": day.isoformat(),
        "currency": "EUR",
        "adults": adults,
        "count": len(trips),
        "filters": {"max_price": max_price, "direct": bool(args.direct), "after": args.after, "before": args.before},
        "trips": trips,
    }
    return emit(payload, as_json)


# ---------- trip ----------


def cmd_trip(args: argparse.Namespace, as_json: bool) -> int:
    trip_id = (args.trip_id or "").strip()
    if not trip_id:
        raise ValueError("TRIP_ID darf nicht leer sein.")

    cached = _TRIP_CACHE.get(trip_id)
    if cached is None:
        raise ParseError(
            f"Trip {trip_id!r} ist nicht bekannt. `flix trip` zeigt die Halte "
            "einer Verbindung aus der Ausgabe von `flix search`; Flix bietet "
            "keinen anonym erreichbaren Fahrtdetails-Endpunkt."
        )

    raw = cached["raw"]
    tz = cached["tz"]
    stops = formatting.build_stops(raw, cached["stations"], cached["cities"], tz)
    dep = stops[0] if stops else {}
    arr = stops[-1] if stops else {}
    minutes = formatting.duration_minutes(raw.get("duration"))
    price = raw.get("price") or {}
    available = raw.get("available") or {}
    remaining = raw.get("remaining") or {}
    seats = available.get("seats")
    if seats is None:
        seats = remaining.get("seats")

    payload = {
        "trip_id": trip_id,
        "status": str(raw.get("status") or ""),
        "from": {"city": dep.get("city"), "station": dep.get("station"), "time": dep.get("time")},
        "to": {"city": arr.get("city"), "station": arr.get("station"), "time": arr.get("time")},
        "duration_minutes": minutes,
        "duration_text": formatting.duration_text(minutes),
        "direct": formatting.is_direct(raw),
        "transfers": formatting.transfer_count(raw),
        "price": price.get("total"),
        "price_with_platform_fee": price.get("total_with_platform_fee"),
        "seats_available": seats,
        "stops": stops,
        "timezone": str(tz) if tz is not None else None,
    }
    return emit(payload, as_json)


# ---------- cheapest ----------


def cmd_cheapest(args: argparse.Namespace, as_json: bool) -> int:
    start = api.parse_iso_date(args.from_date)
    days = api.parse_positive_int(args.days, "--days", minimum=1, maximum=14)
    adults = api.parse_positive_int(args.adults, "--adults", minimum=1, maximum=9)
    origin = api.resolve_city(args.origin)
    dest = api.resolve_city(args.destination)
    if origin["id"] == dest["id"]:
        raise ValueError("Abfahrts- und Zielstadt sind identisch.")

    daily: list[dict[str, Any]] = []
    cities_map: dict[str, Any] = {}
    for offset in range(days):
        day = start + timedelta(days=offset)
        result = _run_search(origin, dest, day, adults, order="price", limit=1, cache=False)
        if not cities_map:
            cities_map = result["cities"]
        cheapest = result["trips"][0].get("price") if result["trips"] else None
        daily.append({"date": day.isoformat(), "price": cheapest, "trips": result["total"]})

    priced = [d for d in daily if d["price"] is not None]
    best = min(priced, key=lambda d: d["price"]) if priced else None
    payload = {
        "from": {"id": origin["id"], "name": _city_name(origin, cities_map)},
        "to": {"id": dest["id"], "name": _city_name(dest, cities_map)},
        "start_date": start.isoformat(),
        "days": days,
        "currency": "EUR",
        "daily": daily,
        "best": best,
    }
    return emit(payload, as_json)


# ---------- watch ----------


def cmd_watch(args: argparse.Namespace, as_json: bool) -> int:
    sub = getattr(args, "watch_cmd", None)
    if sub == "add":
        below = api.parse_amount(args.below, "--below")
        day = api.parse_iso_date(args.date)
        adults = api.parse_positive_int(args.adults, "--adults", minimum=1, maximum=9)
        origin = api.resolve_city(args.origin)
        dest = api.resolve_city(args.destination)
        if origin["id"] == dest["id"]:
            raise ValueError("Abfahrts- und Zielstadt sind identisch.")
        entry = watch.add(origin, dest, day.isoformat(), below, adults)
        return emit({"watch": entry, "path": watch.watch_path()}, as_json)

    if sub == "list":
        items = watch.all_entries()
        return emit({"items": items, "count": len(items), "path": watch.watch_path()}, as_json)

    if sub == "remove":
        wid = (args.id or "").strip()
        if not wid:
            raise ValueError("ID darf nicht leer sein.")
        existed, _ = watch.remove(wid)
        return emit({"removed": existed, "noop": not existed, "id": wid}, as_json)

    if sub == "check":
        items = watch.all_entries()
        results: list[dict[str, Any]] = []
        below_count = 0
        for entry in items:
            below = float(entry.get("below") or 0)
            day = date.fromisoformat(str(entry["date"]))
            adults = int(entry.get("adults") or 1)
            origin = {"id": entry["from"]["id"], "name": entry["from"].get("name")}
            dest = {"id": entry["to"]["id"], "name": entry["to"].get("name")}
            result = _run_search(origin, dest, day, adults, order="price", limit=1, cache=False)
            cheapest = result["trips"][0].get("price") if result["trips"] else None
            matches = cheapest is not None and float(cheapest) <= below
            below_count += 1 if matches else 0
            results.append(
                {
                    "id": entry["id"],
                    "from": entry["from"],
                    "to": entry["to"],
                    "date": entry["date"],
                    "below": below,
                    "cheapest": cheapest,
                    "trips": result["total"],
                    "matches": matches,
                }
            )
        return emit({"checked": len(items), "below_threshold": below_count, "results": results}, as_json)

    return emit(
        {
            "hint": "watch add FROM TO --date YYYY-MM-DD --below EUR | watch list | watch remove ID | watch check",
            "items": watch.all_entries(),
        },
        as_json,
    )


# ---------- book (forbidden) ----------


def cmd_book(args: argparse.Namespace, as_json: bool) -> int:
    # Kein Request an Flix. Es wird bewusst nichts gebucht.
    return fail(EXIT_FORBIDDEN, BOOK_MESSAGE, as_json=as_json)


# ---------- Parser ----------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flix",
        description=(
            "flix – Agent-CLI für FlixBus/FlixTrain. Städte finden, Verbindungen "
            "mit Live-Preisen suchen, Halte ansehen, günstigsten Tag suchen, "
            "Preise lokal beobachten. Buchen wird nicht unterstützt."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--json", action="store_true", help="Genau ein JSON-Objekt auf stdout.")

    sub = parser.add_subparsers(dest="cmd", required=False)

    p_cities = sub.add_parser("cities", help="Städte nach Name suchen")
    p_cities.add_argument("query", nargs="?", default="", help="Suchbegriff")
    p_cities.add_argument("--limit", default="10", help="Maximale Trefferzahl (1–50)")
    p_cities.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    p_search = sub.add_parser("search", help="Verbindungen suchen")
    p_search.add_argument("origin", help="Stadtname oder City-UUID")
    p_search.add_argument("destination", help="Stadtname oder City-UUID")
    p_search.add_argument("--date", default="heute", help="YYYY-MM-DD | heute | morgen")
    p_search.add_argument("--adults", default="1", help="Erwachsene (1–9)")
    p_search.add_argument("--max-price", dest="max_price", default=None, help="Höchstpreis in EUR")
    p_search.add_argument("--direct", action="store_true", help="Nur Direktverbindungen")
    p_search.add_argument("--after", default=None, help="Abfahrt frühestens HH:MM")
    p_search.add_argument("--before", default=None, help="Abfahrt spätestens HH:MM")
    p_search.add_argument("--sort", default="departure", help="price | departure | duration")
    p_search.add_argument("--limit", default="20", help="Maximale Trefferzahl")
    p_search.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    p_trip = sub.add_parser("trip", help="Halte einer Verbindung anzeigen")
    p_trip.add_argument("trip_id", help="trip_id aus der search-Ausgabe")
    p_trip.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    p_cheap = sub.add_parser("cheapest", help="Günstigsten Tag im Zeitraum finden")
    p_cheap.add_argument("origin", help="Stadtname oder City-UUID")
    p_cheap.add_argument("destination", help="Stadtname oder City-UUID")
    p_cheap.add_argument("--from", dest="from_date", default="heute", help="YYYY-MM-DD | heute | morgen")
    p_cheap.add_argument("--days", default="7", help="Anzahl Tage (1–14)")
    p_cheap.add_argument("--adults", default="1", help="Erwachsene (1–9)")
    p_cheap.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    p_watch = sub.add_parser("watch", help="Lokaler Preis-Watch")
    wsub = p_watch.add_subparsers(dest="watch_cmd", required=False)
    w_add = wsub.add_parser("add", help="Watch hinzufügen")
    w_add.add_argument("origin", help="Stadtname oder City-UUID")
    w_add.add_argument("destination", help="Stadtname oder City-UUID")
    w_add.add_argument("--date", default="heute", help="YYYY-MM-DD | heute | morgen")
    w_add.add_argument("--below", default=None, help="Schwellwert in EUR")
    w_add.add_argument("--adults", default="1", help="Erwachsene (1–9)")
    w_add.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    wsub.add_parser("list", help="Watch-Liste").add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    w_rm = wsub.add_parser("remove", help="Watch entfernen (idempotent)")
    w_rm.add_argument("id", help="ID aus watch list")
    w_rm.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    wsub.add_parser("check", help="Alle Watches live prüfen").add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    p_watch.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    p_book = sub.add_parser("book", help="NICHT unterstützt (immer Exit 5)")
    p_book.add_argument("args", nargs=argparse.REMAINDER, help="wird ignoriert")
    p_book.add_argument("--confirm", action="store_true", help="wird ignoriert; Buchen bleibt Exit 5")
    p_book.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    return parser


HANDLERS: dict[str, Callable[[argparse.Namespace, bool], int]] = {
    "cities": cmd_cities,
    "search": cmd_search,
    "trip": cmd_trip,
    "cheapest": cmd_cheapest,
    "watch": cmd_watch,
    "book": cmd_book,
}


# ---------- main ----------


def _split_json_flag(raw: list[str]) -> tuple[bool, list[str]]:
    as_json = False
    rest: list[str] = []
    for token in raw:
        if token == "--json":
            as_json = True
        elif token.startswith("--json="):
            as_json = True
        else:
            rest.append(token)
    return as_json, rest


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    raw = list(argv if argv is not None else sys.argv[1:])
    as_json, filtered = _split_json_flag(raw)

    parser = build_parser()
    try:
        args = parser.parse_args(filtered)
    except SystemExit as exc:
        if exc.code == 0:  # --help / --version
            raise
        if as_json:
            return fail(EXIT_USAGE, "Ungültige Argumente. Siehe `flix --help`.", as_json=True)
        return EXIT_USAGE

    if args.cmd is None:
        if as_json:
            return emit(
                {"commands": ["cities", "search", "trip", "cheapest", "watch", "book"], "version": __version__},
                as_json,
            )
        parser.print_help()
        return EXIT_OK

    handler = HANDLERS.get(args.cmd)
    if handler is None:
        return fail(EXIT_USAGE, f"Unbekannter Befehl: {args.cmd}", as_json=as_json)

    try:
        return handler(args, as_json=as_json)
    except ValueError as exc:
        return fail(EXIT_USAGE, str(exc), as_json=as_json)
    except HttpError as exc:
        return fail(EXIT_NETWORK, str(exc), as_json=as_json)
    except ParseError as exc:
        return fail(EXIT_PARSE, str(exc), as_json=as_json)
    except Exception as exc:  # letzter Schutz: nie ein Traceback auf stdout
        LOG.error("unerwarteter Fehler: %s", exc)
        LOG.debug(traceback.format_exc())
        return fail(EXIT_PARSE, f"Unerwarteter Fehler: {exc}", as_json=as_json, kind="internal")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())