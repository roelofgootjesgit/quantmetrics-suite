# Nieuwe strategieën implementeren in QuantBuild

Dit document beschrijft hoe je een strategie toevoegt, hoe QuantBuild daarvoor is ingericht (meerdere engines), en hoe je **run → QuantLog → QuantAnalytics** end-to-end gebruikt. Research-registratie in `quantresearch` blijft een aparte governance-laag; hier gaat het om uitvoerbare code en reproduceerbare runs.

---

## Pipeline in het kort

```text
YAML config → run_backtest() → trades + QuantLog JSONL → (auto) QuantAnalytics rapporten
```

1. **Run** — `python -m src.quantbuild.app --config <pad>.yaml backtest` laadt `configs/default.yaml`, merge’t jouw config, en start de gekozen backtest-engine.
2. **Log** — als `quantlog.enabled: true`, schrijft de engine events onder `quantlog.base_path` (default `data/quantlog_events`), met een vaste **`run_id`** per run.
3. **Analyze** — als `quantlog.auto_analytics: true` en QuantAnalytics in dezelfde Python-env beschikbaar is, draait na afloop een CLI met `--run-id <run_id>` zodat rapporten onder `quantanalytics/output_rapport/` terechtkomen.

Zonder matching QuantLog-events (zelfde `run_id`) zie je: `kept 0/... events` en geen zinvolle rapporten.

---

## Welke “strategie-mogelijkheden” QuantBuild heeft

Er zijn grofweg **drie** manieren om signalen te definiëren; kies bewust — niet alles hoeft via SQE.

### 1. SQE-stack (default)

- Config: `strategy:` met modules (`liquidity_sweep`, `fair_value_gaps`, `displacement`, …) zoals in `configs/xauusd.yaml` / `strict_prod_v2.yaml`.
- Entry-logica: `run_sqe_conditions` in `src/quantbuild/strategies/sqe_xauusd.py` + `backtest/engine.py`.
- Geschikt voor: itereren op bestaande ICT-modules en regime/session/news als policy-laag.

### 2. Dedicated backtest-engine

- Config: `backtest.engine: <naam>` — de engine vertakt **vóór** SQE-signaalgeneratie (zie `run_backtest` in `src/quantbuild/backtest/engine.py`).
- Voorbeeld: **`ny_sweep_reversion`** — volledige implementatie in `src/quantbuild/strategies/ny_sweep_reversion_engine.py`, research-YAML via `backtest.ny_sweep_reversion_config` (pad relatief aan **`QUANTMETRICS_SUITE_ROOT`**).
- Geschikt voor: sessie-exacte regels (London/NY UTC), eigen FVG/fill-logica, prijs-SL i.p.v. alleen ATR×R.

### 3. Eigen script / orchestratie

- Backtest aanroepen vanuit `quantbuild/scripts/` met `load_config` + `run_backtest`, of alleen `run_backtest` met een gegenereerde config-dict.
- Geschikt voor: experiment batches, A/B, parameter sweeps.

Live-trading volgt een ander pad (`LiveRunner`); deze guide focust op **backtest + logs + analytics**.

---

## Config-contract voor een dedicated engine

Minimaal in je QuantBuild-YAML:

```yaml
symbol: XAUUSD
timeframes: [15m, 1h]

data:
  base_path: data/market_cache

backtest:
  engine: ny_sweep_reversion
  default_period_days: 365
  ny_sweep_reversion_config: configs/experiments/ny_sweep_reversion/A0_raw_setup.yaml

strategy:
  name: ny_sweep_reversion   # vermijdt “lege strategy” waarschuwing; niet verplicht voor routing

quantlog:
  enabled: true
  auto_analytics: true
```

**Suite-layout:** staat je research-YAML onder de suite-root (`configs/experiments/...`), zet dan:

```powershell
$env:QUANTMETRICS_SUITE_ROOT = "C:\path\to\quantmetrics-suite"
```

Anders kan `ny_sweep_reversion_config` niet worden gevonden.

---

## Stappen: nieuwe dedicated engine toevoegen

1. **Spec** — YAML-schema afspreken (sessions, setup, risk, …). Kan onder `configs/experiments/<strategy>/` met `extends` zoals bij NY Sweep.

2. **Signalen + simulator** — nieuwe module onder `src/quantbuild/strategies/<jouw_engine>.py`:
   - functie die entry-candidates teruggeeft (index, richting, entry/sl/tp prijzen);
   - gebruik bestaande `load_parquet`, `compute_atr`, policy `resolve_effective_filters` waar het kan.

3. **Prijs-gebaseerde exits** — gebruik `_simulate_trade_price_levels` in `backtest/engine.py` (vaste SL/TP in prijs) of breid de simulator uit als je partiels/BE nodig hebt.

4. **Routing** — in `run_backtest` na data + regime:

   ```python
   if str((cfg.get("backtest") or {}).get("engine", "")).lower() == "jouw_engine":
       from src.quantbuild.strategies.jouw_engine import run_jouw_backtest
       return run_jouw_backtest(cfg, data, start, end, base_path, symbol, tf, regime_series)
   ```

5. **QuantLog-pariteit** — per uitgevoerde trade minimaal dezelfde keten als SQE waar analytics op steunt:
   - `signal_detected`, `signal_evaluated`
   - `risk_guard_decision` (ALLOW)
   - `trade_action` (ENTER), `order_submitted`, `order_filled`, `trade_executed`, `trade_closed`

   Gebruik `build_signal_evaluated_payload` + `assert_signal_evaluated_payload_complete` voor `signal_evaluated`. Zie `ny_sweep_reversion_engine.py` als referentie.

6. **Runnable preset** — YAML onder `quantbuild/configs/...` met `backtest.engine` en eventueel documentatielink naar de research-config.

---

## Run → log → analyze (concreet)

### Backtest draaien

```powershell
cd quantbuild
$env:QUANTMETRICS_SUITE_ROOT = "C:\path\to\quantmetrics-suite"
python -m src.quantbuild.app --config configs/experiments/ny_sweep_reversion/A0_dedicated_engine.yaml backtest --days 365
```

Logregel met **`run_id`** (bijv. `qb_run_...`) kun je gebruiken voor gefilterde analytics.

### QuantLog controleren

- Map: `quantbuild/data/quantlog_events` (of jouw `quantlog.base_path`).
- Events moeten bij dezelfde `run_id` horen als in de logregel (emitter zet dit automatisch op emits).

### QuantAnalytics

- Automatisch als `quantlog.auto_analytics: true` en `quantmetrics_analytics` importeerbaar is.
- Handmatig (indien nodig), vanuit suite met dezelfde `run_id`:

  ```text
  python -m quantmetrics_analytics.cli.run_analysis --dir <quantlog_base_path> --run-id <run_id> --reports all
  ```

- Output: typisch `../quantanalytics/output_rapport/` naast `quantbuild`, tenzij `QUANTMETRICS_ANALYTICS_OUTPUT_DIR` gezet is.

Zet `QUANTMETRICS_ANALYTICS_AUTO=0` om auto-run uit te zetten.

---

## Referentie-implementatie: NY Sweep Reversion

| Onderdeel | Locatie |
|-----------|---------|
| Engine | `src/quantbuild/strategies/ny_sweep_reversion_engine.py` |
| Routing | `backtest/engine.py` (`engine == ny_sweep_reversion`) |
| Research specs | `configs/experiments/ny_sweep_reversion/*.yaml` (suite-root) |
| QuantBuild preset | `quantbuild/configs/experiments/ny_sweep_reversion/A0_dedicated_engine.yaml` |

**`risk.max_trades_per_day` (default 2):** harde bovengrens per **UTC-kalenderdag** — 0, 1 of 2 trades afhankelijk van hoeveel geaccepteerde setups die dag overlappen met sequentiële uitvoering. Er is **geen “minimaal 1 trade per dag”** in de risk-config: op dagen zonder geldige setup blijft het 0. Na een run toont de engine-log regels als `skipped: … daily_cap=N` wanneer ruwe signalen door de dag-cap vallen.

---

## Troubleshooting

| Symptoom | Oplossing |
|----------|-----------|
| `NY sweep spec YAML not found` | `QUANTMETRICS_SUITE_ROOT` zetten; pad `ny_sweep_reversion_config` relatief aan suite-root. |
| `kept 0/... events` in QuantAnalytics | Geen emits voor deze run, of verkeerde `--dir` / `run_id`. Dedicated engine: QuantLog-keten per trade implementeren. |
| Suite preflight / layout errors | `QUANTMETRICS_SUITE_ROOT` wijst naar de map die **zowel** `quantbuild` als `configs` bevat. |

---

## Volgende laag: quantresearch

Experimenten registreren, varianten vergelijken en beslissingen vastleggen gaat via `quantresearch` (registry, vergelijkingen, knowledge files). Dat is optioneel voor een eerste werkende engine, maar nodig voor governance en reproduceerbaarheid op portfolio-niveau.
