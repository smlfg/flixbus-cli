# Anforderungen – flixbus-cli

## Ziel

Eine Python-CLI (`flix`), mit der ein Agent **live** FlixBus- und
FlixTrain-Verbindungen abfragen kann: Städte und Haltestellen finden,
Verbindungen mit Live-Preisen und freien Plätzen suchen und filtern,
Haltfolgen einer Verbindung ansehen, den günstigsten Tag in einem Zeitraum
finden und Verbindungen lokal auf einen Preis-Schwellwert beobachten.

Buchen ist **nicht** Teil des Werkzeugs.

## Datenquelle

Die inoffizielle, aber anonymous erreichbare JSON-Schnittstelle von
`https://global.api.flixbus.com`, die auch die Flix-Website selbst nutzt.
Kein Login, kein API-Key. Recherche und Rohbeispiele: `docs/ENDPOINTS.md`.

## Funktionale Anforderungen

### F1 – Städte und Haltestellen finden

`flix cities QUERY` liefert Städte (City-UUID, Name, Land, Bezirk,
Koordinaten, Zeitzonenoffset, `is_flixbus_city`). Die UUID ist der Schlüssel
für alle weiteren Befehle. Sortierung nach API-Score, exakte Namens-Treffer
zuerst. `--limit` begrenzt die Trefferzahl.

### F2 – Verbindungen suchen

`flix search FROM TO` liefert für ein Datum die Verbindungen mit
Abfahrts-/Ankunftszeit (lokale Zeit der Abfahrtsstadt, mit Offset),
Haltestellenname (aus der `stations`-Karte der Antwort), Dauer, Umstiegsart,
Preis (Grundpreis und Endpreis inkl. Plattformgebühr), freie Plätze,
Fahrradplätze und Kapazitätsstufe.

Pflichtfilter:
* `--date YYYY-MM-DD | heute | morgen`
* `--adults N`
* `--max-price EUR` – filtert nach `price.total`
* `--direct` – nur `transfer_type_key == "direct"`
* `--after HH:MM` / `--before HH:MM` – filtert nach lokaler Abfahrtszeit
* `--sort price | departure | duration`
* `--limit N`

FROM/TO ist ein Stadtname oder eine City-UUID. Bei mehreren Treffern
gewinnt die beste Übereinstimmung; die **aufgelöste Stadt wird im Ergebnis
mit ausgegeben**, damit ein Agent sieht, was wirklich benutzt wurde. Bei
keinem Treffer Exit 1 mit Vorschlägen.

### F3 – Haltfolge einer Verbindung

`flix trip TRIP_ID` zeigt die Halte der Verbindung mit Zeiten.
`TRIP_ID` kommt aus der `search`-Ausgabe (Feld `uid` bzw. `trip_id`).

Es gibt **keinen** anonymous erreichbaren Fahrtdetails-Endpunkt
(`docs/ENDPOINTS.md`, Abschnitt 4). Die Haltfolge wird daher aus den `legs`
der Such-Antwort aufgebaut – jedes Leg liefert Abfahrts- und
Ankunftshaltestelle mit Zeit; bei Umstiegen sind das genau die
Umstiegsstationen. `trip` arbeitet offline auf dem Ergebnis der letzten
Suche im gleichen Prozess und, falls vorhanden, auf dem lokalen Cache.

### F4 – Günstigster Tag in einem Zeitraum

`flix cheapest FROM TO --from YYYY-MM-DD --days N` (N ≤ 14) fragt jeden Tag
im Zeitraum ab und liefert den günstigsten Preis pro Tag sowie den Tag mit
dem Gesamtminimum. Tage ohne Verbindung werden mit `null` ausgewiesen und
nicht übersprungen, damit die Tagesfolge vollständig bleibt.

### F5 – Lokaler Preis-Watch

`flix watch add FROM TO --date ... --below EUR` legt lokal einen Beobachtungseintrag
an; `watch list` zeigt alle, `watch remove ID` löscht (idempotent),
`watch check` fragt live ab und meldet, welche Einträge unter dem
Schwellwert liegen. Ablage in
`$XDG_CONFIG_HOME/flixbus-cli/watch.json` (Fallback `~/.config`).

### F6 – Buchen ist nicht unterstützt

`flix book …` endet immer mit Exit 5 und einer klaren Meldung – auch mit
`--confirm`. Es wird keine Buchungsanfrage gestellt.

## Nicht-funktionale Anforderungen

* **N1 Exit-Codes**: 0 ok, 1 Usage/Validierung, 2 Auth, 3 Netzwerk/HTTP,
  4 Parse, 5 Forbidden (nicht unterstützte Aktion). Jede Fehlerklasse hat
  genau einen Code, „unbekannt" ist nie Erfolg.
* **N2 JSON-Vertrag**: mit `--json` steht auf stdout **genau ein**
  JSON-Objekt – auch bei Fehlern, auch bei Argumentfehlern. Fehlerobjekt:
  `{"error": {"code": <int>, "kind": <str>, "message": <str>}}`.
  Nie ein Traceback auf stdout; Logs und Meldungen gehen nach stderr.
* **N3 Eingabevalidierung**: Datum, Uhrzeit, Preis, `--adults`, `--days`,
  `--limit` werden vor jedem Request geprüft. Ungültige Werte → Exit 1,
  kein Request. Datum in der Vergangenheit → Exit 1.
* **N4 Zeitzonen**: alle Ausgabezeiten in lokaler Zeit der Abfahrtsstadt mit
  Offset. Die API liefert je Stadt einen eigenen Offset; der der
  Abfahrtsstadt ist maßgeblich.
* **N5 Tests**: Tests erreichen nie echte Server. Konfigurationspfade
  kommen aus Umgebungsvariablen.
* **N6 Lizenz**: MIT. Autor nur Name + `smlfg`, keine erfundenen
  Personendaten.
* **N7 Abhängigkeiten**: nur `requests` (plus `pytest` als dev-Extra).

## Akzeptanztests

Vollständige Liste mit Fehlerpfaden: `docs/ACCEPTANCE.md`.

## Out of Scope

* Buchen, Bezahlen, Tickets, Login, Account.
* Rück- und Mehrwegsuche.
* Sitzauswahl, Sitzplatzkarten.
* Verspätungs-/Live-Abfahrtsdaten in Echtzeit (das sind
  Echtzeitdaten, die die Such-Antwort nicht liefert).