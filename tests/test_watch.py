"""Tests für ``flixbus_cli.watch`` (Persistenz, ID, Idempotenz)."""

from __future__ import annotations

from pathlib import Path

import pytest

from flixbus_cli import watch

from _helpers import isolated_fs


HB = {"id": "city-hb", "name": "Heilbronn"}
BLN = {"id": "city-bln", "name": "Berlin"}


class TestWatchPersistence:
    def test_add_then_list(self, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            watch.add(HB, BLN, "2026-10-25", 25.0, 1)
            items = watch.all_entries()
            assert len(items) == 1
            e = items[0]
            assert e["from"]["id"] == "city-hb"
            assert e["to"]["id"] == "city-bln"
            assert e["below"] == 25.0
            assert e["date"] == "2026-10-25"

    def test_add_is_idempotent(self, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            watch.add(HB, BLN, "2026-10-25", 25.0, 1)
            watch.add(HB, BLN, "2026-10-25", 25.0, 1)
            watch.add(HB, BLN, "2026-10-25", 25.0, 1)
            assert len(watch.all_entries()) == 1

    def test_make_id_stable(self) -> None:
        a = watch.make_id("a", "b", "2026-10-25", 25.0, 1)
        b = watch.make_id("a", "b", "2026-10-25", 25.0, 1)
        assert a == b
        assert len(a) == 8

    def test_remove_idempotent(self, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            watch.add(HB, BLN, "2026-10-25", 25.0, 1)
            entry = watch.all_entries()[0]
            wid = entry["id"]
            # erste Entfernung: entfernt
            existed, _ = watch.remove(wid)
            assert existed is True
            # zweite: no-op
            existed2, _ = watch.remove(wid)
            assert existed2 is False
            # unbekannte ID: no-op
            existed3, _ = watch.remove("xxxxxx")
            assert existed3 is False

    def test_broken_file_raises_parse_error(self, tmp_path: Path) -> None:
        from flixbus_cli.api import ParseError
        with isolated_fs(tmp_path):
            # watch.json mit kaputtem JSON anlegen
            target = watch.watch_path()
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            Path(target).write_text("{ this is not json", encoding="utf-8")
            # load() wirft ParseError (Exit 4) statt eine leere Liste.
            with pytest.raises(ParseError):
                watch.load()

    def test_file_format_is_json_with_correct_keys(self, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            watch.add(HB, BLN, "2026-10-25", 25.0, 2)
            import json

            with open(watch.watch_path(), encoding="utf-8") as fh:
                data = json.load(fh)
            assert isinstance(data, dict)
            (key, value), = data.items()
            assert key == watch.make_id("city-hb", "city-bln", "2026-10-25", 25.0, 2)
            for field in ("id", "from", "to", "date", "below", "adults", "created_at"):
                assert field in value

    def test_watch_path_under_xdg(self, tmp_path: Path) -> None:
        with isolated_fs(tmp_path):
            target = watch.watch_path()
            assert target.endswith("watch.json")
            assert target.startswith(str(tmp_path))
