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

from . import __version__

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


# ---------- Zentrale Ausgabe ----------


def emit(payload: dict, as_json: bool, text: str | None = None) -> int:
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


def _to_text(payload: dict) -> str:
    """Lesbare Darstellung für den Non-JSON-Modus."""
    lines: list[str] = []

    def render(value, indent: int = 0) -> None:
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
                        f"{k}={item[k]}"
                        for k in list(item)[:4]
                        if not isinstance(item[k], (dict, list))
                    )
                    lines.append(f"{pad}- {head}")
                else:
                    lines.append(f"{pad}- {item}")
        else:
            lines.append(f"{pad}{value}")

    render(payload)
    return "\n".join(lines) if lines else ""


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
    sub.add_parser("cities", help="Städte nach Name suchen")
    sub.add_parser("search", help="Verbindungen suchen")
    sub.add_parser("trip", help="Halte einer Verbindung anzeigen")
    sub.add_parser("cheapest", help="Günstigsten Tag im Zeitraum finden")
    sub.add_parser("watch", help="Lokaler Preis-Watch")
    sub.add_parser("book", help="NICHT unterstützt (immer Exit 5)")
    return parser


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
            return emit({"commands": ["cities", "search", "trip", "cheapest", "watch", "book"], "version": __version__}, as_json)
        parser.print_help()
        return EXIT_OK

    return fail(EXIT_USAGE, f"Unbekannter Befehl: {args.cmd}", as_json=as_json)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())