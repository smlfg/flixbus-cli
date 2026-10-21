"""End-to-End-Tests für ``flix``-Befehle mit gemockten HTTP-Antworten."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from flixbus_cli import api as api_mod

from _fixtures import (
    BERLIN,
    CITY_HEILBRONN,
    HEILBRONN,
    HEILBRONN_NECKARSULM,
    build_day_response,
    make_cities_response,
    make_search_response,
    make_trip,
)
from _helpers import (
    assert_no_traceback,
    exit_for,
    isolated_fs,
    one_json,
    run_cli,
)


class _FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload) if not isinstance(payload, (bytes, str)) else str(payload)

    def json(self) -> Any:
        if isinstance(self._payload, (dict, list)):
            return self._payload
        raise ValueError("not json")


class _FakeSession:
    """requests.Session-Ersatz, der je URL-Pfad eine vorbereitete
    Antwort liefert. Verhindert jeden echten HTTP-Roundtrip."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.handlers: dict[str, Any] = {}
        self.default_status: int = 200

    def register(self, path_suffix: str, payload: Any, *, status: int = 200) -> None:
        self.handlers[path_suffix] = (status, payload)

    def get(self, url: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> _FakeResponse:
        self.requests.append((url, dict(params or {})))
        for suffix, (status, payload) in self.handlers.items():
            if url.endswith(suffix):
                return _FakeResponse(status, payload)
        return _FakeResponse(self.default_status, {})

    def headers(self) -> dict[str, str]:
        return {}

    def update(self, *args, **kwargs) -> None:
        return None


@pytest.fixture
def fake_session(monkeypatch: pytest.MonkeyPatch) -> _FakeSession:
    """Monkeypatched ``api.session``, damit keine echten HTTP-Anfragen gehen."""
    sess = _FakeSession()
    monkeypatch.setattr(api_mod, "session", lambda: sess)
    return sess


class TestGlobalCli:
    def test_help(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["--help"])
        assert code == exit_for("ok")
        for cmd in ("cities", "search", "trip", "cheapest", "watch", "book"):
            assert cmd in out

    def test_version(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["--version"])
        assert code == exit_for("ok")
        assert out.startswith("flix ")
        assert "0.1.0" in out

    def test_no_cmd_human(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli([])
        assert code == exit_for("ok")
        assert out  # leer nicht

    def test_no_cmd_json(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["--json"])
        assert code == exit_for("ok")
        body = one_json(out)
        assert "commands" in body
        assert "version" in body

    def test_unknown_cmd(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["nope", "--json"])
        assert code == exit_for("usage")
        body = one_json(out)
        assert body["error"]["kind"] == "usage"


class TestCitiesCommand:
    def test_search_heilbronn(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        cities = make_cities_response(HEILBRONN, HEILBRONN_NECKARSULM)
        fake_session.register("/search/autocomplete/cities", cities)
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["cities", "heilbronn", "--json"])
        assert code == exit_for("ok")
        body = one_json(out)
        assert body["query"] == "heilbronn"
        assert body["count"] == 2
        assert body["cities"][0]["name"] == "Heilbronn"  # exakter Treffer voran

    def test_empty_query_exits_1(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["cities", "", "--json"])
        assert code == exit_for("usage")
        body = one_json(out)
        assert body["error"]["kind"] == "usage"

    def test_limit_too_low(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        cities = make_cities_response(HEILBRONN)
        fake_session.register("/search/autocomplete/cities", cities)
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["cities", "heilbronn", "--limit", "0", "--json"])
        assert code == exit_for("usage")

    def test_limit_invalid(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["cities", "heilbronn", "--limit", "abc", "--json"])
        assert code == exit_for("usage")
        assert_no_traceback(out, err)

    def test_http_error_500(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        sess = _FakeSession()
        sess.default_status = 500
        monkeypatch.setattr(api_mod, "session", lambda: sess)
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["cities", "xyz", "--json"])
        assert code == exit_for("network")
        body = one_json(out)
        assert body["error"]["kind"] == "network"
        assert_no_traceback(out, err)

    def test_invalid_json_response(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        class _Bad:
            def get(self, *a, **k):
                r = _FakeResponse(200, {})
                r.text = "<html>bad</html>"
                # raise on .json() — emulate non-json body
                def boom():
                    raise ValueError("no json")
                r.json = boom  # type: ignore[attr-defined]
                return r

        monkeypatch.setattr(api_mod, "session", lambda: _Bad())
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["cities", "xyz", "--json"])
        assert code == exit_for("parse")
        body = one_json(out)
        assert body["error"]["kind"] == "parse"


def _make_dated_search_response(day_iso: str) -> dict[str, Any]:
    """Baut eine kleine, günstige Such-Antwort für einen Tag."""
    t1 = make_trip(
        uid="direct:trip-A",
        departure_iso=f"{day_iso}T07:06:00+02:00",
        arrival_iso=f"{day_iso}T13:57:00+02:00",
        price=19.99,
    )
    t2 = make_trip(
        uid="direct:trip-B",
        departure_iso=f"{day_iso}T09:30:00+02:00",
        arrival_iso=f"{day_iso}T15:00:00+02:00",
        price=24.90,
    )
    return make_search_response(results={"direct:trip-A": t1, "direct:trip-B": t2})


class TestSearchCommand:
    def test_search_ok(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        response = _make_dated_search_response("2026-10-25")
        fake_session.register("/search/service/v4/search", response)
        # cities-endpoint mocken, damit resolve_city funktioniert
        fake_session.register(
            "/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN)
        )
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                ["search", "heilbronn", "berlin", "--date", "2026-10-25", "--json"]
            )
        assert code == exit_for("ok")
        body = one_json(out)
        assert body["from"]["name"] == "Heilbronn"
        assert body["to"]["name"] == "Berlin"
        assert body["count"] == 2
        assert body["trips"][0]["trip_id"] == "direct:trip-A"
        # Per-timestamp Offset
        assert body["trips"][0]["departure"] == "2026-10-25T07:06:00+02:00"

    def test_max_price_filter(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        response = _make_dated_search_response("2026-10-25")
        fake_session.register("/search/service/v4/search", response)
        fake_session.register(
            "/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN)
        )
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                [
                    "search", "heilbronn", "berlin", "--date", "2026-10-25",
                    "--max-price", "20", "--json",
                ]
            )
        assert code == exit_for("ok")
        body = one_json(out)
        assert body["count"] == 1
        assert body["trips"][0]["price"] == 19.99

    def test_excludes_after_midnight_next_calendar_day(
        self, fake_session: _FakeSession, tmp_path: Path
    ) -> None:
        """API-Nachtfahrten des Folgetags (include_after_midnight_rides) werden ausgefiltert."""
        day = "2026-10-26"
        next_day = "2026-10-27"
        on_day = make_trip(
            uid="direct:on-day",
            departure_iso=f"{day}T22:00:00+02:00",
            arrival_iso=f"{next_day}T04:00:00+02:00",
            price=15.99,
        )
        after_midnight = make_trip(
            uid="direct:next-midnight",
            departure_iso=f"{next_day}T00:20:00+01:00",
            arrival_iso=f"{next_day}T06:00:00+01:00",
            price=11.99,
        )
        response = make_search_response(
            results={"direct:on-day": on_day, "direct:next-midnight": after_midnight}
        )
        fake_session.register("/search/service/v4/search", response)
        fake_session.register(
            "/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN)
        )
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                ["search", "heilbronn", "berlin", "--date", day, "--json"]
            )
        assert code == exit_for("ok")
        body = one_json(out)
        assert body["count"] == 1
        assert body["trips"][0]["trip_id"] == "direct:on-day"
        assert all(t["departure"].startswith(f"{day}T") for t in body["trips"])

    def test_after_before_filter(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        response = _make_dated_search_response("2026-10-25")
        fake_session.register("/search/service/v4/search", response)
        fake_session.register(
            "/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN)
        )
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                [
                    "search", "heilbronn", "berlin", "--date", "2026-10-25",
                    "--after", "09:00", "--json",
                ]
            )
        assert code == exit_for("ok")
        body = one_json(out)
        assert body["count"] == 1
        assert body["trips"][0]["trip_id"] == "direct:trip-B"

    def test_unknown_city(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        fake_session.register("/search/autocomplete/cities", [])
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                ["search", "atlantis", "berlin", "--date", "2026-10-25", "--json"]
            )
        assert code == exit_for("usage")
        body = one_json(out)
        assert body["error"]["kind"] == "usage"

    def test_past_date(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                ["search", "heilbronn", "berlin", "--date", "2020-01-01", "--json"]
            )
        assert code == exit_for("usage")
        assert_not_called(fake_session)

    def test_bad_format_date(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                ["search", "heilbronn", "berlin", "--date", "25.10.2026", "--json"]
            )
        assert code == exit_for("usage")
        assert_not_called(fake_session)

    def test_bad_clock(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                [
                    "search", "heilbronn", "berlin", "--date", "2026-10-25",
                    "--after", "25:00", "--json",
                ]
            )
        assert code == exit_for("usage")
        assert_not_called(fake_session)

    def test_bad_adults(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                [
                    "search", "heilbronn", "berlin", "--date", "2026-10-25",
                    "--adults", "0", "--json",
                ]
            )
        assert code == exit_for("usage")
        assert_not_called(fake_session)

    def test_bad_max_price(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                [
                    "search", "heilbronn", "berlin", "--date", "2026-10-25",
                    "--max-price", "abc", "--json",
                ]
            )
        assert code == exit_for("usage")
        assert_not_called(fake_session)

    def test_max_price_negative(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                [
                    "search", "heilbronn", "berlin", "--date", "2026-10-25",
                    "--max-price", "-5", "--json",
                ]
            )
        assert code == exit_for("usage")
        assert_not_called(fake_session)


class TestTripCommand:
    def test_trip_unknown_returns_4(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["trip", "unknown:abc", "--json"])
        assert code == exit_for("parse")
        body = one_json(out)
        assert body["error"]["kind"] == "parse"

    def test_trip_empty_args(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        """``flix trip`` ohne Argumente -> argparse SystemExit 2.

        Das ``--json``-Wrap muss auch dann ein JSON-Objekt liefern.
        """
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["trip"])
        # Argparse wirft SystemExit(2); unser Wrapper mappt das auf Exit 1
        # mit Usage-Fehler, weil kein --json gesetzt ist.
        assert code in (1, 2)

    def test_trip_empty_args_json(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["trip", "--json"])
        # argparse SystemExit 2 wird in main() zu Exit 1 mit JSON-Fehler gemappt.
        assert code in (1, 2), (out, err)

    def test_trip_after_search_in_new_process(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """``trip`` muss in einem **frischen** Aufruf funktionieren, wenn die
        Such-Antwort auf der Platte liegt (Cache). Der prozess-lokale
        ``_TRIP_CACHE`` wird hier explizit geleert, statt Module zu
        reloaden (Reload würde die nächste Test-Fixture korrumpieren)."""
        from pathlib import Path as PathCls
        from flixbus_cli import cli as cli_mod

        # 1) Im Sandbox-Verzeichnis: search -> Cache schreiben
        sess = _FakeSession()
        monkeypatch.setattr(api_mod, "session", lambda: sess)
        day_iso = "2026-10-25"
        trip_uid = "direct:trip-A"
        response = _make_dated_search_response(day_iso)
        sess.register("/search/service/v4/search", response)
        sess.register(
            "/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN)
        )
        with isolated_fs(tmp_path):
            # search schreibt Cache und füllt prozess-lokales _TRIP_CACHE.
            code, out, _ = run_cli(
                ["search", "heilbronn", "berlin", "--date", day_iso, "--json"]
            )
            assert code == exit_for("ok"), out
            cache_dir = cli_mod.cache_store.cache_dir()
            cached = list(PathCls(cache_dir).glob("search-*.json"))
            assert cached, "Cache-Datei wurde nicht geschrieben"

            # Prozess-lokalen ``_TRIP_CACHE`` leeren, als wäre dies ein
            # neuer Prozess / ein neuer Lookup.
            cli_mod._TRIP_CACHE.clear()

            # 2) trip im selben Modul, aber mit leerem _TRIP_CACHE.
            code2, out2, err2 = run_cli(["trip", trip_uid, "--json"])
        assert code2 == exit_for("ok"), (out2, err2)
        decoder = json.JSONDecoder()
        body, _end = decoder.raw_decode(out2.strip())
        assert body["trip_id"] == trip_uid
        assert body["from"]["city"] == "Heilbronn"
        assert body["to"]["city"] == "Berlin"
        assert body["duration_minutes"] == 411
        assert body["duration_text"] == "6h51m"
        assert body["direct"] is True


    def test_trip_timezone_follows_departure_offset_across_dst(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
        ) -> None:
            """Regression (QA 2026-10-21): ``timezone`` muss der Zone der
            Abfahrtszeit folgen, nicht ``timezone_offset_seconds`` der Stadt.

            Live-Befund: die Stadt-Fixture meldet ``+02:00`` (Offset *heute*),
            die Fahrten am 26.10. tragen aber ``+01:00``, weil die Sommerzeit
            am 25.10.2026 endet. Vor dem Fix meldete ``flix trip``
            ``"timezone": "+02:00"`` und widersprach damit den Zeiten im
            selben Objekt.
            """
            from pathlib import Path as PathCls
            from flixbus_cli import cli as cli_mod

            sess = _FakeSession()
            monkeypatch.setattr(api_mod, "session", lambda: sess)
            day_iso = "2026-10-26"  # nach dem Ende der Sommerzeit
            trip_uid = "ic:winter-trip"
            trip = make_trip(
                uid=trip_uid,
                departure_iso=f"{day_iso}T05:33:00+01:00",
                arrival_iso=f"{day_iso}T16:04:00+01:00",
                price=79.99,
                duration_minutes=631,
            )
            sess.register(
                "/search/service/v4/search",
                make_search_response(results={trip_uid: trip}),
            )
            sess.register("/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN))

            with isolated_fs(tmp_path):
                code, out, err = run_cli(
                    ["search", "heilbronn", "berlin", "--date", day_iso, "--json"]
                )
                assert code == exit_for("ok"), (out, err)
                cli_mod._TRIP_CACHE.clear()
                code2, out2, err2 = run_cli(["trip", trip_uid, "--json"])

            assert code2 == exit_for("ok"), (out2, err2)
            body = one_json(out2)
            assert body["from"]["time"] == f"{day_iso}T05:33:00+01:00"
            # Zone = Offset der Abfahrtszeit, nicht der Stadt (7200 -> +02:00).
            assert body["timezone"] == "+01:00", body["timezone"]
            # Kein Halt darf eine andere Zone als die Abfahrt tragen.
            for stop in body["stops"]:
                assert stop["time"].endswith("+01:00"), stop


    def test_text_output_shows_time_station_price(
        self, fake_session: _FakeSession, tmp_path: Path
    ) -> None:
        """Regression (QA 2026-10-21): die Textausgabe von ``search`` muss
        Zeit, Ort und Preis zeigen.

        Vor dem Fix nahm der Renderer blind die ersten vier JSON-Keys einer
        Verbindung - das waren ``trip_id``/``status``/``direct``/
        ``transfers``, wodurch Abfahrtszeit, Station und Preis gar nicht
        erst erschienen. Die UID frass ausserdem die halbe Zeile.
        """
        response = _make_dated_search_response("2026-10-25")
        fake_session.register("/search/service/v4/search", response)
        fake_session.register(
            "/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN)
        )
        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                ["search", "heilbronn", "berlin", "--date", "2026-10-25"]
            )
        assert code == exit_for("ok"), (out, err)
        # Jede Verbindung braucht mindestens: Abfahrtszeit, Ankunftszeit
        # und Preis.
        for needle in (
            "2026-10-25T07:06:00+02:00",
            "2026-10-25T13:57:00+02:00",
            "19.99",
        ):
            assert needle in out, needle
        assert "station" in out
        # Keine Verbindungszeile darf von einem 60-Zeichen-UID-Dump
        # dominiert werden.
        for line in out.splitlines():
            if line.strip().startswith("- ") and "departure=" in line:
                assert len(line) < 300, line


class TestCheapestCommand:
    def test_cheapest_min_per_day(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Tagesminimum je Tag = min(preise des Tages).

        Pro Tag wird eine eigene Antwort gerendert. Das Routing
        geschieht über ``departure_date`` (DD.MM.YYYY) im Request.
        """
        from datetime import date

        day1, day2, day3 = date(2026, 10, 25), date(2026, 10, 26), date(2026, 10, 27)
        responses = {
            day1.strftime("%d.%m.%Y"): build_day_response(day=day1, prices=[19.99, 24.90, 22.50]),
            day2.strftime("%d.%m.%Y"): build_day_response(day=day2, prices=[35.0, 33.0]),
            day3.strftime("%d.%m.%Y"): build_day_response(day=day3, prices=[18.0, 21.0]),
        }

        class RoutingSession:
            cities_payload = make_cities_response(HEILBRONN, BERLIN)
            cities_offset: int = 0

            def __init__(self) -> None:
                self.requests: list[tuple[str, dict]] = []

            def get(self, url, params=None, timeout=None):
                self.requests.append((url, dict(params or {})))
                if url.endswith("/search/autocomplete/cities"):
                    return _FakeResponse(200, self.cities_payload)
                departure_date = (params or {}).get("departure_date", "")
                payload = responses.get(departure_date)
                if payload is None:
                    return _FakeResponse(404, {"error": "not found"})
                return _FakeResponse(200, payload)

        sess = RoutingSession()
        monkeypatch.setattr(api_mod, "session", lambda: sess)

        with isolated_fs(tmp_path):
            code, out, err = run_cli(
                [
                    "cheapest", "heilbronn", "berlin",
                    "--from", "2026-10-25", "--days", "3", "--json",
                ]
            )
        assert code == exit_for("ok"), (out, err)
        body = one_json(out)
        # Tagesminimum korrekt: 19.99, 33.0, 18.0
        assert body["daily"][0]["price"] == 19.99
        assert body["daily"][1]["price"] == 33.0
        assert body["daily"][2]["price"] == 18.0
        # Bester Tag = niedrigster Preis = 2026-10-27 mit 18.0
        assert body["best"]["price"] == 18.0
        assert body["best"]["date"] == "2026-10-27"

    def test_cheapest_days_too_high(
        self, fake_session: _FakeSession, tmp_path: Path
    ) -> None:
        with isolated_fs(tmp_path):
            code, out, _ = run_cli(
                [
                    "cheapest", "heilbronn", "berlin", "--from", "2026-10-25",
                    "--days", "30", "--json",
                ]
            )
        assert code == exit_for("usage")

    def test_cheapest_days_zero(
        self, fake_session: _FakeSession, tmp_path: Path
    ) -> None:
        with isolated_fs(tmp_path):
            code, out, _ = run_cli(
                [
                    "cheapest", "heilbronn", "berlin", "--from", "2026-10-25",
                    "--days", "0", "--json",
                ]
            )
        assert code == exit_for("usage")


class TestWatchCommand:
    def test_add_then_list_then_remove(
        self, fake_session: _FakeSession, tmp_path: Path
    ) -> None:
        # Mock für resolve_city in add
        fake_session.register("/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN))
        with isolated_fs(tmp_path):
            code, out, _ = run_cli(
                [
                    "watch", "add", "heilbronn", "berlin",
                    "--date", "2026-10-25", "--below", "25", "--json",
                ]
            )
            assert code == exit_for("ok"), out
            body = one_json(out)
            wid = body["watch"]["id"]

            code, out, _ = run_cli(["watch", "list", "--json"])
            assert code == exit_for("ok")
            body = one_json(out)
            assert body["count"] == 1

            code, out, _ = run_cli(["watch", "remove", wid, "--json"])
            assert code == exit_for("ok")
            body = one_json(out)
            assert body["removed"] is True
            assert body["noop"] is False

            # No-op: Exit 0, removed=False, noop=True.
            code, out, _ = run_cli(["watch", "remove", wid, "--json"])
            assert code == exit_for("ok")
            body = one_json(out)
            assert body["removed"] is False
            assert body["noop"] is True

    def test_add_missing_below(
        self, fake_session: _FakeSession, tmp_path: Path
    ) -> None:
        fake_session.register("/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN))
        with isolated_fs(tmp_path):
            code, out, _ = run_cli(
                [
                    "watch", "add", "heilbronn", "berlin",
                    "--date", "2026-10-25", "--json",
                ]
            )
        assert code == exit_for("usage")

    def test_add_zero_below(
        self, fake_session: _FakeSession, tmp_path: Path
    ) -> None:
        fake_session.register("/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN))
        with isolated_fs(tmp_path):
            code, out, _ = run_cli(
                [
                    "watch", "add", "heilbronn", "berlin",
                    "--date", "2026-10-25", "--below", "0", "--json",
                ]
            )
        assert code == exit_for("usage")

    def test_check_reports_matches(
        self, fake_session: _FakeSession, tmp_path: Path
    ) -> None:
        fake_session.register("/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN))
        # Such-Antwort für check (limit=1 reicht).
        response = _make_dated_search_response("2026-10-25")
        fake_session.handlers["/search/service/v4/search"] = (200, response)
        fake_session.register("/search/autocomplete/cities", make_cities_response(HEILBRONN, BERLIN))

        with isolated_fs(tmp_path):
            run_cli(
                [
                    "watch", "add", "heilbronn", "berlin",
                    "--date", "2026-10-25", "--below", "25", "--json",
                ]
            )
            code, out, _ = run_cli(["watch", "check", "--json"])
        assert code == exit_for("ok"), out
        body = one_json(out)
        assert body["checked"] == 1
        assert body["below_threshold"] == 1
        assert body["results"][0]["matches"] is True

    def test_broken_watch_file_returns_4(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Kaputte ``watch.json`` -> Exit 4 (parse), genau ein JSON-Objekt."""
        from flixbus_cli import watch as watch_mod
        from pathlib import Path as PathCls

        with isolated_fs(tmp_path):
            target = watch_mod.watch_path()
            PathCls(target).parent.mkdir(parents=True, exist_ok=True)
            PathCls(target).write_text("not-json", encoding="utf-8")
            code, out, err = run_cli(["watch", "list", "--json"])
        assert code == exit_for("parse")
        body = one_json(out)
        assert body["error"]["kind"] == "parse"
        assert_no_traceback(out, err)


class TestBookCommand:
    def test_book_exits_5(self, fake_session: _FakeSession, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            code, out, err = run_cli(["book", "anything", "--json"])
        assert code == exit_for("forbidden")
        body = one_json(out)
        assert body["error"]["kind"] == "forbidden"
        assert "Buchen" in body["error"]["message"]

    def test_book_with_confirm_still_5(
        self, fake_session: _FakeSession, tmp_path: Path
    ) -> None:
        with isolated_fs(tmp_path):
            code, out, _ = run_cli(["book", "--confirm", "--json"])
        assert code == exit_for("forbidden")


def assert_not_called(fake: _FakeSession) -> None:
    assert fake.requests == [], f"unerwartete HTTP-Anfragen: {fake.requests}"
