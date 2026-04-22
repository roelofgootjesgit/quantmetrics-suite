# Quant research log — Q1 2026 regime A/B (vastgelegd)

**Venster (UTC):** 2026-01-01 — 2026-03-31  
**Symbol / TF:** XAUUSD 15m (+ 1h data volgens parent-config)  
**Datum runs:** 2026-04-22 (lokale machine)

Doel: productie-varianten **apples-to-apples** vergelijken + één **EDGE_DISCOVERY**-run als **throughput-plafond** (niet hetzelfde als production edge).

---

## 1. Configs

| Label | Config-bestand | `system_mode` | Hypothese |
|-------|------------------|---------------|-----------|
| Baseline | `configs/backtest_2026_jan_mar.yaml` | PRODUCTION | referentie strict_prod_v2 |
| Expansion-only | `configs/backtest_2026_jan_mar_expansion_only.yaml` | PRODUCTION | `trend.skip: true` |
| Expansion + NY | `configs/backtest_2026_jan_mar_expansion_ny.yaml` | PRODUCTION | trend uit + expansion `allowed_sessions: [New York]`, `min_hour_utc` uit |
| Research ceiling | `configs/backtest_2026_jan_mar_edge_discovery.yaml` | EDGE_DISCOVERY | zelfde venster; regime/session/H1/news/cooldown/position uit per policy — **bovengrens**, geen production-strategie |

Zie ook: `docs/PARALLEL_BACKTEST_AB.md`, `quantmetrics_os/docs/STRATEGY_EXPLOIT_ROADMAP.md`.

---

## 2. Engine-samenvatting (backtest-log)

| Label | Trades | net_pnl | pf | wr | dd | `run_id` |
|-------|--------|---------|-----|-----|-----|----------|
| Expansion + NY (prod) | 8 | 48.47 | 2.00 | 50.0% | -2.00R | `qb_run_20260422T195532Z_ac8f549c` |
| Research ceiling | 110 | 371.45 | 1.45 | 26.4% | -10.00R | `qb_run_20260422T195553Z_042ce3fe` |

**Eerder (zelfde codebasis, zelfde venster, productie):**

| Label | Trades | net_pnl | pf | wr | dd |
|-------|--------|---------|-----|-----|-----|
| Baseline | 11 | -113.31 | 0.20 | 9.1% | -10.00R |
| Expansion-only | 8 | 48.47 | 2.00 | 50.0% | -2.00R |

### Observatie expansion + NY vs expansion-only

In deze Q1-run zijn **Expansion-only** en **Expansion + NY** numeriek **identiek** (8 trades, zelfde PnL/PF/WR). Interpretatie: alle uitgevoerde expansion-trades vielen al in de **New York**-session; de extra session-knip veranderde hier niets. Blijft nuttig als **vaste productieregel** voor live.

---

## 3. QuantAnalytics (`run_id`-gefilterd)

### Expansion + NY — `qb_run_20260422T195532Z_ac8f549c`

Rapport: `quantanalyticsv1/output_rapport/quantlog_events_20260422_195543Z.txt`  
KEY_FINDINGS: `quantlog_events_20260422_195543Z_KEY_FINDINGS.md`

Uit KEY_FINDINGS (samenvatting):

- **Closed-trade expectancy (overall):** mean_r = **0.500**, n = **8**
- **Exit efficiency (median capture vs |MFE|):** ~**92%**
- **Regime-slice:** expansion mean_r = **0.500**, n = **8**
- **Funnel:** detected = **133**, evaluated = **133**, ENTER/REVERSE = **8**
- **GUARD_DOMINANCE (MEDIUM):** `regime_profile` ≈ **90%** van BLOCKs (113/125); `regime_allowed_sessions` 10 BLOCKs
- Interpretatie: na trend-isolatie blijft **regime_profile** (o.a. compression vs expansion bucket + skip-logica in logging) de dominante bottleneck op het **evaluatie-/guard-pad** — vervolgstap: guard-deconstructie (zie exploit roadmap).

### Research ceiling — `qb_run_20260422T195553Z_042ce3fe`

Rapport: `quantlog_events_20260422_195601Z.txt`  
KEY_FINDINGS: `quantlog_events_20260422_195601Z_KEY_FINDINGS.md`

- **Overall:** mean_r ≈ **0.164**, n = **110**
- **Funnel:** detected **155** → ENTER/REVERSE **110** (veel hogere doorvoer)
- **Blocks:** vooral `daily_loss_cap` (98%) — ander gedrag dan production (verwacht bij EDGE_DISCOVERY)
- **Belangrijk:** regime-slices in deze run zijn **niet** vergelijkbaar met “expansion-only production”: alle regimes traden mee; gebruik dit alleen als **plafond** / stress-test, niet als PnL-doel.

---

## 4. Commando’s (reproduceren)

```text
python -m src.quantbuild.app --config configs/backtest_2026_jan_mar.yaml backtest
python -m src.quantbuild.app --config configs/backtest_2026_jan_mar_expansion_only.yaml backtest
python -m src.quantbuild.app --config configs/backtest_2026_jan_mar_expansion_ny.yaml backtest
python -m src.quantbuild.app --config configs/backtest_2026_jan_mar_edge_discovery.yaml backtest
```

QuantAnalytics handmatig met zelfde `run_id` als in de log:

```text
python -m quantmetrics_analytics.cli.run_analysis --dir <quantlog_base> --run-id <run_id> --reports all
```

---

## 5. Vast te houden conclusie (desk)

- **Production:** trend uit → **expectancy-sign** verbetert sterk t.o.v. baseline in dit venster; expansion-trades tonen **positieve mean R** en gezonde exit-capture in analytics.
- **Throughput:** veel meer **signal_evaluated** dan **fills** → volgende onderzoeksstap is **waarom** (guard-blokken; cijfers staan in KEY_FINDINGS).
- **Research ceiling:** aparte modus om **maximale** trade-frequentie te zien — niet verwarren met production KPI’s.
