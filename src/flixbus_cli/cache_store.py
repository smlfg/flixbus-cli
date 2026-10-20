"""Persistenter Cache für Such-Antworten unter ``$XDG_CACHE_HOME``.

Ermöglicht ``flix trip <trip_id>`` in einem **neuen** Prozess: das
Such-Ergebnis wird beim ersten Aufruf von ``search``/``cheapest``
nachgeladen und in ``cache/search/<hash>.json`` abgelegt; ``trip`` schaut
zuerst im prozess-internen Cache, dann hier, ohne neue HTTP-Anfrage.

Inhaltlich werden die Roh-Antwort von ``global.api.flixbus.com``,
die Liste der aufgelösten Städte und die gewählte Abfahrtsstadt
gespeichert. Keine Zugangsdaten, nur Suchparameter (From/To/Date/Adults).
TTL: 30 Tage; danach wird der Eintrag verworfen.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date, timedelta
from typing import Any

CACHE_DIR_NAME = "flixbus-cli"
CACHE_FILE_PREFIX = "search-"
CACHE_TTL_DAYS = 30


def cache_dir() -> str:
    base = (
        os.environ.get("XDG_CACHE_HOME")
        or os.path.join(os.path.expanduser("~"), ".cache")
    )
    sub = os.path.join(base, CACHE_DIR_NAME, "search")
    os.makedirs(sub, exist_ok=True)
    return sub


def cache_path_for(from_id: str, to_id: str, day: date, adults: int) -> str:
    raw = "|".join([from_id, to_id, day.isoformat(), str(adults)])
    name = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return os.path.join(cache_dir(), f"{CACHE_FILE_PREFIX}{name}.json")


def _write_atomic(path: str, payload: dict[str, Any]) -> None:
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".cache-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save(
    from_id: str,
    to_id: str,
    day: date,
    adults: int,
    *,
    raw: dict[str, Any],
    origin: dict[str, Any],
    destination: dict[str, Any],
    tz_offset_seconds: int | None,
) -> str:
    """Legt die Such-Antwort ab. Gibt den Pfad zurück."""
    path = cache_path_for(from_id, to_id, day, adults)
    payload = {
        "version": 1,
        "saved_at": _utcnow_iso(),
        "from_id": from_id,
        "to_id": to_id,
        "date": day.isoformat(),
        "adults": adults,
        "origin": origin,
        "destination": destination,
        "tz_offset_seconds": tz_offset_seconds,
        "raw": raw,
    }
    try:
        _write_atomic(path, payload)
    except OSError:
        # Cache ist optional; Fehler beim Schreiben dürfen das Tool
        # nicht stoppen.
        return ""
    return path


def load(from_id: str, to_id: str, day: date, adults: int) -> dict[str, Any] | None:
    """Lädt einen Cache-Eintrag, falls vorhanden und frisch."""
    path = cache_path_for(from_id, to_id, day, adults)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    saved_at = data.get("saved_at")
    if not isinstance(saved_at, str):
        return None
    if _older_than(saved_at, CACHE_TTL_DAYS):
        try:
            os.unlink(path)
        except OSError:
            pass
        return None
    raw = data.get("raw")
    if not isinstance(raw, dict):
        return None
    return {
        "raw": raw,
        "origin": data.get("origin") or {"id": from_id, "name": ""},
        "destination": data.get("destination") or {"id": to_id, "name": ""},
        "tz_offset_seconds": data.get("tz_offset_seconds"),
        "saved_at": saved_at,
    }


def find_trip(trip_id: str, *, from_id: str, to_id: str, day: date, adults: int) -> dict[str, Any] | None:
    """Sucht ``trip_id`` im passenden Cache-Eintrag. Gibt ``raw`` und Kontext zurück."""
    entry = load(from_id, to_id, day, adults)
    if entry is None:
        return None
    raw = entry["raw"]
    results = raw.get("trips") or []
    for seg in results:
        if not isinstance(seg, dict):
            continue
        inner = seg.get("results")
        if isinstance(inner, dict) and trip_id in inner and isinstance(inner[trip_id], dict):
            return {
                "raw": inner[trip_id],
                "stations": raw.get("stations") or {},
                "cities": raw.get("cities") or {},
                "tz_offset_seconds": entry.get("tz_offset_seconds"),
                "origin": entry.get("origin"),
                "destination": entry.get("destination"),
                "saved_at": entry.get("saved_at"),
            }
    return None


def _utcnow_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _older_than(saved_at: str, days: int) -> bool:
    from datetime import datetime

    try:
        when = datetime.fromisoformat(saved_at)
    except ValueError:
        return True
    cutoff = datetime.now(when.tzinfo) - timedelta(days=days)
    return when < cutoff
