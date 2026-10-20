"""HTTP-Zugriff auf die Flix-JSON-API.

Alle Endpunkte, Felder und Fallstricke sind in docs/ENDPOINTS.md
dokumentiert und live verifiziert. Diese Schicht kapselt:

* HTTP/Netzwerk-Fehler   -> HttpError   (Exit 3)
* unlesbare Antwort     -> ParseError  (Exit 4)
* Eingabefehler          -> ValueError  (Exit 1)
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

import requests

DEFAULT_BASE_URL = "https://global.api.flixbus.com"
DEFAULT_TIMEOUT = 30.0
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

CITIES_PATH = "/search/autocomplete/cities"
STATIONS_PATH = "/search/autocomplete/stations"
SEARCH_PATH = "/search/service/v4/search"

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_MAX_HORIZON_DAYS = 400


class HttpError(Exception):
    """Netzwerk- oder HTTP-Fehler -> Exit 3."""


class ParseError(Exception):
    """Antwort nicht lesbar / unerwartetes Format -> Exit 4."""


# ---------- Hilfsfunktionen ----------


def base_url() -> str:
    """Basis-URL aus FLIX_BASE_URL (für Tests/Fixtures)."""
    raw = (os.environ.get("FLIX_BASE_URL") or DEFAULT_BASE_URL).strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"FLIX_BASE_URL ist keine gültige URL: {raw!r}")
    return raw.rstrip("/")


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "de-DE,de;q=0.9",
        }
    )
    return s


def _get_json(sess: requests.Session, url: str, params: dict[str, Any]) -> Any:
    try:
        resp = sess.get(url, params=params, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:  # DNS, TLS, Timeout, ...
        raise HttpError(f"Netzwerkfehler bei {url}: {exc}") from exc

    status = resp.status_code
    if status >= 400:
        detail = ""
        try:
            body = resp.json()
            if isinstance(body, dict):
                detail = str(body.get("message") or body.get("error") or "")
        except ValueError:
            detail = (resp.text or "")[:200]
        if status in (401, 403):
            raise HttpError(f"Zugriff verweigert (HTTP {status}): {detail}".strip())
        raise HttpError(f"HTTP {status} von {url}: {detail}".strip())

    try:
        return resp.json()
    except ValueError as exc:
        raise ParseError(f"Ungültiges JSON von {url}: {exc}") from exc


# ---------- Eingabevalidierung ----------


def parse_iso_date(value: str, *, today: date | None = None) -> date:
    """YYYY-MM-DD | heute | morgen -> date. Wirft ValueError bei Unsinn."""
    if value is None:
        raise ValueError("Datum fehlt.")
    raw = str(value).strip()
    if not raw:
        raise ValueError("Datum darf nicht leer sein.")
    low = raw.lower()
    base = today or date.today()
    if low == "heute":
        return base
    if low == "morgen":
        return base + timedelta(days=1)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        raise ValueError(
            f"Ungültiges Datum {raw!r}; erwartet YYYY-MM-DD, 'heute' oder 'morgen'."
        ) from None
    if parsed < base:
        raise ValueError(
            f"Datum {parsed.isoformat()} liegt in der Vergangenheit "
            f"(heute ist {base.isoformat()})."
        )
    if (parsed - base).days > _MAX_HORIZON_DAYS:
        raise ValueError(
            f"Datum {parsed.isoformat()} liegt mehr als {_MAX_HORIZON_DAYS} Tage in der Zukunft."
        )
    return parsed


def parse_clock(value: str) -> tuple[int, int]:
    """HH:MM -> (Stunde, Minute)."""
    raw = str(value).strip()
    m = _TIME_RE.match(raw)
    if not m:
        raise ValueError(f"Ungültige Uhrzeit {raw!r}; erwartet HH:MM (00:00–23:59).")
    return int(m.group(1)), int(m.group(2))


def parse_positive_int(
    value: Any, name: str, *, minimum: int = 1, maximum: int | None = None
) -> int:
    try:
        num = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{name} muss eine ganze Zahl sein, nicht {value!r}.") from None
    if num < minimum:
        raise ValueError(f"{name} muss mindestens {minimum} sein (ist {num}).")
    if maximum is not None and num > maximum:
        raise ValueError(f"{name} darf höchstens {maximum} sein (ist {num}).")
    return num


def parse_amount(value: Any, name: str) -> float:
    raw = str(value).strip().replace(",", ".")
    try:
        num = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} muss eine Zahl sein, nicht {value!r}.") from None
    if num != num or num in (float("inf"), float("-inf")):
        raise ValueError(f"{name} darf nicht NaN oder Inf sein.")
    if num <= 0:
        raise ValueError(f"{name} muss größer als 0 sein (ist {num:g}).")
    return num


def looks_like_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(str(value).strip()))


# ---------- Städte ----------


def _normalise_city(raw: dict[str, Any]) -> dict[str, Any]:
    loc = raw.get("location") or {}
    return {
        "id": str(raw.get("id") or ""),
        "name": str(raw.get("name") or ""),
        "country": str(raw.get("country") or ""),
        "district": raw.get("district"),
        "lat": loc.get("lat"),
        "lon": loc.get("lon"),
        "timezone_offset_seconds": raw.get("timezone_offset_seconds"),
        "is_flixbus_city": bool(raw.get("is_flixbus_city")),
        "legacy_id": raw.get("legacy_id"),
    }


def find_cities(query: str, *, sess: requests.Session | None = None) -> list[dict[str, Any]]:
    """Autocomplete für Städte. Wirft ValueError/HttpError/ParseError."""
    raw = (query or "").strip()
    if not raw:
        raise ValueError("Suchbegriff darf nicht leer sein.")
    sess = sess or session()
    data = _get_json(
        sess,
        base_url() + CITIES_PATH,
        {"q": raw, "lang": "de", "country": "de", "flixbus_cities_only": "false"},
    )
    if not isinstance(data, list):
        raise ParseError("Unerwartetes Antwortformat: Städteliste erwartet.")
    cities = [_normalise_city(c) for c in data if isinstance(c, dict)]
    return [c for c in cities if c["id"]]


def best_city_match(query: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Beste Übereinstimmung: exakter Name (case-insensitive) vor Präfix vor Teil."""
    raw = (query or "").strip().lower()
    if not candidates:
        return None
    for c in candidates:
        if c["name"].strip().lower() == raw:
            return c
    for c in candidates:
        if c["name"].strip().lower().startswith(raw):
            return c
    for c in candidates:
        if raw in c["name"].strip().lower():
            return c
    return None


def resolve_city(query: str, *, sess: requests.Session | None = None) -> dict[str, Any]:
    """Name oder UUID -> Stadt-Dict. Wirft ValueError mit Vorschlägen."""
    raw = (query or "").strip()
    if not raw:
        raise ValueError("Stadtname darf nicht leer sein.")
    if looks_like_uuid(raw):
        # Eine UUID kann nicht über Autocomplete aufgelöst werden; der Name
        # bleibt unbekannt, die ID ist aber gültig und wird direkt benutzt.
        # Der echte Name kommt dann aus der `cities`-Karte der Such-Antwort.
        return {
            "id": raw,
            "name": "",
            "country": "",
            "district": None,
            "lat": None,
            "lon": None,
            "timezone_offset_seconds": None,
            "is_flixbus_city": True,
            "legacy_id": None,
        }
    candidates = find_cities(raw, sess=sess)
    best = best_city_match(raw, candidates)
    if best is None:
        names = ", ".join(c["name"] for c in candidates[:8]) or "keine Vorschläge"
        raise ValueError(f"Stadt {raw!r} nicht gefunden. Vorschläge: {names}.")
    return best


# ---------- Suche ----------


def search_trips(
    from_id: str,
    to_id: str,
    day: date,
    *,
    adults: int = 1,
    sess: requests.Session | None = None,
) -> dict[str, Any]:
    """Roh-Suche. Gibt die ungefilterte API-Antwort zurück."""
    sess = sess or session()
    params = {
        "from_city_id": from_id,
        "to_city_id": to_id,
        "departure_date": day.strftime("%d.%m.%Y"),
        "products": json.dumps({"adult": adults}),
        "currency": "EUR",
        "locale": "de",
        "search_by": "cities",
        "include_after_midnight_rides": "1",
    }
    data = _get_json(sess, base_url() + SEARCH_PATH, params)
    if not isinstance(data, dict):
        raise ParseError("Unerwartetes Antwortformat: Objekt erwartet.")
    return data


def extract_results(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """trips[0].results -> Dict uid->trip.

    `results` kommt live als **Dict** (Schlüssel = uid), nicht als Liste.
    Beide Formen werden akzeptiert, weil das Format nicht garantiert ist.
    """
    trips = data.get("trips")
    if not isinstance(trips, list) or not trips:
        raise ParseError("Antwort enthält keine 'trips'-Liste.")
    first = trips[0]
    if not isinstance(first, dict):
        raise ParseError("Unerwartetes Format in trips[0].")
    results = first.get("results")
    if results is None:
        raise ParseError("Antwort enthält kein 'results'.")
    if isinstance(results, dict):
        return {k: v for k, v in results.items() if isinstance(v, dict)}
    if isinstance(results, list):
        out: dict[str, dict[str, Any]] = {}
        for idx, item in enumerate(results):
            if isinstance(item, dict):
                out[str(item.get("uid") or idx)] = item
        return out
    raise ParseError("Unerwartetes Format in trips[0].results.")