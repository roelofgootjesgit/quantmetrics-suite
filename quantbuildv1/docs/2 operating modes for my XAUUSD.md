# Twee operating modes voor XAUUSD (SQE)

Dit document beschrijft twee expliciete systeemmodi voor het SQE / XAUUSD‑spoor binnen QuantBuild: **edge‑ontdekking** (research) en **productie** (bescherming). De modus staat centraal in configuratie als `system_mode`, met één resolver in `src/quantbuild/policy/system_mode.py` (geen verspreide ad‑hoc checks).

---

## 1. Probleem

- Backtests leveren vaak signaalkandidaten; live/demo kan bijna leeg blijven door regime/sessie/cooldown/risk‑gating.
- **Edge‑ontdekking** en **productie‑bescherming** moeten van elkaar te scheiden zijn voor metingen en voor strikte live‑policy.

---

## 2. De twee modi

| Modus | Doel |
|--------|------|
| `EDGE_DISCOVERY` | Meer throughput om ruwe expectancy te meten; niet‑essentiële blockers uit; besliscontext blijft logbaar. |
| `PRODUCTION` | Strikte live‑policy: regime/sessie/cooldown e.d. aan; conservatief voor deployment. |

### 2.1 `EDGE_DISCOVERY`

- Hogere tradefrequentie voor statistiek (gecontroleerd, geen “permanent wild” profiel).
- Standaardmapping in code: zie onder **Standaard `filters:` per modus**.
- **Dagelijks verlies‑cap** (`daily_loss`) en **spread‑guard** blijven standaard aan; **equity kill switch** in de backtest blijft altijd actief (catastrofaal).
- Live gebruikt **`research_raw_first` standaard aan** in deze modus: SQE wordt geëvalueerd vóór regime/sessie‑blokken (zelfde als expliciet `filters.research_raw_first: true`).

### 2.2 `PRODUCTION`

- Alle policy‑lagen volgens de onderstaande defaults, tenzij je per sleutel overschrijft in `filters:`.

---

## 3. Configuratie

### 3.1 Topniveau

```yaml
system_mode: PRODUCTION    # PRODUCTION | EDGE_DISCOVERY
```

Staat ook in `configs/default.yaml` (default `PRODUCTION`).

### 3.2 Optionele overrides

Alles wat je onder `filters:` zet **wint** van de modus‑default (handig om één laag tijdelijk te testen):

| Sleutel | Betekenis |
|---------|-----------|
| `regime` | Regime‑profiel `skip` + gerelateerde blokken in backtest |
| `session` | Sessietijd / allowed_sessions / min/max uur (backtest + live) |
| `cooldown` | Zelfde bar opnieuw verwerken blokkeren (live) |
| `news` | NewsGate blok |
| `position_limit` | Max open posities (live) / max trades per sessie (backtest) |
| `daily_loss` | Dagelijks verlies‑plafond |
| `spread` | Spread‑guard (live) |
| `research_raw_first` | SQE vóór regime‑poort (live); default `false` in PRODUCTION, `true` in EDGE_DISCOVERY |
| `structure_h1_gate` | M15‑entries alignen met 1h‑structuur (`_apply_h1_gate` in backtest); alleen backtest; default `true` in PRODUCTION, `false` in EDGE_DISCOVERY |

Resolver: `resolve_effective_filters(cfg)` in `src/quantbuild/policy/system_mode.py`.

### 3.3 Standaard `filters:` per modus

| Sleutel | PRODUCTION | EDGE_DISCOVERY |
|---------|------------|----------------|
| regime | true | false |
| session | true | false |
| cooldown | true | false |
| news | true | false |
| position_limit | true | false |
| daily_loss | true | true |
| spread | true | true |
| research_raw_first | false | true |
| structure_h1_gate | true | false |

---

## 4. Waar het landt

- **Live**: `LiveRunner` leest de effectieve filters na resolutie; startup log: `LiveRunner system_mode=... effective_filters=...`.
- **Backtest**: `run_backtest` past dezelfde sleutels toe op H1‑structure gate (indien actief), regime/sessieprefilter, regime‑profielblokken, positielimiet per sessie, NewsGate en dagelijks verlies‑cap. Equity kill switch blijft altijd aan.
- **QuantLog**: `trade_action.payload` en `decision_context` bevatten `system_mode` waar van toepassing.

---

## 5. Logging

- **`system_mode`** staat op relevante events (o.a. live `trade_action`, backtest start/complete/ENTER).
- Diepgaande bypass‑reason strings (`regime_bypassed_edge_discovery`, …) zijn optioneel uitbreidbaar; het gedrag staat nu via **uitgeschakelde filters** en expliciete `system_mode` vast.

---

## 6. Snel testen

### Backtest — edge overlay op strict prod

```text
python -m src.quantbuild.app backtest --config configs/system_mode_edge_discovery.yaml
```

`configs/system_mode_edge_discovery.yaml` doet `extends: strict_prod_v2.yaml` en zet alleen `system_mode: EDGE_DISCOVERY`.

Zelf vergelijken met productie‑profiel:

```text
python -m src.quantbuild.app backtest --config configs/strict_prod_v2.yaml
```

### Tests in de repo

```text
pytest tests/test_system_mode.py tests/test_backtest.py
```

`TestSystemModeBacktest` toont hetzelfde gemockte signaal onder `regime_profiles.expansion.skip: true`: **0 trades in PRODUCTION**, **≥1 trade in EDGE_DISCOVERY**.

---

## 7. Risico’s

| Risico | Mitigatie |
|--------|-----------|
| Te veel trades / DD in discovery | Alleen demo/paper of klein risico; production account: `system_mode: PRODUCTION`. |
| Onduidelijk welke modus draait | Startup‑log + `system_mode` op events. |

---

## 8. Zie ook

- `docs/SYSTEM_MODES_EDGE_DISCOVERY_VS_PRODUCTION.md` — compacte operator‑versie.
