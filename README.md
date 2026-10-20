# flixbus-cli

`flix` – eine CLI, mit der ein Agent **live** FlixBus- und FlixTrain-Verbindungen
abfragen kann: Städte finden, Verbindungen mit Live-Preisen und freien Plätzen
suchen und filtern, Halte einer Verbindung ansehen, den günstigsten Tag in einem
Zeitraum finden und Preise lokal beobachten.

**Buchen ist nicht implementiert.** `flix book` endet immer mit Exit 5 und stellt
keine Anfrage an Flix.

Kein Login, kein API-Key. Die CLI nutzt die inoffizielle, anonymous erreichbare
JSON-Schnittstelle von `global.api.flixbus.com` – dieselbe, die die Flix-Website
selber nutzt. Verifiziert am 2026-10-20.

## Installation

```bash
pip install .
```

## Nutzung

```bash
flix cities heilbronn --limit 5 --json
flix search heilbronn berlin --date morgen --limit 5 --json
flix search stuttgart münchen --date morgen --max-price 20 --direct --json
flix trip "<trip_id aus search>" --json
flix cheapest heilbronn berlin --from morgen --days 7 --json
flix watch add heilbronn berlin --date morgen --below 25 --json
flix watch list --json
flix watch check --json
flix watch remove <id> --json
```

Mit `--json` steht auf stdout genau ein JSON-Objekt – auch bei Fehlern.
Ohne `--json` gibt es lesbare Textausgabe; Meldungen gehen nach stderr.

## Exit-Codes

| Code | Bedeutung |
|---|---|
| 0 | Erfolg |
| 1 | Usage / Validierung (unbekannte Stadt, Datum in der Vergangenheit) |
| 2 | Auth (reserviert) |
| 3 | Netzwerk / HTTP-Fehler |
| 4 | Parse-Fehler |
| 5 | Forbidden (nicht unterstützte Aktion, z. B. `book`) |

## Dokumentation

* `ANFORDERUNGEN.md` – was das Werkzeug können muss.
* `INTERFACE.md` – verbindlicher Vertrag für alle Befehle, Flags, Ausgabeformate.
* `docs/ACCEPTANCE.md` – Akzeptanztests inklusive aller Fehlerpfade.
* `docs/ENDPOINTS.md` – die verwendeten API-Endpunkte, live verifiziert, mit
  allen Fallstricken (Zeitzonen, `results` als Dict, fehlende Felder) und der
  Liste der Endpunkte, die anonym **nicht** erreichbar sind.

## Grenzen

* Kein Fahrtdetails-Endpunkt: Flix liefert die Halte einer Verbindung nur im
  Suchergebnis (`legs`). `flix trip` arbeitet deshalb auf den Daten der
  letzten `search` im selben Prozess. Details in `docs/ENDPOINTS.md`, Abschnitt 4.
* Suchergebnisse sind Momentaufnahmen, keine Live-Abfahrtsdaten.
* Preise sind Grundpreis (`price`) und Endpreis inklusive Plattformgebühr
  (`price_with_platform_fee`).

## Lizenz

MIT – siehe `LICENSE`.