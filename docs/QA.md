# QA Live-Ergebnisse

Lauf: 2026-10-21 (UTC+2). Install: frisches venv `/tmp/flix-qa`, `pip install git+https://github.com/smlfg/flixbus-cli.git` (nach `git pull`, Stand `main`). D5 = 2026-10-26, D3 = 2026-10-24.

| Befehl / Check | Erwartet | Beobachtet | OK/FAIL | Fix-Commit |
|---|---|---|---|---|
| `flix cities heilbronn --json` | Erster Treffer Heilbronn, UUID | `Heilbronn`, `40d91420-8646-11e6-9066-549f350fcb0c` | OK | — |
| `flix search heilbronn berlin --date D5 --limit 5 --json` | Heilbronn-Umgebung → Berlin, D5 lokal, ≤5, Preis>0, Ankunft nach Abfahrt | 5 Treffer, semantisch geprüft | OK | — |
| `flix search stuttgart münchen --date D5 --max-price 20 --direct --sort price --json` | Preis≤20, direkt, aufsteigend Preis | 20 Treffer, Preise 11.99…19.99 sortiert | OK | — |
| `flix search frankfurt köln --date D3 --after 10:00 --before 14:00 --json` | Abfahrten 10:00–14:00 lokal | 6 Treffer, alle im Fenster | OK | — |
| Zeitzone DST 2026-10-25 (nach 03:00 +01:00, vs. API curl) | Lokale Uhrzeit = API-Rohdaten | 0 Offset-/Zeit-Abweichungen (Stuttgart–München) | OK | (Regression: `8dd689d`) |
| `flix trip <id> --json` (neuer Prozess nach `search`) | Erster Halt Abfahrt, Berlin im Ziel, Zeiten monoton | 4 Halte, OK | OK | — |
| `flix cheapest heilbronn münchen --from D3 --days 3 --json` | 3 Tage, Tagesmin = min(`search` selber Tag) | 24./25./26.10., Preise 17.99/19.49/19.49 stimmen | OK | — |
| `flix search …` Text (ohne `--json`) | Lesbar | YAML-ähnliche Struktur inkl. `trips:`-Zeilen | OK | (Regression: `78c8a1f`) |
| `watch add` / `list` / `check --json` / `remove` | Echte Treffer unter Schwelle | `matches: true`, `cheapest: 34.48`, `< 500` | OK | — |
| `watch remove 999` | QA-Checkliste: Exit 1; Vertrag `INTERFACE.md`: Exit 0 noop | Exit 0, `noop: true` (idempotent) | OK* | — |
| Kaputte `watch.json` | Exit 4 | Exit 4, Parse-Meldung | OK | (Regression: `02d290c`) |
| `search xyzunbekannt berlin` | Exit 1, Meldung/Vorschläge | Exit 1, usage JSON | OK | — |
| `search … --date 2020-01-01` | Exit 1 | Exit 1, Vergangenheit | OK | — |
| `search … --date 31.12.` | Exit 1 | Exit 1, ungültiges Datum | OK | — |
| `cheapest … --days 99` | Exit 1 | Exit 1, max 14 Tage | OK | — |
| `trip gibtsnicht --json` | Sauberer Fehler, kein Traceback | Exit 4, ein JSON-Fehlerobjekt | OK | — |
| `book x --confirm --json` | Exit 5, ein JSON-Fehlerobjekt | Exit 5, `kind: forbidden` | OK | — |
| `flix --version` / `--help` / `search --help` | Stimmt mit README (Optionen vorhanden) | `flix 0.1.0`, alle dokumentierten `search`-Flags in `--help` | OK | — |
| `pytest -q` (Repo) | Grün | 93 passed | OK | — |

\*Abweichung nur zwischen QA-Checkliste und `INTERFACE.md`/`docs/ACCEPTANCE.md` (F5: idempotenter No-op Exit 0); Implementierung folgt dem Vertrag.

## Fixes in diesem Lauf

Keine neuen Fixes nötig; bereits gepushte Commits live verifiziert: `02d290c` (watch.json Exit 4), `8dd689d` (Trip/DST), `78c8a1f` (Textausgabe).

## Offene Punkte

Keine.
