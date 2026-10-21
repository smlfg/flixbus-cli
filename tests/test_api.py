"""Tests für ``flixbus_cli.api``: Eingabevalidierung und Parser."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from flixbus_cli import api


class TestParseIsoDate:
    def test_today_and_morgen(self) -> None:
        today = date(2026, 10, 20)
        assert api.parse_iso_date("heute", today=today) == today
        assert api.parse_iso_date("morgen", today=today) == today + timedelta(days=1)

    def test_iso_format_ok(self) -> None:
        today = date(2026, 10, 20)
        assert api.parse_iso_date("2026-10-25", today=today) == date(2026, 10, 25)

    def test_empty(self) -> None:
        today = date(2026, 10, 20)
        with pytest.raises(ValueError):
            api.parse_iso_date("", today=today)

    def test_invalid_format(self) -> None:
        today = date(2026, 10, 20)
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            api.parse_iso_date("25.10.2026", today=today)

    def test_past_rejected(self) -> None:
        today = date(2026, 10, 20)
        with pytest.raises(ValueError, match="Vergangenheit"):
            api.parse_iso_date("2020-01-01", today=today)

    def test_too_far_future_rejected(self) -> None:
        today = date(2026, 10, 20)
        with pytest.raises(ValueError, match="Tage in der Zukunft"):
            api.parse_iso_date("2099-01-01", today=today)


class TestParseClock:
    def test_ok(self) -> None:
        assert api.parse_clock("09:00") == (9, 0)
        assert api.parse_clock("23:59") == (23, 59)

    @pytest.mark.parametrize("raw", ["25:00", "9:00", "9-00", "abc"])
    def test_invalid(self, raw: str) -> None:
        with pytest.raises(ValueError, match="HH:MM"):
            api.parse_clock(raw)


class TestParseInt:
    def test_min_max(self) -> None:
        assert api.parse_positive_int("5", "--x") == 5
        assert api.parse_positive_int("5", "--x", minimum=1, maximum=9) == 5
        with pytest.raises(ValueError):
            api.parse_positive_int("0", "--x")
        with pytest.raises(ValueError):
            api.parse_positive_int("10", "--x", maximum=9)
        with pytest.raises(ValueError):
            api.parse_positive_int("abc", "--x")

    def test_negative(self) -> None:
        with pytest.raises(ValueError):
            api.parse_positive_int("-5", "--x")


class TestParseAmount:
    def test_ok(self) -> None:
        assert api.parse_amount("19.99", "--max-price") == 19.99
        assert api.parse_amount("19,99", "--max-price") == 19.99

    @pytest.mark.parametrize("raw", ["abc", "-5", "0", "NaN", "Infinity"])
    def test_invalid(self, raw: str) -> None:
        with pytest.raises(ValueError):
            api.parse_amount(raw, "--max-price")


class TestExtractResults:
    def test_dict(self) -> None:
        data = {"trips": [{"results": {"abc": {"uid": "abc", "foo": 1}}}]}
        out = api.extract_results(data)
        assert "abc" in out
        assert out["abc"]["foo"] == 1

    def test_list(self) -> None:
        data = {"trips": [{"results": [{"uid": "abc", "foo": 1}]}]}
        out = api.extract_results(data)
        assert out == {"abc": {"uid": "abc", "foo": 1}}

    def test_missing(self) -> None:
        with pytest.raises(api.ParseError):
            api.extract_results({"trips": [{}]})
        with pytest.raises(api.ParseError):
            api.extract_results({"trips": []})
        with pytest.raises(api.ParseError):
            api.extract_results({"trips": [{"results": "nope"}]})


class TestBestCityMatch:
    def test_exact_beats_prefix(self) -> None:
        cities = [
            {"id": "1", "name": "Heilbronn"},
            {"id": "2", "name": "Heilbronn an der Donau"},
        ]
        best = api.best_city_match("Heilbronn", cities)
        assert best and best["id"] == "1"

    def test_prefix_when_no_exact(self) -> None:
        cities = [{"id": "1", "name": "Heidelberg"}]
        result = api.best_city_match("heid", cities)
        assert result is not None and result["id"] == "1"

    def test_substring_when_no_prefix(self) -> None:
        cities = [{"id": "1", "name": "Mannheim"}, {"id": "2", "name": "Heilbronn"}]
        result = api.best_city_match("bronn", cities)
        assert result is not None and result["id"] == "2"

    def test_none(self) -> None:
        assert api.best_city_match("abc", []) is None
