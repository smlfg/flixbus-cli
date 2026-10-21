"""Lokaler Preis-Watch.

Ablage: $XDG_CONFIG_HOME/flixbus-cli/watch.json (Fallback ~/.config).
Enthält ausschließlich öffentliche Suchparameter – keine Zugangsdaten.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from .api import ParseError

CONFIG_DIR_NAME = "flixbus-cli"
WATCH_FILE = "watch.json"


def config_dir() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, CONFIG_DIR_NAME)


def watch_path() -> str:
    return os.path.join(config_dir(), WATCH_FILE)


def _empty() -> dict[str, dict[str, Any]]:
    return {}


def load() -> dict[str, dict[str, Any]]:
    path = watch_path()
    if not os.path.exists(path):
        return _empty()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ParseError(
            f"watch.json ist kaputt: {exc}. Bitte reparieren oder löschen."
        ) from exc
    except OSError as exc:
        raise ParseError(f"watch.json nicht lesbar: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError("watch.json muss ein JSON-Objekt sein.")
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def save(items: dict[str, dict[str, Any]]) -> None:
    directory = config_dir()
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, WATCH_FILE)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".watch-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def make_id(from_id: str, to_id: str, day_iso: str, below: float, adults: int) -> str:
    """Stabile ID über die Suchparameter -> `add` ist idempotent."""
    raw = "|".join([from_id, to_id, day_iso, f"{below:.2f}", str(adults)])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def add(from_city: dict[str, Any], to_city: dict[str, Any], day_iso: str, below: float, adults: int) -> dict[str, Any]:
    items = load()
    wid = make_id(from_city["id"], to_city["id"], day_iso, below, adults)
    entry = {
        "id": wid,
        "from": {"id": from_city["id"], "name": from_city.get("name") or ""},
        "to": {"id": to_city["id"], "name": to_city.get("name") or ""},
        "date": day_iso,
        "below": below,
        "adults": adults,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    items[wid] = entry
    save(items)
    return entry


def remove(wid: str) -> tuple[bool, bool]:
    """Gibt (entfernt, existierte) zurück. Idempotent."""
    items = load()
    existed = wid in items
    if existed:
        del items[wid]
        save(items)
    return existed, True


def all_entries() -> list[dict[str, Any]]:
    items = load()
    return sorted(items.values(), key=lambda e: (str(e.get("date") or ""), str(e.get("id") or "")))