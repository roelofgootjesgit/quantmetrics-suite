# QuantLog Event Versioning Policy

## 1. Doel

Dit beleid borgt dat schemawijzigingen beheersbaar blijven en historische replay niet breken.

QuantLog behandelt event schema als contract, niet als vrijblijvende logstructuur.

---

## 2. Versie-niveaus

QuantLog gebruikt `event_version` per event type.

### Major change (breaking)

Nieuwe `event_version` verplicht bij:

- verplicht veld toevoegen
- veld verwijderen
- veld hernoemen
- veldtype wijzigen
- enum semantiek breken
- payload-structuur breken

### Minor change (non-breaking)

Zelfde `event_version` mag blijven bij:

- optioneel veld toevoegen
- extra payload metadata toevoegen
- nieuw event type toevoegen (zonder bestaande eventtypes te breken)
- extra enum waarde die oude consumers niet breekt

### Patch-level change

Geen schema-impact, alleen:

- documentatie-verbetering
- testuitbreiding
- interne tooling zonder contractwijziging

---

## 3. Backward compatibility regels

1. Oude events moeten replaybaar blijven.
2. Validator mag oude eventversies niet stilzwijgend breken.
3. Breaking changes vereisen:
   - nieuwe `event_version`
   - fixture updates
   - migratiestrategie of compatibiliteitslaag

---

## 4. Replay-compatibiliteit

Replay is een primaire succesmaatstaf.

Bij schemawijzigingen moet bewezen zijn:

- replay van oude fixtures werkt nog
- replay-ordering blijft deterministisch
- correlatievelden blijven bruikbaar (`trace_id`, `order_ref`, `position_id`, `run_id`, `session_id`)

---

## 5. Migratiebeleid

Bij breaking wijzigingen:

1. Nieuwe versie introduceren.
2. Oude versie minimaal tijdelijk ondersteunen in validator/replay.
3. Fixtureset voor oud + nieuw eventformat onderhouden.
4. Pas daarna oude variant deprecaten.

---

## 6. CI vereisten bij schemawijziging

Schemawijziging mag alleen mergen als alle gates groen zijn:

- unit tests
- contract fixture checks
- end-to-end smoke
- sample day validate/summarize
- replay integrity check
- quality score gate (threshold)
- anomaly negative gate (moet falen)

---

## 7. Verantwoordelijkheid

Een schemawijziging vereist expliciete review op:

- contract-impact
- replay-impact
- fixture-impact
- docs-impact

Geen schemawijziging zonder bijbehorende test- en documentatie-update.

---

## 8. Voorbeelden

### Toegestaan zonder nieuwe `event_version`

- `order_filled.payload` krijgt optioneel veld `liquidity_flag`.

### Vereist nieuwe `event_version`

- `trade_action.payload.decision` hernoemen naar `action`.
- `source_seq` type wijzigen van int naar string.
- `trace_id` optioneel maken of verwijderen.

