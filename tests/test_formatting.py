"""Tests für ``flixbus_cli.formatting``: Parser, Filter, Sort, Dauer."""

from __future__ import annotations

from datetime import date

import pytest

from flixbus_cli import formatting

from _fixtures import (
    CITY_HEILBRONN,
    STATION_BERLIN_ZOB,
    STATION_HB_HBF,
    STATION_HEIDELBERG,
    make_search_response,
    make_trip,
)


def _stations() -> dict[str, dict]:
    return make_search_response()["stations"]


def _cities() -> dict[str, dict]:
    return make_search_response()["cities"]


class TestParseApiDatetime:
    def test_with_offset(self) -> None:
        dt = formatting.parse_api_datetime("2026-10-25T07:06:00+02:00")
        assert dt is not None
        assert dt.hour == 7
        assert dt.tzinfo is not None
        assert dt.utcoffset().total_seconds() == 7200

    def test_with_z(self) -> None:
        dt = formatting.parse_api_datetime("2026-10-25T05:06:00Z")
        assert dt is not None
        assert dt.utcoffset().total_seconds() == 0

    def test_invalid(self) -> None:
        assert formatting.parse_api_datetime("not-a-date") is None
        assert formatting.parse_api_datetime("") is None
        assert formatting.parse_api_datetime(None) is None


class TestInstantDiffMinutes:
    def test_same_offset(self) -> None:
        start = formatting.parse_api_datetime("2026-10-25T07:06:00+02:00")
        end = formatting.parse_api_datetime("2026-10-25T13:57:00+02:00")
        assert formatting.instant_diff_minutes(start, end) == 411

    def test_dst_crossing_plus2_to_plus1(self) -> None:
        """2026-10-25 03:00 +02:00 -> 03:30 +01:00 = 90 Minuten (die Uhr
        springt um 03:00 -> 02:00, also dauert 03:00->03:30 +01:00
        eine echte Stunde und 30 Minuten Wandzeit).
        """
        start = formatting.parse_api_datetime("2026-10-25T03:00:00+02:00")
        end = formatting.parse_api_datetime("2026-10-25T03:30:00+01:00")
        # Wandzeit: 03:00+02 ist 01:00 UTC, 03:30+01 ist 02:30 UTC → 90 Min.
        assert formatting.instant_diff_minutes(start, end) == 90

    def test_none(self) -> None:
        assert formatting.instant_diff_minutes(None, None) is None


class TestOffsetFromSeconds:
    def test_ok(self) -> None:
        tz = formatting.offset_from_seconds(7200)
        assert tz is not None
        assert tz.utcoffset(None).total_seconds() == 7200

    @pytest.mark.parametrize("raw", [None, "abc"])
    def test_invalid(self, raw) -> None:
        assert formatting.offset_from_seconds(raw) is None


class TestApplyFilters:
    def test_max_price(self) -> None:
        trips = [
            {"price": 10.0, "_departure_minutes": 60, "direct": True},
            {"price": 25.0, "_departure_minutes": 60, "direct": True},
            {"price": 15.0, "_departure_minutes": 60, "direct": True},
        ]
        out = formatting.apply_filters(trips, max_price=15.0)
        assert len(out) == 2
        assert all(t["price"] <= 15 for t in out)

    def test_direct_only(self) -> None:
        trips = [
            {"price": 10.0, "_departure_minutes": 60, "direct": True},
            {"price": 25.0, "_departure_minutes": 60, "direct": False},
        ]
        out = formatting.apply_filters(trips, direct_only=True)
        assert len(out) == 1
        assert out[0]["direct"] is True

    def test_after_before(self) -> None:
        trips = [
            {"price": 10.0, "_departure_minutes": 8 * 60 + 30, "direct": True},
            {"price": 10.0, "_departure_minutes": 12 * 60, "direct": True},
            {"price": 10.0, "_departure_minutes": 18 * 60 + 30, "direct": True},
        ]
        out = formatting.apply_filters(
            trips, after=(9, 0), before=(18, 0)
        )
        assert len(out) == 1
        assert 9 * 60 <= out[0]["_departure_minutes"] <= 18 * 60

    def test_after_or_before_only(self) -> None:
        trips = [
            {"price": 10.0, "_departure_minutes": 7 * 60, "direct": True},
            {"price": 10.0, "_departure_minutes": 10 * 60, "direct": True},
        ]
        # nur before
        out = formatting.apply_filters(trips, before=(8, 0))
        assert [t["_departure_minutes"] for t in out] == [7 * 60]

    def test_no_filter(self) -> None:
        trips = [{"price": 10.0, "_departure_minutes": 60, "direct": True}]
        assert formatting.apply_filters(trips) == trips


class TestSortTrips:
    def test_price(self) -> None:
        trips = [{"price": 30, "_sort_departure": 0, "duration_minutes": 100},
                 {"price": 10, "_sort_departure": 0, "duration_minutes": 100},
                 {"price": 20, "_sort_departure": 0, "duration_minutes": 100}]
        out = formatting.sort_trips(trips, "price")
        assert [t["price"] for t in out] == [10, 20, 30]

    def test_departure(self) -> None:
        trips = [{"price": 10, "_sort_departure": 300, "duration_minutes": 100},
                 {"price": 10, "_sort_departure": 100, "duration_minutes": 100}]
        out = formatting.sort_trips(trips, "departure")
        assert [t["_sort_departure"] for t in out] == [100, 300]

    def test_duration(self) -> None:
        trips = [{"price": 10, "_sort_departure": 0, "duration_minutes": 90},
                 {"price": 10, "_sort_departure": 0, "duration_minutes": 30}]
        out = formatting.sort_trips(trips, "duration")
        assert [t["duration_minutes"] for t in out] == [30, 90]

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unbekannte Sortierung"):
            formatting.sort_trips([], "random")


class TestNormaliseTrip:
    def test_keeps_per_timestamp_offset_dst_boundary(self) -> None:
        """Regressionstest: Abflug vor DST-Ende (+02:00), Ankunft danach
        (+01:00) – jeder Zeitstempel behält seinen Original-Offset."""
        trip = make_trip(
            uid="direct:dst",
            departure_iso="2026-10-25T03:00:00+02:00",
            arrival_iso="2026-10-25T03:30:00+01:00",
            price=19.99,
            duration_minutes=120,  # api-seitig (bewusst falsch für den Test)
        )
        out = formatting.normalise_trip(
            uid=trip["uid"],
            raw=trip,
            stations=_stations(),
            cities=_cities(),
            tz=None,  # tz nicht verwendet, Original-Offset zählt
            from_id=CITY_HEILBRONN,
            to_id="x",
            day_iso="2026-10-25",
            adults=1,
        )
        assert out["departure"] == "2026-10-25T03:00:00+02:00"
        assert out["arrival"] == "2026-10-25T03:30:00+01:00"
        # Echte Differenz (UTC): 90 Min – api-Dauer wird überschrieben.
        assert out["duration_minutes"] == 90
        assert out["duration_text"] == "1h30m"
        # Offsets für Inspektion
        assert out["departure_offset"] == 7200
        assert out["arrival_offset"] == 3600

    def test_uses_stations_and_cities(self) -> None:
        trip = make_trip(uid="x", departure_iso="2026-10-25T07:06:00+02:00",
                         arrival_iso="2026-10-25T13:57:00+02:00", price=20.0)
        out = formatting.normalise_trip(
            uid=trip["uid"], raw=trip, stations=_stations(), cities=_cities(),
            tz=None, from_id=CITY_HEILBRONN, to_id="y",
            day_iso="2026-10-25", adults=2,
        )
        assert out["departure_station"] == "Heilbronn Hbf"
        assert out["arrival_station"] == "Berlin ZOB"
        assert out["departure_city"] == "Heilbronn"
        assert out["arrival_city"] == "Berlin"
        assert out["booking_url"].startswith("https://www.flixbus.de/suche?")


class TestBuildStops:
    def test_direct(self) -> None:
        trip = make_trip(
            uid="d",
            departure_iso="2026-10-25T07:06:00+02:00",
            arrival_iso="2026-10-25T13:57:00+02:00",
        )
        stops = formatting.build_stops(trip, _stations(), _cities(), None)
        assert [s["type"] for s in stops] == ["departure", "arrival"]
        assert stops[0]["city"] == "Heilbronn"
        assert stops[-1]["city"] == "Berlin"

    def test_with_transfer_keeps_per_timestamp_offset(self) -> None:
        """Verbindung Bus->Zug mit Umstieg: jeder Halt mit Original-Offset."""
        legs = [
            {
                "ride_id": "ride-A",
                "departure": {"date": "2026-10-25T07:06:00+02:00",
                              "city_id": CITY_HEILBRONN,
                              "station_id": STATION_HB_HBF},
                "arrival": {"date": "2026-10-25T08:09:00+02:00",
                            "city_id": "x",
                            "station_id": STATION_HEIDELBERG},
                "means_of_transport": "bus",
            },
            {
                "ride_id": "ride-B",
                "departure": {"date": "2026-10-25T08:09:00+02:00",
                              "city_id": "x",
                              "station_id": STATION_HEIDELBERG},
                "arrival": {"date": "2026-10-25T13:57:00+01:00",
                            "city_id": "y",
                            "station_id": STATION_BERLIN_ZOB},
                "means_of_transport": "train",
            },
        ]
        trip = make_trip(
            uid="u", departure_iso=legs[0]["departure"]["date"],
            arrival_iso=legs[-1]["arrival"]["date"], price=25.0,
            legs=legs, direct=False,
            intermediate_count=1,
        )
        stops = formatting.build_stops(trip, _stations(), _cities(), None)
        assert [s["type"] for s in stops] == ["departure", "transfer", "arrival"]
        # Per-timestamp Offset erhalten
        assert stops[0]["time"] == "2026-10-25T07:06:00+02:00"
        assert stops[1]["time"] == "2026-10-25T08:09:00+02:00"
        assert stops[2]["time"] == "2026-10-25T13:57:00+01:00"


class TestStripInternal:
    def test_drops_underscore_keys(self) -> None:
        trip = {"price": 10, "_departure_minutes": 60, "_sort_departure": 1.0}
        out = formatting.strip_internal(trip)
        assert "price" in out
        assert "_departure_minutes" not in out
        assert "_sort_departure" not in out
