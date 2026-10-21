"""Hilfsfunktionen für die Test-Suite: Sandbox-Env, CLI-Aufruf."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

# ``conftest.py`` am Repo-Root stellt ``src/`` an den Anfang von
# ``sys.path``. Hier muss nichts mehr ergänzt werden.


@contextlib.contextmanager
def isolated_fs(
    tmp_path: Path,
    *,
    xdg_config_home: str | None = None,
    xdg_cache_home: str | None = None,
):
    """Setzt HOME/XDG auf tmp_path, damit Config und Cache dort landen."""
    env_before = {}
    keys = (
        "HOME",
        "USERPROFILE",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "FLIX_BASE_URL",
        "FLIX_TRIP_FROM_ID",
        "FLIX_TRIP_TO_ID",
        "FLIX_TRIP_DATE",
        "FLIX_TRIP_ADULTS",
        "ACCEPTANCE_SANDBOX",
    )
    for key in keys:
        env_before[key] = os.environ.get(key)
    os.environ["HOME"] = str(tmp_path)
    os.environ["USERPROFILE"] = str(tmp_path)
    if xdg_config_home is not None:
        os.environ["XDG_CONFIG_HOME"] = xdg_config_home
    elif "XDG_CONFIG_HOME" in env_before:
        os.environ["XDG_CONFIG_HOME"] = str(tmp_path / ".config")
    if xdg_cache_home is not None:
        os.environ["XDG_CACHE_HOME"] = xdg_cache_home
    elif "XDG_CACHE_HOME" in env_before:
        os.environ["XDG_CACHE_HOME"] = str(tmp_path / ".cache")
    else:
        # Falls XDG_CACHE_HOME vorher nicht gesetzt war, setzen wir es
        # explizit auf den Test-Pfad, damit kein echter Cache genutzt wird.
        os.environ["XDG_CACHE_HOME"] = str(tmp_path / ".cache")
    os.environ["ACCEPTANCE_SANDBOX"] = "1"
    try:
        yield tmp_path
    finally:
        for key, value in env_before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_cli(
    args: Iterable[str],
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[int, str, str]:
    """Ruft ``cli.main`` auf und fängt stdout/stderr ab."""
    from flixbus_cli import cli

    saved: dict[str, str | None] = {}
    if env:
        for key, value in env.items():
            saved[key] = os.environ.get(key)
            os.environ[key] = str(value)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(list(args))
        except SystemExit as exc:  # --help/--version
            code = int(exc.code if exc.code is not None else 0)
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    return code, out.getvalue(), err.getvalue()


def one_json(stdout: str) -> dict[str, Any]:
    """Parst genau ein JSON-Objekt aus stdout (kein multi-doc)."""
    text = stdout.strip()
    if not text:
        return {}
    # Mehrere Zeilen können zu einem JSON gehören (pretty-printed).
    decoder = json.JSONDecoder()
    obj, _end = decoder.raw_decode(text)
    return obj


def assert_no_traceback(stdout: str, stderr: str) -> None:
    """Stellt sicher, dass weder stdout noch stderr ein Traceback enthält."""
    for stream_name, txt in (("stdout", stdout), ("stderr", stderr)):
        assert "Traceback " not in txt, f"Traceback in {stream_name}: {txt[:500]}"
        assert 'File "' not in txt, f"File-Frame in {stream_name}: {txt[:500]}"


def exit_for(name: str) -> int:
    from flixbus_cli.cli import (
        EXIT_AUTH,
        EXIT_FORBIDDEN,
        EXIT_NETWORK,
        EXIT_OK,
        EXIT_PARSE,
        EXIT_USAGE,
    )

    return {
        "ok": EXIT_OK,
        "usage": EXIT_USAGE,
        "auth": EXIT_AUTH,
        "network": EXIT_NETWORK,
        "parse": EXIT_PARSE,
        "forbidden": EXIT_FORBIDDEN,
    }[name]
