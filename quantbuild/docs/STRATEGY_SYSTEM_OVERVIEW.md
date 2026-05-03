# Overzicht: strategie-opzet QuantMetrics / QuantBuild (team)

Doel van dit document: één gedeelde waarheid voor **hoe strategie nu werkt in code**, waar **NY Sweep** past, en **welke hendels** de hoeveelheid trades bepalen — zodat jullie kunnen overleggen over “meer trades” zonder verkeerde aannames.

---

## 1. Plaats in de suite (hoog niveau)

| Laag | Rol |
|------|-----|
| **QuantBuild** | Data laden, backtest, optioneel **live**; configs in YAML. |
| **QuantLog** | JSONL events per run (`run_id`); basis voor traceerbaarheid. |
| **QuantAnalytics** | Rapporten / funnels op basis van QuantLog (vaak auto na backtest). |
| **quantresearch** (apart) | Experimenten registreren, vergelijken, besluitvorming — niet verplicht voor elke backtest. |

**Typische flow:** `config` → `backtest` → **trades** + **QuantLog** → (optioneel) **QuantAnalytics**.

### Run-artifacts (canonieke map)

Na een backtest kun je alles bundelen onder **`quantmetrics_os/runs/<experiment_id>/<role>/`** (QuantOS `collect_run_artifact.py`), door in de QuantBuild-config:

- `quantlog.consolidated_run_file: true` (één `runs/<run_id>.jsonl` in QuantBuild),
- `artifacts.enabled: true`,
- `artifacts.experiment_id` (mapnaam onder `quantmetrics_os/runs/`),
- optioneel `artifacts.role`: `single` | `baseline` | `variant`.

Daar landen o.a. `quantlog_events.jsonl`, `config_snapshot.yaml`, `resolved_config.yaml` (indien aanwezig), `run_info.json`, en onder `analytics/` de recente QuantAnalytics `.txt` / `.md` exports. Zet **`QUANTMETRICS_OS_ROOT`** als `quantmetrics_os` niet als directe sibling van `quantbuild` staat.

*(Optioneel: `quantresearch_runs` in QuantBuild kopieert naar `quantresearch/runs/` — alleen aan als je dat expliciet wilt; standaard team-output is **`quantmetrics_os/runs`**.)*

---

## 2. Twee manieren om te backtesten (belangrijk)

### A. Standaard: **SQE (Strategy / ICT-modules)**

- **Config:** `strategy:` met modules zoals `liquidity_sweep`, `fair_value_gaps`, `displacement`, `market_structure_shift`, plus `entry_require_sweep_displacement_fvg` e.d.
- **Code:** `run_sqe_conditions` + `_compute_modules_once` in `strategies/sqe_xauusd.py`, aangestuurd vanuit `backtest/engine.py`.
- **Exit-simulatie:** ATR × R (`tp_r` / `sl_r`) — geen vaste prijs-SL op “sweep extreme” in dezelfde zin als de research-NY-spec.
- **Gebruik:** productie-achtige iteraties op bestaande modules; grote history; vergelijking met oudere runs.

### B. **Dedicated: NY Sweep Reversion engine**

- **Config-schakelaar:** `backtest.engine: ny_sweep_reversion`
- **Research-spec (suite):** pad via `backtest.ny_sweep_reversion_config` (relatief t.o.v. `QUANTMETRICS_SUITE_ROOT`), bijv. `configs/experiments/ny_sweep_reversion/A0_high_sample.yaml` (merged YAML met `extends`).
- **Code:** `strategies/ny_sweep_reversion_engine.py` — **niet** dezelfde signaallogica als SQE; die volgt o.a. London high/low (UTC), sweep → displacement → FVG, limit op FVG-mid, SL op sweep-extreme ± buffer, TP volgens `take_profit` in de spec.
- **Exit-simulatie:** vaste **prijs**-SL/TP via `_simulate_trade_price_levels` (R-multiple t.o.v. risico in prijs).
- **Gebruik:** testen van de **hypothese** zoals in jullie research-YAML; vergelijk **niet** één-op-één met SQE-zonder-toelichting.

**Proxy-run (alleen ter referentie):** `A0_base_run.yaml` in QuantBuild mapte A0-intentie naar SQE — dat is **geen** identieke NY-hypothese.

---

## 3. NY Sweep engine — keten (conceptueel)

1. **London reference session** (UTC): uit parquet M15 worden per kalenderdag high/low in het venster uit `sessions.london_reference` gehaald.
2. **Sweep-zoekvenster:** standaard gelijk aan **`trade_allowed_window`** (of optioneel `sessions.sweep_search_window`). Eerder zat de sweep alleen in een smal `ny_setup_window` (1 uur) — dat is aangepast voor meer kansen.
3. Per geschikt M15-bar (in dat venster): sweep van London low/high volgens regels in `setup.sweep`.
4. Daarna in dezelfde keten (max **N** bars vooruit, `MAX_CHAIN_BARS` in code): **displacement** → **FVG** (min gap in points) → **limit fill** op FVG-mid binnen `expire_if_not_filled_bars`, met invalidatie bij close buiten FVG-zone.
5. Optioneel **H1 bias** als `bias.h1_structure.enabled: true` (merged spec).
6. **Risk / throughput:** zie §5.

---

## 4. Policy-laag (niet hetzelfde als entry-logica)

- **`system_mode`:** o.a. `EDGE_DISCOVERY` zet standaard een aantal **effective filters** uit (regime, news, session, …) — tenzij je ze in `filters:` weer aanzet.
- QuantBuild **default.yaml** merge’t altijd mee; omgevingsvariabelen kunnen data paths override’n.

Dit verklaart waarom twee configs met dezelfde “strategie” toch andere **gates** kunnen hebben.

---

## 5. Wat bepaalt vooral **hoeveel trades** (NY Sweep)

| Hendel | Effect op throughput |
|--------|----------------------|
| **`trade_allowed_window` / `sweep_search_window`** | Breed venster (bijv. tot 16:00 UTC) ⇒ meer bars waar een sweep mag starten. |
| **Displacement & FVG drempels** | Hogere eisen (`min_range_atr_multiple`, `min_gap_points`, body/range) ⇒ minder setups. |
| **`expire_if_not_filled_bars`** | Korter ⇒ minder limit fills. |
| **`MAX_CHAIN_BARS` (code)** | Korter ⇒ displacement/FVG moeten dichter bij sweep vallen. |
| **`risk.max_trades_per_day`** | **Hard cap** (default **2**) per **UTC-dag** — geen “minimaal 1 per dag”. |
| **Sequentie / overlap** | Max één open trade: als een nieuw signaal vóór **exit** van de vorige zit ⇒ **skip** (geteld als `overlap` in de log). |
| **`stop_after_consecutive_losses`** | Bij intake vaak **2** ⇒ na 2 verliezers stopt de **rest van de backtest** — dat kan trades **dramatisch** verlagen (research-variant kan dit verhogen voor hogere *n*). |
| **News gate** | Alleen als `news.enabled` + effectieve filter `news` aan. |

Logregel (na run) bevat o.a.:  
`max 2 fills per UTC day | skipped: overlap=… daily_cap=… consec_loss=… daily_loss=…`

---

## 6. Huidige presets (naamgeving)

| Preset / pad | Kort |
|--------------|------|
| `configs/experiments/ny_sweep_reversion/ny_sweep_reversion_v1.yaml` | Canonieke research-intake (candidate). |
| `A0_raw_setup.yaml` | Min filters / fixed 2R / geen H1, news, spread. |
| `A0_high_sample.yaml` | Lossere parameters + breder venster + hogere `stop_after_consecutive_losses` **voor meer trades in research**. |
| `quantbuild/.../A0_5y_high_sample.yaml` | QuantBuild entry: **1825 dagen**, engine NY sweep, wijst naar `A0_high_sample.yaml`. |
| `quantbuild/.../A0_dedicated_engine.yaml` | NY sweep + bijv. `A0_raw_setup` (strenger, minder trades). |
| `A0_base_run.yaml` (SQE-proxy) | SQE-config die A0-**achtig** wil zijn — **geen** dedicated NY-hypothese. |

---

## 7. “Meer trades” — team-afwegingen

1. **Hypothese vs volume:** lossere regels verhogen *n* maar veranderen wat je test — duidelijk labelen (zoals `A0_high_sample`).
2. **Cap 2/dag:** intake blijft max 2 — als je puur **sample size** wilt, is dat oké; als je **capaciteit live** anders wilt, moet de **YAML + beleid** expliciet wijzigen.
3. **Overlap:** veel signalen op dezelfde dag kunnen door **één-open-trade** vallen; dat is **by design** tenzij je multi-slot of portfolio-logica bouwt.
4. **Twee engines:** meer trades via **SQE** (andere module-instellingen) vs via **NY dedicated** zijn **niet** automatisch vergelijkbaar — rapporteer ze apart.

---

## 8. Relevante paden (Implementatie)

| Onderdeel | Pad |
|-----------|-----|
| Backtest entry | `quantbuild/src/quantbuild/backtest/engine.py` |
| SQE | `quantbuild/src/quantbuild/strategies/sqe_xauusd.py` |
| NY Sweep engine | `quantbuild/src/quantbuild/strategies/ny_sweep_reversion_engine.py` |
| Research configs | `configs/experiments/ny_sweep_reversion/*.yaml` (suite-root) |
| Implementatiehandleiding | `quantbuild/docs/IMPLEMENTING_NEW_STRATEGIES.md` |

---

*Versie: samenvatting tbv teamoverleg; technische details staan in code en research-YAML.*
