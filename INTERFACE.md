# Interface – flix (`flixbus-cli`)

Verbindlicher Vertrag. Alles hier wird wörtlich umgesetzt.

## Aufruf

```
flix <BEFEHL> [OPTIONEN]
flix --help
flix --version
```

Globale Option `--json` ist überall gültig und darf an jeder Stelle stehen.

## Exit-Codes

| Code | Bedeutung |
|---|---|
| 0 | Erfolg |
| 1 | Usage / Validierung (inkl. unbekannte Stadt, Datum in der Vergangenheit) |
| 2 | Auth (für diesen Befehl nicht zutreffend, aber reserviert) |
| 3 | Netzwerk / HTTP-Fehler |
| 4 | Parse-Fehler (unlesbare oder unerwartete API-Antwort) |
| 5 | Forbidden / nicht unterstützte Aktion |

## JSON-Ausgabe

Mit `--json` steht auf stdout **genau ein** JSON-Objekt. Ohne `--json` steht
dieselbe Information als lesbarer Text auf stdout; Warnungen und Meldungen
gehen immer auf stderr.

Fehlerobjekt (unabhängig vom Befehl):

```json
{"error": {"code": 1, "kind": "usage", "message": "…"}}
```

`kind`-Werte: `usage`, `auth`, `network`, `parse`, `forbidden`, `internal`.
Ein Traceback erscheint nie auf stdout.

---

## `flix cities QUERY [--limit N] [--json]`

Findet Städte per Name.

* `QUERY` – Suchtext, nicht leer.
* `--limit N` – maximale Trefferzahl (Standard 10, 1–50).

Erfolg:

```json
{
  "query": "heilbronn",
  "cities": [
    {"id": "40d91420-…", "name": "Heilbronn", "country": "de",
     "district": "Baden-Württemberg", "lat": 49.168435, "lon": 9.219901,
     "timezone_offset_seconds": 7200, "is_flixbus_city": true,
     "legacy_id": 110}
  ],
  "count": 1
}
```

Fehler: leere Query → Exit 1.

---

## `flix search FROM TO [OPTIONEN]`

| Option | Typ | Standard | Bedeutung |
|---|---|---|---|
| `--date` | `YYYY-MM-DD` \| `heute` \| `morgen` | `heute` | Abreisedatum |
| `--adults` | int 1–9 | 1 | Erwachsene |
| `--max-price` | EUR > 0 | – | Höchstpreis (Grundpreis je Person) |
| `--direct` | flag | aus | nur Direktverbindungen |
| `--after` | `HH:MM` | – | Abfahrt frühestens |
| `--before` | `HH:MM` | – | Abfahrt spätestens |
| `--sort` | `price` \| `departure` \| `duration` | `departure` | Sortierung |
| `--limit` | int ≥ 1, max 200 | 20 | maximale Treffer |
| `--json` | flag | – | JSON-Ausgabe |

* `FROM`/`TO` sind Stadtnamen oder City-UUIDs.
* Mehrdeutige Namen: beste Übereinstimmung, exakter Namens-Treffer zuerst.
  Die **aufgelöste Stadt steht im Ergebnis** (`from`/`to`).
* Unbekannte Stadt → Exit 1, `kind: usage`, `message` enthält Vorschläge.

Erfolg:

```json
{
  "from": {"query": "heilbronn", "id": "40d91420-…", "name": "Heilbronn",
           "country": "de", "timezone_offset_seconds": 7200},
  "to":   {"query": "berlin", "id": "40d8f682-…", "name": "Berlin",
           "country": "de", "timezone_offset_seconds": 7200},
  "date": "2026-10-25",
  "currency": "EUR",
  "adults": 1,
  "count": 7,
  "filters": {"max_price": 20.0, "direct": true, "after": null,
              "before": null},
  "trips": [
    {
      "trip_id": "direct:45df97f7-…",
      "status": "available",
      "direct": true,
      "transfers": 0,
      "provider": "flixbus",
      "departure": "2026-10-25T07:06:00+02:00",
      "arrival":   "2026-10-25T13:57:00+02:00",
      "departure_station": "Berlin ZOB",
      "arrival_station": "Berlin Südkreuz",
      "departure_city": "Heilbronn",
      "arrival_city": "Berlin",
      "duration_minutes": 411,
      "duration_text": "6h51m",
      "price": 19.99,
      "price_with_platform_fee": 20.98,
      "seats_available": 42,
      "bike_slots": 0,
      "capacity": "medium",
      "means_of_transport": "bus",
      "booking_url": "https://www.flixbus.de/…"
    }
  ]
}
```

Fehler:
* ungültiges `--date`/`--after`/`--before`/`--adults`/`--max-price`/`--limit` → Exit 1
* Datum in der Vergangenheit → Exit 1
* unbekannte Stadt → Exit 1 mit Vorschlägen
* HTTP ≠ 200 oder unlesbares JSON → Exit 3 bzw. 4

---

## `flix trip TRIP_ID [--json]`

* `TRIP_ID` – `uid`/`trip_id` aus der `search`-Ausgabe. Muss zu einem
  bekannten Trip passen.
* Zeiten in lokaler Zeit der Abfahrtsstadt mit Offset.

Erfolg:

```json
{
  "trip_id": "direct:45df97f7-…",
  "status": "available",
  "from": {"city": "Heilbronn", "station": "Heilbronn Hbf",
           "time": "2026-10-25T07:06:00+02:00"},
  "to":   {"city": "Berlin", "station": "Berlin ZOB",
           "time": "2026-10-25T13:57:00+02:00"},
  "duration_minutes": 411,
  "duration_text": "6h51m",
  "direct": true,
  "transfers": 0,
  "price": 19.99,
  "price_with_platform_fee": 20.98,
  "seats_available": 42,
  "stops": [
    {"type": "departure", "station": "Heilbronn Hbf", "city": "Heilbronn",
     "time": "2026-10-25T07:06:00+02:00", "means_of_transport": "bus"},
    {"type": "transfer", "station": "Heidelberg Hbf", "city": "Heidelberg",
     "time": "2026-10-25T08:09:00+02:00", "means_of_transport": "train"},
    {"type": "arrival", "station": "Berlin ZOB", "city": "Berlin",
     "time": "2026-10-25T13:57:00+02:00", "means_of_transport": "train"}
  ]
}
```

Fehler:
* unbekannte/leere `TRIP_ID` → Exit 1
* ID bekannt syntaktisch, aber nicht im Cache und keine Live-Auflösung
  möglich → Exit 4 (`kind: parse`) mit Hinweis, dass `trip` die Halte aus
  der Suche bezieht (kein anonymous erreichbarer Detail-Endpunkt).

---

## `flix cheapest FROM TO --from YYYY-MM-DD --days N [--adults N] [--json]`

| Option | Typ | Standard | Bedeutung |
|---|---|---|---|
| `--from` | `YYYY-MM-DD` | `heute` | erster Tag des Zeitraums |
| `--days` | int 1–14 | 7 | Anzahl Tage |
| `--adults` | int 1–9 | 1 | Erwachsene |

Erfolg:

```json
{
  "from": {"id": "…", "name": "Heilbronn"},
  "to":   {"id": "…", "name": "Berlin"},
  "start_date": "2026-10-25",
  "days": 3,
  "currency": "EUR",
  "daily": [
    {"date": "2026-10-25", "price": 19.99, "trips": 12},
    {"date": "2026-10-26", "price": null, "trips": 0},
    {"date": "2026-10-27", "price": 24.90, "trips": 9}
  ],
  "best": {"date": "2026-10-25", "price": 19.99}
}
```

`best` ist `null`, wenn im ganzen Zeitraum keine Verbindung lag.
Fehler: `--days` > 14 oder < 1 → Exit 1; unbekannte Stadt → Exit 1.

---

## `flix watch …`

```
flix watch add FROM TO --date YYYY-MM-DD|heute|morgen --below EUR [--adults N] [--json]
flix watch list [--json]
flix watch remove ID [--json]
flix watch check [--json]
```

Ablage: `$XDG_CONFIG_HOME/flixbus-cli/watch.json`, Fallback
`~/.config/flixbus-cli/watch.json`. Keine Zugangsdaten, nur öffentliche
Suchparameter.

* `add` – legt einen Eintrag an, ID = 8 Hex-Zeichen (SHA-1 über die
  Suchparameter, damit `add` idempotent ist).
* `list` – alle Einträge, auch bei leerer Liste Exit 0.
* `remove ID` – unbekannte ID ist ein No-op, Exit 0 (idempotent).
* `check` – fragt live ab und liefert Treffer unter dem Schwellwert.

Eintrag:

```json
{"id": "1a2b3c4d", "from": {"id": "…", "name": "Heilbronn"},
 "to": {"id": "…", "name": "Berlin"}, "date": "2026-10-25",
 "below": 20.0, "adults": 1, "created_at": "2026-10-20T09:00:00+00:00"}
```

`check`:

```json
{"checked": 2, "below_threshold": 1,
 "results": [{"id": "1a2b3c4d", "date": "2026-10-25", "below": 20.0,
              "cheapest": 19.99, "trips": 12, "matches": true}]}
```

Fehler: `--below` fehlt oder ≤ 0 → Exit 1; unbekannte Stadt → Exit 1.

---

## `flix book …`

Buchen ist nicht unterstützt. Jeder Aufruf von `flix book` – auch
`flix book --confirm` – endet mit:

* Exit **5**
* `kind: forbidden`
* Message: Buchen wird nicht unterstützt; die CLI liefert nur
  Suchergebnisse, Preise und Links.

Es wird keine Anfrage an Flix abgesetzt.

---

## `flix --help` / `flix --version`

* `--help` → Nutzung auf stdout, Exit 0.
* `--version` → `flix <version>`, Exit 0.