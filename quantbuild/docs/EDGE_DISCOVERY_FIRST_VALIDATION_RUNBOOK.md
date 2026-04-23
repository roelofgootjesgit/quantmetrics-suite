# EDGE_DISCOVERY_FIRST_VALIDATION_RUNBOOK

## QuantBuild — Eerste validatieronde voor EDGE_DISCOVERY vs PRODUCTION

---

## 1. Doel

Dit runbook is bedoeld om de eerste echte validatie uit te voeren nadat het systeem is opgesplitst in:

- `PRODUCTION`
- `EDGE_DISCOVERY`

(zie ook `system_mode` in YAML en `src/quantbuild/policy/system_mode.py`)

Het doel is **niet** om meteen winst te bewijzen.

Het doel is om te bewijzen:

1. dat `EDGE_DISCOVERY` daadwerkelijk meer signal-throughput geeft dan `PRODUCTION`
2. dat de signal engine in live/demo eindelijk trades kan produceren
3. dat we guard-impact en signal-edge van elkaar kunnen scheiden
4. dat backtest en live zich in dezelfde richting gedragen zodra suppressie wordt verlaagd

---

## 2. Belangrijkste vraag van deze fase

De kernvraag is:

> **Leeft de signal engine echt, zodra we niet-essentiële blokkades verlagen?**

Nog niet:

- is de strategy definitief production-ready
- is de risk-engine optimaal
- is expectancy al stabiel

Deze fase gaat puur om:

```text
throughput → observable behavior → eerste edge-validatie
```

---

## 3. Modes

### 3.1 PRODUCTION

Conservatieve mode met bestaande beschermlagen actief:

- regime filter aan
- session filter aan
- cooldown aan
- position limit aan
- news gating aan
- daily loss cap aan
- spread bescherming aan

Doel:

- baseline / reference mode

(Config: `system_mode: PRODUCTION` — default in `configs/default.yaml`; referentie-backtest bijv. `configs/strict_prod_v2.yaml`.)

### 3.2 EDGE_DISCOVERY

Research mode met hogere throughput:

- regime filter uit of bypassed
- session filter uit of bypassed
- cooldown uit of sterk gereduceerd
- position limit losser of bypassed
- daily loss cap blijft aan
- spread bescherming blijft aan
- catastrophic protection blijft aan (o.a. equity kill switch in backtest)

Doel:

- signal edge isoleren
- trade volume creëren
- guard-impact zichtbaar maken

(Config: bijv. `configs/system_mode_edge_discovery.yaml`, die `extends: strict_prod_v2.yaml` gebruikt.)

---

## 4. Wat we in deze ronde willen bewijzen

Deze validatie is geslaagd als we minimaal één van deze drie dingen aantonen:

### A.

`EDGE_DISCOVERY` produceert significant meer trades dan `PRODUCTION`

### B.

Live/demo in `EDGE_DISCOVERY` produceert echte `ENTER` events

### C.

De dominante blockers verschuiven van:

- regime/session/cooldown  
  naar:
- echte strategy- of risk-blockers

---

## 5. Run matrix

Voer deze runs uit.

### Run 1 — Backtest PRODUCTION

```bash
python -m src.quantbuild.app backtest --config configs/strict_prod_v2.yaml
```

Doel:

- baseline
- huidige conservatieve output meten

### Run 2 — Backtest EDGE_DISCOVERY

```bash
python -m src.quantbuild.app backtest --config configs/system_mode_edge_discovery.yaml
```

Doel:

- throughput delta meten
- zien wat guards echt onderdrukken

### Run 3 — Live/Demo PRODUCTION (optioneel als referentie)

Gebruik bestaande production-achtige live/demo setup (`system_mode: PRODUCTION` of equivalente strikte `filters:`).

Doel:

- vergelijkbaar referentiepunt houden

### Run 4 — Live/Demo EDGE_DISCOVERY

Gebruik edge discovery op demo-account, bijvoorbeeld door in je live YAML:

```yaml
system_mode: EDGE_DISCOVERY
```

(of een config die alleen deze overlay toevoegt naast je broker-/data-instellingen)

Doel:

- testen of de signal engine nu echte live entries produceert

---

## 6. Metrics die je altijd moet verzamelen

Voor elke run dezelfde metrics verzamelen.

### 6.1 Run metadata

- datum
- mode (`PRODUCTION` of `EDGE_DISCOVERY`)
- symbol
- timeframe
- environment (`dry_run`, `demo`, `live`)
- config file
- `run_id` (QuantLog)

### 6.2 Signal funnel

Verzamelen:

- total `signal_evaluated`
- total `signal_detected`
- total `trade_action`
- total `ENTER`
- total `NO_ACTION`

Afgeleide ratio’s:

- `signal_evaluated → ENTER`
- `signal_detected → ENTER`
- `trade_action → ENTER`

### 6.3 Blocker distribution

Verzamelen top reason codes (QuantLog-canonical waar van toepassing):

- `regime_blocked`
- `session_blocked`
- `cooldown_active`
- `risk_blocked`
- `position_limit_reached`
- `no_setup`
- andere relevante reasons

Doel:

- zien wat dominant is per mode

### 6.4 Guard distribution

Verzamelen `risk_guard_decision` per guard:

- `guard_name`
- decision (`ALLOW`, `BLOCK`)
- reason

Specifiek tellen:

- hoeveel `BLOCK`
- hoeveel `ALLOW`
- welke guard blokkeert het meest

### 6.5 Session / regime mix

Verzamelen voor `trade_action` en `signal_detected`:

- session-verdeling
- regime-verdeling

Doel:

- zien of `EDGE_DISCOVERY` vooral nieuwe trades geeft in Asia / London / NY
- zien in welke regime-contexts het systeem eindelijk iets doet

### 6.6 Strategy module activity

Voor `signal_detected`-events (payload/modules):

- trend / liquidity / trigger / structure signalen waar beschikbaar
- `combo_active_modules_count` of equivalent uit je decision context

Doel:

- zien of de strategie überhaupt leeft
- vergelijken of module-activiteit verschilt tussen backtest en live

### 6.7 Trade outcome metrics

Alleen als `ENTER` > 0.

Verzamelen:

- aantal trades
- winrate
- avg R
- expectancy
- PF
- max DD
- MAE/MFE indien beschikbaar

---

## 7. Vergelijkingsformat

Gebruik voor elke run een compacte tabel.

### 7.1 Run summary tabel

| Metric            | PRODUCTION | EDGE_DISCOVERY |
| ----------------- | ---------: | -------------: |
| signal_evaluated  |          x |              y |
| signal_detected   |          x |              y |
| trade_action      |          x |              y |
| ENTER             |          x |              y |
| NO_ACTION         |          x |              y |
| Enter rate        |         x% |             y% |

### 7.2 Blocker tabel

| Reason            | PRODUCTION | EDGE_DISCOVERY |
| ----------------- | ---------: | -------------: |
| regime_blocked    |          x |              y |
| session_blocked   |          x |              y |
| cooldown_active   |          x |              y |
| risk_blocked      |          x |              y |
| no_setup          |          x |              y |

### 7.3 Guard tabel

| Guard                    | PRODUCTION BLOCK | EDGE_DISCOVERY BLOCK |
| ------------------------ | ---------------: | -------------------: |
| regime_profile           |                x |                    y |
| regime_allowed_sessions  |                x |                    y |
| daily_loss_cap           |                x |                    y |
| max_trades_per_session   |                x |                    y |

---

## 8. Verwachte uitkomst per mode

### 8.1 Wat je verwacht in PRODUCTION

- lage trade count
- veel blockers
- lage enter rate
- conservatief profiel

Dit is normaal.

### 8.2 Wat je verwacht in EDGE_DISCOVERY

- hogere trade count
- veel minder regime/session/cooldown blockers
- hogere enter rate
- mogelijk meer `signal_detected`
- nog steeds catastrophic protection actief waar geconfigureerd

Dit is gewenst.

---

## 9. Hoe je de resultaten interpreteert

### Scenario A — EDGE_DISCOVERY geeft duidelijk meer trades

#### Interpretatie

Goed nieuws.

Dit betekent:

- signal engine leeft
- suppressie kwam grotendeels van guards
- volgende stap = expectancy meten

#### Besluit

Ga door met:

- live/demo `EDGE_DISCOVERY`
- trade outcome analysis
- daarna guard reintroduction

---

### Scenario B — EDGE_DISCOVERY geeft nog steeds bijna 0 trades

#### Interpretatie

Dan ligt het probleem dieper:

- signal engine ziet echt weinig setups
- of live/backtest logica nog niet aligned
- of data mismatch blijft groot

#### Besluit

Terug naar:

- alignment debug
- module-level compare
- near-miss logging uitbreiden

---

### Scenario C — EDGE_DISCOVERY geeft veel trades, maar slechte expectancy

#### Interpretatie

Goed nieuws én slecht nieuws.

Goed:

- system throughput werkt
- logging is bruikbaar

Slecht:

- raw signal edge is zwak

#### Besluit

Dan pas:

- filters terugbrengen
- regime gating slim herintroduceren
- risk tuning doen

---

### Scenario D — Backtest EDGE_DISCOVERY goed, live EDGE_DISCOVERY nog steeds dood

#### Interpretatie

Zeer belangrijke uitkomst.

Dan heb je nog steeds:

```text
backtest logic ≠ live logic
```

#### Besluit

Focus volledig op:

- live/backtest alignment
- data source mismatch
- candle/session/regime equivalence

---

## 10. Beslisregels na deze validatieronde

Gebruik deze beslisboom.

### Beslisregel 1

Als `EDGE_DISCOVERY ENTER >> PRODUCTION ENTER`

→ Guard suppressie is een hoofdprobleem

### Beslisregel 2

Als `EDGE_DISCOVERY live ENTER > 0`

→ Live engine leeft eindelijk → start trade quality analyse

### Beslisregel 3

Als `EDGE_DISCOVERY live ENTER = 0` maar backtest heeft wel veel enters

→ Alignment probleem prioriteit 1

### Beslisregel 4

Als enter count hoog genoeg is maar expectancy negatief

→ Raw signal edge zwak → filters daarna slim inzetten

---

## 11. Praktisch werkformat per run

Gebruik dit template na elke run.

### Run Review Template

#### Metadata

- Date:
- Mode:
- Config:
- Environment:
- Run ID:

#### Signal Funnel

- signal_evaluated:
- signal_detected:
- trade_action:
- ENTER:
- NO_ACTION:
- Enter rate:

#### Top Blockers

1.  
2.  
3.  

#### Top Blocking Guards

1.  
2.  
3.  

#### Sessions / Regimes

- Dominant session:
- Dominant regime:

#### Strategy Activity

- trend / structure / liquidity / trigger frequency (naar wat je uit logs haalt):
- combo count distribution:

#### Outcome

- trades:
- expectancy:
- PF:
- DD:

#### Conclusion

- Does signal engine live?
- Are guards too suppressive?
- Is alignment still suspect?
- What is the next action?

---

## 12. Wat je NIET moet doen in deze fase

Niet doen:

- direct terug naar production conclusions
- random thresholds aanpassen zonder data
- teveel tegelijk tunen
- risk model optimaliseren voordat throughput bewezen is
- edge claims maken op basis van 0–5 trades

---

## 13. Belangrijkste discipline

Deze fase vraagt een andere mindset.

Niet:

> “alleen de beste trades”

Maar:

> “genoeg observaties verzamelen om de waarheid te zien”

---

## 14. Definitie van succes voor deze ronde

Deze validatieronde is succesvol als we aan het eind kunnen zeggen:

1. hoeveel suppressie guards veroorzaken
2. of `EDGE_DISCOVERY` live echte enters produceert
3. of backtest en live in dezelfde richting bewegen
4. of de signal engine op zichzelf edge-potentieel heeft
5. wat de volgende bottleneck is

---

## 15. Mentor conclusie

Dit runbook is de brug tussen:

- mooie architectuur  
  en  
- echte trading research

Zonder deze stap blijf je hangen in theorie.

Met deze stap kun je eindelijk objectief zien:

- of je signal engine leeft
- of je guards de edge doden
- of je alignment nog stuk is
- of je volgende stap strategy tuning of alignment debugging moet zijn

---

## Zie ook

- `docs/2 operating modes for my XAUUSD.md`
- `docs/SYSTEM_MODES_EDGE_DISCOVERY_VS_PRODUCTION.md`
