# QuantBuild / QuantLog — Upgrade Data Verzamelen

## Logging Upgrade Handbook voor Desk-Grade Analyse

---

# Doel

Dit document beschrijft welke extra data we moeten loggen om van:

* **bruikbare observability**
  naar
* **desk-grade strategie-analyse**

te gaan.

De huidige logging is al voldoende voor:

* runtime-analyse
* no-trade diagnose
* basis filterdiagnose

Maar nog niet voldoende voor:

* echte near-miss analyse
* volledige gate/veto analyse
* same-bar mechaniek debugging
* edge-validatie op setup-niveau
* execution-analyse zodra er trades komen

Dit document definieert de volgende upgrade.

---

# 1. Strategische reden voor deze upgrade

Op dit moment weten we al veel:

* de bot leeft
* de bot evalueert
* de bot neemt geen trades
* veel events eindigen in `same_bar_already_processed`
* de echte evaluaties eindigen vaak in `no_setup`

Dat is waardevol.

Maar voor serieuze strategieverbetering missen we nog het antwoord op:

* **waarom wordt same-bar zo vaak geraakt?**
* **welke gate blokkeert de setup als eerste?**
* **hoe dicht zaten we bij een echte entry?**
* **welke module bleef meestal uit?**
* **is de strategie te streng, of komt de markt gewoon niet in setup?**

Dat is precies de data die nu toegevoegd moet worden.

---

# 2. Upgrade-principe

We voegen géén willekeurige logging toe.

We loggen alleen data die helpt om deze vier vragen te beantwoorden:

1. Waar komt de blokkade vandaan?
2. Welke module faalt?
3. Hoe dicht zitten we bij een trade?
4. Is dit een strategieprobleem of een runtime-/guardprobleem?

---

# 3. Nieuwe logging-doelen

De upgrade richt zich op vijf blokken:

1. **Same-bar mechaniek**
2. **Gate summary / veto chain**
3. **Near-miss analyse**
4. **Entry candidate context**
5. **Execution lifecycle** (pas relevant zodra entries komen)

---

# 4. Must-have uitbreidingen

---

## 4.1 Same-bar mechaniek loggen

## Probleem

We zien nu vaak:

* `eval_stage = same_bar_already_processed`
* `reason = cooldown_active`

Maar nog niet scherp genoeg:

* waarom dit exact gebeurt
* of dit logisch is
* of dit te agressief is

## Doel

Per evaluatie exact kunnen reconstrueren:

* was dit echt dezelfde bar?
* waarom is de bar niet opnieuw verwerkt?
* hoe vaak gebeurde dit al?
* zat er eerder al een echte setup-check op deze bar?

## Nieuwe velden

```json
{
  "new_bar_detected": false,
  "bar_ts": "2026-04-17T14:30:00Z",
  "poll_ts": "2026-04-17T14:31:25Z",
  "same_bar_guard_triggered": true,
  "same_bar_guard_reason": "last_processed_bar_ts_matches_latest_bar_ts",
  "same_bar_skip_count_for_bar": 3,
  "previous_eval_stage_on_bar": "no_entry_signal"
}
```

## Waarom dit nodig is

Hiermee kun je straks onderscheiden tussen:

* normale polling op dezelfde candle
* onterechte suppressie
* bar-processing bug
* te agressieve same-bar guard

---

## 4.2 Gate summary / veto chain

## Probleem

Nu moeten we uit losse velden afleiden welke gate de entry blokkeerde.

Dat is te omslachtig voor snelle desk-analyse.

## Doel

Per `signal_evaluated` direct zien:

* welke gates pass/fail gaven
* welke gate als eerste blokkeerde
* welke gates niet eens meer bereikt zijn

## Nieuwe velden

```json
{
  "gate_summary": {
    "session_gate": "pass",
    "regime_gate": "pass",
    "structure_gate": "fail",
    "liquidity_gate": "fail",
    "trigger_gate": "fail",
    "same_bar_guard": "pass",
    "risk_gate": "not_reached"
  },
  "blocked_by_primary_gate": "structure_gate",
  "blocked_by_secondary_gate": "trigger_gate",
  "evaluation_path": [
    "session_gate",
    "regime_gate",
    "structure_gate",
    "liquidity_gate",
    "trigger_gate"
  ]
}
```

## Waarom dit nodig is

Dit versnelt analyse enorm.

Je wilt in één oogopslag kunnen zien:

> “deze setup sterft bijna altijd bij structure of liquidity”

in plaats van dat je daarvoor zes losse velden moet correleren.

---

## 4.3 Near-miss analyse

## Probleem

Nu weten we meestal alleen:

* setup false
* combo count 0
* entry signal false

Maar niet:

* hoe dichtbij we ooit kwamen
* welke module nog miste
* of thresholds net te streng zijn

## Doel

Zien of er “bijna trades” waren.

Dat is cruciaal voor edge-validatie.

## Nieuwe velden

```json
{
  "near_entry_score": 0.35,
  "closest_to_entry_side": "long",
  "active_modules_count_long": 1,
  "active_modules_count_short": 0,
  "missing_modules_long": ["trigger", "liquidity"],
  "missing_modules_short": ["structure", "trigger", "liquidity"],
  "entry_distance_long": 2,
  "entry_distance_short": 3
}
```

## Uitleg

### `near_entry_score`

Een simpele interne score van 0–1:

* 0 = totaal geen setup
* 1 = entry direct geldig

### `entry_distance_long`

Aantal hoofdvoorwaarden dat nog ontbreekt tot entry.

Voorbeeld:

* 0 = entry klaar
* 1 = nog één blokkade
* 2 = nog twee blokkades

## Waarom dit nodig is

Je wilt straks weten:

* zaten we vaak dichtbij?
* of zat de strategie structureel mijlenver weg?

Dat bepaalt of je moet:

* thresholds aanpassen
* filters versoepelen
* of gewoon accepteren dat er geen edge was

---

## 4.4 Entry candidate context

## Probleem

We loggen nog te weinig context rond “bijna setup” situaties.

## Doel

Per evaluatie kunnen zien of er ooit serieus kandidaatgedrag was.

## Nieuwe velden

```json
{
  "setup_candidate": false,
  "candidate_side": null,
  "candidate_strength": 0.22,
  "candidate_reason": "structure_present_but_trigger_missing",
  "entry_ready": false
}
```

## Waarom dit nodig is

Dit helpt om onderscheid te maken tussen:

* totaal geen setup
* zwakke kandidaat
* bijna entry
* harde veto laat in de keten

---

## 4.5 Combo / module detail uitbreiden

## Probleem

Een losse `combo_active_modules_count` is te mager.

## Doel

Per side exact zien welke modules actief waren.

## Nieuwe velden

```json
{
  "modules_long": {
    "structure": false,
    "liquidity": false,
    "trigger": false
  },
  "modules_short": {
    "structure": false,
    "liquidity": false,
    "trigger": false
  },
  "combo_active_modules_count_long": 0,
  "combo_active_modules_count_short": 0
}
```

## Waarom dit nodig is

Dan kun je straks query’s doen zoals:

* “hoe vaak was structure ok maar trigger niet?”
* “komt liquidity ooit door in New York?”
* “is short side altijd dood?”

---

# 5. Nice-to-have uitbreidingen

---

## 5.1 Polling context

```json
{
  "poll_cycle_id": "abc123",
  "poll_interval_seconds": 60,
  "bars_loaded": 500,
  "latest_bar_complete": true
}
```

Dit helpt bij diagnosing:

* polling-frequentie
* incomplete bar reads
* bootstrap/load issues

---

## 5.2 Market state compact

```json
{
  "market_state": {
    "atr_state": "low",
    "range_state": "compressed",
    "session_volatility_state": "normal"
  }
}
```

Niet essentieel, wel nuttig voor latere analytics.

---

## 5.3 Threshold snapshot

```json
{
  "threshold_snapshot": {
    "min_combo_required": 3,
    "min_displacement": 0.25,
    "lookback_bars": 5
  }
}
```

Heel waardevol als je vaak parameters verandert en later wilt weten onder welke settings een run draaide.

---

# 6. Execution lifecycle logging

## Alleen relevant zodra er entries komen

Zodra de bot trades gaat nemen, moeten we ook de execution-kant verrijken.

## Nieuwe events / velden

### order_submitted

```json
{
  "order_ref": "ord_123",
  "side": "buy",
  "symbol": "XAUUSD",
  "size": 0.1,
  "intended_entry": 3245.10,
  "submit_ts": "..."
}
```

### order_acknowledged

```json
{
  "order_ref": "ord_123",
  "broker_ack_ts": "...",
  "ack_latency_ms": 180
}
```

### order_filled

```json
{
  "order_ref": "ord_123",
  "fill_price": 3245.30,
  "fill_ts": "...",
  "slippage_points": 20
}
```

### protection_attached

```json
{
  "order_ref": "ord_123",
  "sl_attached": true,
  "tp_attached": true
}
```

## Waarom dit nodig is

Pas dan kun je echt analyseren:

* execution kwaliteit
* latency
* slippage
* broker gedrag
* protection failures

---

# 7. Eventtypes die minimaal aanwezig moeten zijn in exports

Voor serieuze analyse moeten exports minimaal bevatten:

* `signal_evaluated`
* `trade_action`
* `order_submitted` (indien van toepassing)
* `order_acknowledged`
* `order_filled`
* `position_opened`
* `position_closed`
* `error`

## Belangrijk

Een export met alleen `trade_action` is onvoldoende voor diepe analyse.

---

# 8. Aanbevolen event-structuur per `signal_evaluated`

Dit is het minimale “rijke” eventformaat dat we willen bereiken.

```json
{
  "event_type": "signal_evaluated",
  "timestamp_utc": "...",
  "run_id": "...",
  "session_id": "...",
  "symbol": "XAUUSD",
  "session": "New York",
  "regime": "trend",

  "eval_stage": "no_entry_signal",
  "setup": false,
  "signal_direction": "NONE",

  "new_bar_detected": false,
  "bar_ts": "...",
  "poll_ts": "...",
  "same_bar_guard_triggered": false,
  "same_bar_guard_reason": null,
  "same_bar_skip_count_for_bar": 0,

  "gate_summary": {
    "session_gate": "pass",
    "regime_gate": "pass",
    "structure_gate": "fail",
    "liquidity_gate": "fail",
    "trigger_gate": "fail",
    "same_bar_guard": "pass",
    "risk_gate": "not_reached"
  },

  "blocked_by_primary_gate": "structure_gate",
  "blocked_by_secondary_gate": "trigger_gate",

  "modules_long": {
    "structure": false,
    "liquidity": false,
    "trigger": false
  },
  "modules_short": {
    "structure": false,
    "liquidity": false,
    "trigger": false
  },

  "combo_active_modules_count_long": 0,
  "combo_active_modules_count_short": 0,

  "near_entry_score": 0.12,
  "closest_to_entry_side": "long",
  "entry_distance_long": 3,
  "entry_distance_short": 3,
  "missing_modules_long": ["structure", "liquidity", "trigger"],
  "missing_modules_short": ["structure", "liquidity", "trigger"],

  "setup_candidate": false,
  "candidate_side": null,
  "candidate_strength": 0.0,
  "candidate_reason": "no_viable_candidate",

  "threshold_snapshot": {
    "min_combo_required": 3,
    "lookback_bars": 5
  }
}
```

---

# 9. Prioriteitenvolgorde

## Fase 1 — direct bouwen

De hoogste ROI toevoegingen:

1. `same_bar_guard_reason`
2. `new_bar_detected`
3. `same_bar_skip_count_for_bar`
4. `gate_summary`
5. `blocked_by_primary_gate`
6. `active_modules_count_long/short`
7. `missing_modules_long/short`
8. `near_entry_score`

## Fase 2 — daarna

9. `setup_candidate`
10. `candidate_reason`
11. `threshold_snapshot`

## Fase 3 — pas bij entries

12. execution lifecycle logging

---

# 10. Waarom deze upgrade zo belangrijk is

Op dit moment weet je al:

* de bot doet weinig
* same-bar guard is dominant
* echte evaluaties leveren geen setup op

Maar na deze upgrade weet je ook:

* **waarom**
* **welke gate eerst doodloopt**
* **of er bijna-trades bestaan**
* **of je thresholds te streng zijn**
* **of de strategie conceptueel leeft**

Dat is het verschil tussen:

* “de bot deed niks”
  en
* “de liquidity gate faalt 82% van de near-entry gevallen in New York trend-regime”

Dat tweede is desk-grade informatie.

---

# 11. Acceptance criteria

Deze upgrade is geslaagd als we na een run kunnen antwoorden op:

1. Waarom werd same-bar guard geactiveerd?
2. Welke gate blokkeerde als eerste?
3. Welke modules waren actief per side?
4. Hoe dicht waren we bij entry?
5. Waren er near-miss situaties?
6. Is de strategie te streng of gewoon niet actief in deze markt?
7. Als er een trade kwam: hoe verliep execution?

---

# 12. Definitie van succes

Succes is niet:

* meer logs
* meer JSON
* meer ruis

Succes is:

> elke no-trade dag kunnen terugbrengen tot een concrete strategische diagnose

---

# 13. Mentor conclusie

De huidige logging is al goed genoeg om te zien dat het systeem zichzelf inhoudelijk blokkeert.

De volgende upgrade moet niet breder worden.

Hij moet **scherper** worden.

Focus dus op:

* same-bar mechaniek
* veto chain
* near-miss structuur

Dat zijn de drie upgrades die je van “goede observability” naar “echte strategie-analyse” brengen.

---

# Bestandsnaam

Aanbevolen naam:

`docs/QUANTBUILD_LOGGING_UPGRADE_DATA_COLLECTION.md`
