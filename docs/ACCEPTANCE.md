# Akzeptanztests – flixbus-cli

Jeder Test ist gegen das Interface in `INTERFACE.md` formuliert.
Tests erreichen **keine** echten Server: das Harness unter
`/home/box/cli-daily/agent-learnings/tests/harness/` blockiert alles außer
Loopback (`PYTHONPATH`, `ACCEPTANCE_SANDBOX=1`). Live-Prüfungen stehen
getrennt unten und sind als `LIVE` markiert.

Konventionen:
* `json` = Aufruf mit `--json`; geprüft wird, dass auf stdout **genau ein**
  JSON-Objekt steht (`json.loads(stdout)` ohne Fehler) und `stderr` nichts
  in stdout leckt.
* `kein traceback` = stderr/stdout enthalten nicht das Wort `Traceback` und
  kein `File "`-Fragment.

---

## A – global

| # | Fall | Erwartet |
|---|---|---|
| A1 | `flix --help` | Exit 0, Text enthält `cities`, `search`, `trip`, `cheapest`, `watch`, `book` |
| A2 | `flix --version` | Exit 0, Ausgabe `flix <x.y.z>` |
| A3 | `flix` (ohne Befehl) | Exit 0, Hilfe auf stdout |
| A4 | `flix --json` (ohne Befehl) | Exit 0, genau ein JSON-Objekt |

## B – cities

| # | Fall | Erwartet |
|---|---|---|
| B1 | `flix cities heilbronn --json` (Mock: 2 Treffer) | Exit 0; `count == 2`; erstes Element ist der exakte Namens-Treffer; `id`, `name`, `country` vorhanden |
| B2 | `flix cities berlin --limit 1 --json` | Exit 0; `len(cities) == 1` |
| B3 | `flix cities "" --json` | Exit 1, `kind == "usage"`, ein JSON-Objekt |
| B4 | `flix cities xyz --limit 0 --json` | Exit 1 (`--limit` ≥ 1) |
| B5 | `flix cities xyz --limit abc --json` | Exit 1, kein Traceback |
| B6 | `flix cities xyz --json`, Server 500 | Exit 3, `kind == "network"` |
| B7 | `flix cities xyz --json`, Server liefert HTML | Exit 4, `kind == "parse"` |

## C – search

| # | Fall | Erwartet |
|---|---|---|
| C1 | `flix search heilbronn berlin --date 2026-10-25 --json` | Exit 0; `from.name == "Heilbronn"`, `to.name == "Berlin"`; `count` stimmt mit `len(trips)` überein |
| C2 | Ausgabe enthält je Trip `departure`/`arrival` mit Offset | Offset der Abfahrtsstadt; `parse_iso(departure)` == `from`-Datum |
| C3 | Trip-Zeitstempel lokal in Abfahrtsstadt | Umrechnungstest: Mock-Trip `2026-10-25T07:06:00+02:00`, Abfahrtsstadt-Offset 7200 → Ausgabe `2026-10-25T07:06:00+02:00` |
| C4 | `--adults 2` | `adults == 2` im Ergebnis; `products == {"adult": 2}` im Request |
| C5 | `--max-price 20` | alle `price <= 20`; ein Trip mit 25 EUR fällt weg |
| C6 | `--direct` | alle `direct == true` |
| C7 | `--after 09:00 --before 18:00` | alle Abfahrten ≥ 09:00 und ≤ 18:00 lokal |
| C8 | `--after 25:00` | Exit 1 (`HH:MM`), kein Request |
| C9 | `--sort price` | Preise aufsteigend; `--sort duration` → `duration_minutes` aufsteigend; `--sort departure` → chronologisch |
| C10 | `--limit 3` | `len(trips) <= 3` |
| C11 | unbekannte Stadt `flix search atlantis berlin --json` | Exit 1, `kind == "usage"`, Message enthält Vorschläge (Mock: Name der Kandidaten) |
| C12 | City-UUID als FROM | funktioniert wie Name; `from.query` == die UUID |
| C13 | mehrdeutiger Name | beste Übereinstimmung gewählt; aufgelöste Stadt im Ergebnis sichtbar |
| C14 | `--date 2020-01-01` | Exit 1 (Vergangenheit), kein Request |
| C15 | `--date 25.10.2026` | Exit 1 (Format), kein Request |
| C16 | `--date morgen` | Erfolg; `date` == morgen |
| C17 | `--adults 0` / `--adults abc` | Exit 1 |
| C18 | `--max-price -5` / `--max-price abc` | Exit 1 |
| C19 | Server 403/500 | Exit 3 |
| C20 | Antwort ohne `trips` | Exit 4 |
| C21 | `trips[0].results` als **Dict** | wird korrekt iteriert (nicht als Liste) – ein Dict mit 3 Einträgen liefert 3 Trips |
| C22 | Stations-/Cities-Map | `departure_station` ist der Name aus `stations[station_id]`, kein UUID |
| C23 | gleiche Stadt FROM und TO | Exit 1 |
| C24 | unbekanntes `--sort` | Exit 1 |

## D – trip

| # | Fall | Erwartet |
|---|---|---|
| D1 | `flix trip <gültige ID> --json` nach `search` | Exit 0; `stops[0].type == "departure"`, letztes `== "arrival"` |
| D2 | Direktverbindung | genau 2 Stops, `direct == true`, `transfers == 0` |
| D3 | Umstieg mit 2 Legs | 3 Stops, mittlerer `type == "transfer"` |
| D4 | Stop-Zeiten | alle mit Offset der Abfahrtsstadt, aufsteigend |
| D5 | `flix trip "" --json` | Exit 1 |
| D6 | `flix trip unbekannte-id --json` | Exit 4, `kind == "parse"`, kein Traceback |
| D7 | Stationsnamen aufgelöst | jeder Stop hat `station` als Name, nicht als UUID |

## E – cheapest

| # | Fall | Erwartet |
|---|---|---|
| E1 | `--from 2026-10-25 --days 3` | Exit 0; `len(daily) == 3`; Daten folgen aufeinander |
| E2 | Tag ohne Verbindung | `{"date": …, "price": null, "trips": 0}` – Tag bleibt in der Liste |
| E3 | `best` | Tag mit dem minimalen Preis; `null`, wenn kein Tag eine Verbindung hat |
| E4 | `--days 15` | Exit 1 |
| E5 | `--days 0` | Exit 1 |
| E6 | unbekannte Stadt | Exit 1 |
| E7 | Teilfehler (ein Tag HTTP 500) | Exit 3, kein Teilresultat |

## F – watch

| # | Fall | Erwartet |
|---|---|---|
| F1 | `watch add A B --date D --below 20 --json` | Exit 0; `id` ist 8 Hex-Zeichen; Datei existiert mit Modus 0600 |
| F2 | `watch list` nach `add` | Exit 0, ein Eintrag |
| F3 | `watch list` ohne Einträge | Exit 0, `items == []` |
| F4 | `watch remove ID` | Exit 0, Eintrag weg |
| F5 | `watch remove unbekannt` | Exit 0, `noop == true` (idempotent) |
| F6 | `watch add` ohne `--below` | Exit 1 |
| F7 | `watch add … --below 0` / `--below abc` | Exit 1 |
| F8 | `watch add A B --date 2020-01-01 --below 5` | Exit 1 (Vergangenheit), keine Datei geschrieben |
| F9 | `watch check` | Exit 0; `checked == len(items)`; `below_threshold` zählt die Treffer |
| F10 | `watch check` ohne Einträge | Exit 0, `checked == 0` |
| F11 | `XDG_CONFIG_HOME` zeigt auf Temp-Verzeichnis | Datei wird dort abgelegt, nicht unter `$HOME` |
| F12 | `watch.json` kaputt (kein JSON) | Exit 0 bei `list` (leer) statt Traceback |
| F13 | `watch add` zweimal identisch | gleiche ID, kein Duplikat (idempotent) |

## G – book (forbidden)

| # | Fall | Erwartet |
|---|---|---|
| G1 | `flix book --json` | Exit **5**, `kind == "forbidden"` |
| G2 | `flix book heilbronn berlin --date morgen --confirm --json` | Exit 5, gleiche Meldung |
| G3 | `flix book … --json` | **kein** HTTP-Request (Harness-Log bleibt leer) |
| G4 | `flix book` ohne `--json` | Exit 5, Meldung auf stderr |

## H – Fehlerpfad-Konventionen (für alle Befehle)

| # | Fall | Erwartet |
|---|---|---|
| H1 | jeder Fehler mit `--json` | genau ein JSON-Objekt `{"error": {…}}`, `code` == Exit-Code |
| H2 | jeder Fehler | kein Traceback in stdout oder stderr |
| H3 | Argumentfehler mit `--json` (`flix cities --json --limit`) | Exit 1, ein JSON-Objekt (kein argparse-Text auf stdout) |
| H4 | unbekannter Befehl `flix quatsch --json` | Exit 1, ein JSON-Objekt |
| H5 | `--json` an jeder Stelle erkannt (`flix --json cities x`, `flix cities x --json`) | identisches Verhalten |

---

## LIVE (nur manuell, nicht in der Testsuite)

| # | Befehl | Prüfung |
|---|---|---|
| L1 | `flix search heilbronn berlin --date <+5 Tage> --limit 5 --json` | `from.name == Heilbronn`, `to.name == Berlin`, Datum == Suchdatum, genau ein JSON-Objekt |
| L2 | `flix search stuttgart münchen --date <+5 Tage> --max-price 20 --direct --json` | alle `price <= 20`, alle `direct == true`, Datum == Suchdatum, Städte stimmen |
| L3 | `flix cities berlin --json` | live Treffer, UUID plausibel |
| L4 | `flix cheapest stuttgart berlin --from <+5 Tage> --days 3 --json` | Tagesfolge, `best` = Minimum |