"""Synthetische JSON-Antworten für die Unit-Tests.

Diese Daten sind nicht live – sie spiegeln das Schema aus
``docs/ENDPOINTS.md`` wider und sind absichtlich handgeschrieben, damit
die Tests deterministisch sind und keine echten Server brauchen.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

STATION_HB_HBF = "dcbabcbb-0000-4000-8000-000000000001"
STATION_BERLIN_ZOB = "dcbabbfa-0000-4000-8000-000000000002"
STATION_HEIDELBERG = "dcbabcbc-0000-4000-8000-000000000003"
STATION_MANNHEIM = "dcbabccc-0000-4000-8000-000000000004"

CITY_HEILBRONN = "40d91420-0000-4000-8000-000000000010"
CITY_BERLIN = "40d8f682-0000-4000-8000-000000000020"
CITY_HEIDELBERG = "40d901a5-0000-4000-8000-000000000030"
CITY_MANNHEIM = "40d91111-0000-4000-8000-000000000040"


def make_search_response(
    *,
    results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Baut eine minimale Such-Antwort im Schema aus ENDPOINTS.md."""
    inner = {"results": dict(results) if results is not None else {}}
    return {
        "response_uuid": "test-response",
        "trips": [inner],
        "operators": [],
        "brands": [],
        "cities": {
            CITY_HEILBRONN: {"name": "Heilbronn", "slug": "heilbronn", "id": CITY_HEILBRONN},
            CITY_BERLIN: {"name": "Berlin", "slug": "berlin", "id": CITY_BERLIN},
            CITY_HEIDELBERG: {"name": "Heidelberg", "slug": "heidelberg", "id": CITY_HEIDELBERG},
            CITY_MANNHEIM: {"name": "Mannheim", "slug": "mannheim", "id": CITY_MANNHEIM},
        },
        "stations": {
            STATION_HB_HBF: {
                "id": STATION_HB_HBF, "legacy_id": 1,
                "name": "Heilbronn Hbf", "slug": "heilbronn", "is_train": True, "importance": 100,
            },
            STATION_BERLIN_ZOB: {
                "id": STATION_BERLIN_ZOB, "legacy_id": 2,
                "name": "Berlin ZOB", "slug": "berlin-zob", "is_train": False, "importance": 100,
            },
            STATION_HEIDELBERG: {
                "id": STATION_HEIDELBERG, "legacy_id": 3,
                "name": "Heidelberg Hbf", "slug": "heidelberg", "is_train": True, "importance": 80,
            },
            STATION_MANNHEIM: {
                "id": STATION_MANNHEIM, "legacy_id": 4,
                "name": "Mannheim Hbf", "slug": "mannheim", "is_train": True, "importance": 80,
            },
        },
    }


def make_cities_response(*items: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in items:
        out.append(deepcopy(item))
    return out


def make_trip(
    *,
    uid: str,
    departure_iso: str,
    arrival_iso: str,
    price: float = 19.99,
    platform_fee: float | None = 20.98,
    seats: int = 42,
    duration_minutes: int = 411,
    legs: list[dict[str, Any]] | None = None,
    direct: bool = True,
    provider: str = "flixbus",
    intermediate_count: int | None = 0,
) -> dict[str, Any]:
    """Baut einen einzelnen Trip (Ergebnis-Dict)."""
    if legs is None:
        legs = [
            {
                "ride_id": "ride-1",
                "departure": {
                    "date": departure_iso,
                    "city_id": CITY_HEILBRONN,
                    "station_id": STATION_HB_HBF,
                },
                "arrival": {
                    "date": arrival_iso,
                    "city_id": CITY_BERLIN,
                    "station_id": STATION_BERLIN_ZOB,
                },
                "means_of_transport": "bus",
                "amenities": ["WIFI"],
                "operator_id": "mfb",
                "brand_id": "flixbus",
            }
        ]
    return {
        "uid": uid,
        "status": "available",
        "transfer_type": "Direkt" if direct else "Umstieg",
        "transfer_type_key": "direct" if direct else "train#train",
        "provider": provider,
        "departure": {
            "date": departure_iso,
            "city_id": CITY_HEILBRONN,
            "station_id": STATION_HB_HBF,
        },
        "arrival": {
            "date": arrival_iso,
            "city_id": CITY_BERLIN,
            "station_id": STATION_BERLIN_ZOB,
        },
        "duration": {"hours": duration_minutes // 60, "minutes": duration_minutes % 60},
        "price": {
            "total": price,
            "original": price,
            "average": price,
            "total_with_platform_fee": platform_fee if platform_fee is not None else price,
            "average_with_platform_fee": platform_fee if platform_fee is not None else price,
        },
        "remaining": {
            "seats_left_at_price": None,
            "seats": seats,
            "bike_slots": 0,
            "capacity": "medium",
        },
        "available": {"seats": seats, "bike_slots": 0},
        "intermediate_stations_count": intermediate_count,
        "legs": legs,
        "messages": [],
        "restrictions": {
            "sale_restriction": False,
            "bikes_allowed": True,
            "wheelchair_status": "unknown",
        },
    }


# Stadt-Fixture für cities-Tests
HEILBRONN = {
    "id": CITY_HEILBRONN,
    "name": "Heilbronn",
    "country": "de",
    "district": "Baden-Württemberg",
    "location": {"lat": 49.168435, "lon": 9.219901},
    "timezone_offset_seconds": 7200,
    "legacy_id": 110,
    "is_flixbus_city": True,
    "score": 63.4,
}

BERLIN = {
    "id": CITY_BERLIN,
    "name": "Berlin",
    "country": "de",
    "district": None,
    "location": {"lat": 52.520007, "lon": 13.404954},
    "timezone_offset_seconds": 7200,
    "legacy_id": 1,
    "is_flixbus_city": True,
    "score": 50.0,
}

HEILBRONN_NECKARSULM = {
    "id": CITY_HEILBRONN.replace("0010", "0011"),
    "name": "Neckarsulm",
    "country": "de",
    "district": "Baden-Württemberg",
    "location": {"lat": 49.19, "lon": 9.22},
    "timezone_offset_seconds": 7200,
    "legacy_id": 111,
    "is_flixbus_city": True,
    "score": 19.2,
}


# Synthetische "process-trip" für cheapest-Tagesminimum-Checks
def build_day_response(*, day: date, prices: list[float]) -> dict[str, Any]:
    """Mehrere Trips an einem Tag (für cheapest-Smoke)."""
    results = {}
    base_hour = 6
    for i, p in enumerate(prices):
        dep = f"{day.isoformat()}T{base_hour + i:02d}:00:00+02:00"
        arr = f"{day.isoformat()}T{base_hour + i + 3:02d}:00:00+02:00"
        uid = f"direct:test-{day.isoformat()}-{i:03d}"
        results[uid] = make_trip(
            uid=uid,
            departure_iso=dep,
            arrival_iso=arr,
            price=p,
            duration_minutes=180,
        )
    return make_search_response(results=results)
