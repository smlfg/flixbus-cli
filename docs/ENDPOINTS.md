# FlixBus / FlixTrain – verwendete API-Endpunkte

Recherche vom 2026-10-20, live gegen `https://global.api.flixbus.com` verifiziert.
Kein API-Key, kein Login, kein Bot-Schutz. Es genügt ein normaler
Browser-User-Agent. Es handelt sich um die undokumentierte JSON-Schnittstelle,
die auch die Website selbst nutzt.

Gemeinsame Header:

```
Accept: application/json
Accept-Language: de-DE,de;q=0.9
User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36
```

Basis: `https://global.api.flixbus.com`

---

## 1. Städte (Autocomplete)

```
GET /search/autocomplete/cities
```

| Parameter | Beispiel | Bedeutung |
|---|---|---|
| `q` | `heilbronn` | Suchtext (Pflicht) |
| `lang` | `de` | Sprache der Rückgabe |
| `country` | `de` | Länder-Kontext fürs Ranking |
| `flixbus_cities_only` | `false` | `false` = auch Orte ohne Flix-Anbindung |

Beispiel (HTTP 200):

```json
[
  {
    "score": 63.395184,
    "country": "de",
    "has_train_station": true,
    "district": "Baden-Württemberg",
    "name": "Heilbronn",
    "legacy_id": 110,
    "location": {"lon": 9.219901, "lat": 49.168435},
    "timezone_offset_seconds": 7200,
    "id": "40d91420-8646-11e6-9066-549f350fcb0c",
    "stations": null,
    "is_flixbus_city": true
  }
]
```

Wichtig:
* `id` ist die City-UUID und wird von der Suche erwartet.
* `legacy_id` ist die numerische ID – die braucht nur die (nicht anonymous
  erreichbare) Mobile-API.
* `timezone_offset_seconds` liefert die Zeitzone der Abfahrtsstadt
  (7200 = +02:00 für DE im Sommer). Das ist die Referenz für die Ausgabe
  lokaler Zeiten.
* Ergebnisliste ist nach `score` sortiert; der exakte Namens-Treffer
  (`name.lower() == q.lower()`) ist die beste Auflösung.

## 2. Haltestellen (Autocomplete)

```
GET /search/autocomplete/stations
```

Parameter: `q` (Pflicht), `locale` (z. B. `de`).

Antwort ist eine Liste mit zusätzlich `address`, `zipcode`, `city`
(Namensobjekt mit `id`/`legacy_id`) und `importance_order`:

```json
[{"zipcode": "74172", "score": 19.21, "country": {"code": "de"},
  "address": "Bf West (Kanalstraße)", "city": {"name": "Neckarsulm", "legacy_id": 588,
  "id": "40dc48b2-8646-11e6-9066-549f350fcb0c"}, "name": "Neckarsulm",
  "legacy_id": 27, "id": "dcbaccb2-9603-11e6-9066-549f350fcb0c",
  "importance_order": 100, "slug": "heilbronn", "is_train": false}]
```

## 3. Verbindungen (Suche)

```
GET /search/service/v4/search
```

| Parameter | Beispiel | Bedeutung |
|---|---|---|
| `from_city_id` | `40d91420-…-549f350fcb0c` | City-UUID Abfahrt (Pflicht) |
| `to_city_id` | `40d8f682-…-549f350fcb0c` | City-UUID Ankunft (Pflicht) |
| `departure_date` | `25.10.2026` | **Format `DD.MM.YYYY`** (Pflicht) |
| `products` | `{"adult":1}` | JSON-String, nicht form-urlencoded |
| `currency` | `EUR` | ISO-4217 |
| `locale` | `de` | Sprache der Texte |
| `search_by` | `cities` | oder `stations` |
| `include_after_midnight_rides` | `1` | Fahrten nach 00:00 mitnehmen |

Antwort (HTTP 200), Top-Level-Schlüssel:

```
response_uuid, trips, operators, brands, cities, stations,
no_bikes_period, global_platform_fees, platform_fee_in_price_required
```

* `trips` ist eine Liste (je Verkehrstage/Suchsegment ein Element).
* `trips[0].results` ist ein **Dict**, nicht eine Liste: Schlüssel = `uid`,
  Werte = die Verbindung. Iterieren über `.values()`.
* `stations` ist ein Dict `station_id -> {id, legacy_id, name, slug, is_train, importance}`
  – damit lassen sich alle Haltestellennamen ohne zweiten Request auflösen.
* `cities` ist ein Dict `city_id -> {name, slug, legacy_id, id}`.

### Aufbau eines Ergebnisses

```json
{
  "uid": "direct:45df97f7-…:dcbf78bb-…:dcbabbfa-…",
  "status": "available",
  "transfer_type": "Direkt",
  "transfer_type_key": "direct",
  "provider": "flixbus",
  "departure": {"date": "2026-10-25T00:20:00+02:00",
                "city_id": "40d90995-…", "station_id": "dcbf78bb-…"},
  "arrival":   {"date": "2026-10-25T02:50:00+01:00",
                "city_id": "40d901a5-…", "station_id": "dcbabbfa-…"},
  "duration": {"hours": 2, "minutes": 30},
  "price": {"total": 19.99, "original": 19.99, "average": 19.99,
            "total_with_platform_fee": 20.98, "average_with_platform_fee": 20.98},
  "remaining": {"seats_left_at_price": null, "seats": null,
                "bike_slots": 0, "capacity": "medium"},
  "available": {"seats": 42, "bike_slots": 0},
  "intermediate_stations_count": 0,
  "legs": [
    {"ride_id": "45df97f7-2e09-4f5c-b23c-9bd2fda6a66f",
     "departure": {"date": "…", "city_id": "…", "station_id": "…"},
     "arrival":   {"date": "…", "city_id": "…", "station_id": "…"},
     "means_of_transport": "bus", "amenities": ["WIFI", "POWER_SOCKETS"],
     "is_marketplace": false, "operator_id": "mfb", "brand_id": "…",
     "sub_brand_id": null, "vehicle_details": [],
     "layout_configuration": [{"column_layout": "TWO_TWO", "deck": 0}],
     "cheapest_seat": "SEATER",
     "seat_types": [{"seat_type_key": "SEATER", "seat_type": "SEATER"}]}
  ],
  "messages": ["Regionalverbindung wird von unseren Partnern durchgeführt …"],
  "restrictions": {"sale_restriction": false, "bikes_allowed": true,
                   "wheelchair_status": "unknown"}
}
```

Beobachtungen, die die Implementierung beeinflussen:

* `transfer_type_key` ist `"direct"` oder eine `#`-verkettete Liste von
  Verkehrsmitteln (`"train#train"`, `"bus#train"`, …). `direct` lässt sich
  daran erkennen.
* `intermediate_stations_count` ist **nur bei manchen Ergebnissen** vorhanden
  (nicht bei allen Zügen, nicht bei jeder Umstiegsverbindung). Fehlt es, ist
  es `None`, nicht `0`.
* Zeiten tragen den **Offset der jeweiligen Stadt** – Stuttgart
  `+02:00`, München `+01:00` am selben Tag. Für die Anzeige wird deshalb auf
  den Offset der Abfahrtsstadt normalisiert.
* `price.total` ist der Grundpreis, `price.total_with_platform_fee` der
  Endpreis an der Kasse. Für „maximaler Preis“-Vergleiche wird `total`
  verwendet (das ist der von Flix selbst verglichene Wert); im JSON stehen
  beide.
* `legs` ist die vollständige Halt-Folge der Verbindung: jedes Leg hat
  Abfahrts- und Ankunftshaltestelle mit Zeit. Für eine Verbindung mit
  Umstieg sind das genau die Umstiegsstationen. Für `flix trip` wird die
  Haltliste aus `legs` aufgebaut (Abfahrt des ersten Legs … Ankunft des
  letzten Legs) und mit `stations`/`cities` aus derselben Antwort benannt.

## 4. Nicht anonymous erreichbar (Stand 2026-10-20)

* `GET /mobile/v1/trip/search.json` → `403 {"code":403,"message":"You do not
  have the necessary permissions."}`. Braucht `X-API-Authentication`
  (Client-Token der App).
* Alle anderen Pfade unter `/search/service/v4/…` (z. B. `trip_details`,
  `ride_details`, `rides`, `stops`, `ride_stops`, `timetable`,
  `station_timetable`) → `403 {"message":"Missing Authentication Token"}`.
  Das ist die Antwort des API-Gateways auf *unbekannte Routen*, nicht auf
  fehlende Rechte – der Pfad existiert schlicht nicht (anonymous).
* `https://developer.api.flixbus.com` (Partner-Portal) ist hinter Microsoft
  Entra ID gesperrt.

Konsequenz für dieses CLI: **es gibt keinen anonym erreichbaren
Fahrtdetails-Endpunkt.** Die Halte einer Verbindung stecken in `legs` der
Such-Antwort. `flix trip` arbeitet deshalb offline auf den bei der Suche
zwischengespeicherten Daten und zeigt die Haltfolge der Legs. Ein späterer
Lauf kann `trip` um einen Cache erweitern, der bei der Suche die Halte
speichert; das Interface (`flix trip TRIP_ID`) bleibt gleich.

## 5. Buchen

Buchen ist bewusst nicht implementiert. Die Buchungs-/Fare-Endpunkte der
Website sind zusätzlich bot-geschützt; `flix book` existiert nur, um den
Agenten einen sauberen, dokumentierten Exit-Code 5 zu geben.

## 6. Weiterführende Quellen

* `https://global.api.flixbus.com` – die API selbst.
* `https://gtfs.gis.flix.tech/gtfs_generic_eu.zip` – offizieller
  GTFS-Schedule-Feed (nur Fahrplan, keine Preise), ODbL-1.0. Nicht von der
  CLI genutzt.
* Das Portal `developer.api.flixbus.com` ist die vertragliche API für
  Distributoren; dort gibt es Suche, Verfügbarkeit, Buchung, Ticketing.