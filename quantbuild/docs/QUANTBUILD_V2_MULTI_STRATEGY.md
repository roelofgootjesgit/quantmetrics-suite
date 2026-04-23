# QuantBuild v2 — Multi-strategy strategy host

Dit document beschrijft de **doelarchitectuur**, **repo-/mapstructuur**, **strategy-interface**, en **rollout-plan** om QuantBuild om te bouwen van “één vaste strategie in de loop” naar **één engine die meerdere strategie-modules host**, met **portfolio/risk erboven** en **per-account configuratie**.

**Huidige situatie (referentie in deze repo):**

- `src/quantbuild/execution/live_runner.py` importeert en roept `sqe_xauusd` direct aan (hard gekoppelde strategie).
- `src/quantbuild/strategy_modules/base.py` definieert `BaseModule` (ICT/regime-blokken op DataFrame) — dat is **niet** hetzelfde als een **Strategy** die signalen produceert voor de host.
- Er bestaan al bouwstenen richting risico en accounts: o.a. `portfolio_heat.py`, `account_lifecycle.py`, configs zoals `challenge.yaml` / `funded.yaml`.

---

## 1. Waarom v2 (en wat is de edge)

**Edge zit niet in “meer strategieën”, maar in:**

- Sneller strategieën toevoegen zonder de core-loop te kopiëren.
- **Eén** execution-, risk-, logging- en sync-pad voor alle strategieën.
- Slechte strategieën uitzetten zonder deploy van een andere bot.
- Goede strategieën op meerdere accounts met **andere strategy mix** en **andere risk budgetten**.
- **Portfolio-level** vetos (correlatie, totaal risico, max open trades).

**Te vermijden:**

| Risico | Gevolg |
|--------|--------|
| Strategy spaghetti (`if strategy == "x"`) | Ononderhoudbare core, dubbele uitzonderingen |
| Risk leakage | Strategie denkt “1 trade OK”, portfolio al vol |
| Geen lifecycle | Geen enable/disable, score, kill rules |
| N bots, N codebases | Inconsistent gedrag, moeilijk debuggen/deployen |

---

## 2. Repo-keuze: nieuw project vs. dezelfde repo

**Aanbeveling (praktisch):**

- **Nieuw project of duidelijke snapshot** (bijv. `quantbuild-v2` / `quantbuild-suite`) als je **stabiele live flow** niet wilt riskeren tijdens grote refactor — huidige repo blijft referentie en fallback.
- **Zelfde repo, nieuwe packages** (`orchestrator/`, `portfolio/`, strategy loader) is prima als je **branch** (`v2-development`) langdurig kunt isoleren en releases strak scheidt.

**Regel bij kopiëren / aftakken:**

**Wél meenemen:** config-systeem, broker factory, execution contract, risk-basis, logging/quantlog, runner-skelet, stabiele IO.

**Niet blind meenemen:** strategie-specifieke hacks, experimentele scripts, oude uitzonderingen in de main loop.

---

## 3. Vier lagen (doelbeeld)

```
┌─────────────────────────────────────────────────────────┐
│ Layer 4 — Account deployment                            │
│  Per account: YAML/JSON — welke strategieën, portfolio   │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│ Layer 3 — Portfolio orchestration                       │
│  Actief set, signal queue, prioriteit, conflicts, veto  │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│ Layer 2 — Strategy plugins                              │
│  Zelfde interface; geen core if/elif per strategie     │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│ Layer 1 — Core engine                                   │
│  Data, event loop, regime/sessie hooks, broker, risk    │
│  checks, positions sync, logging                         │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Voorgestelde mapstructuur (v2-doel)

Aansluitend op de bestaande `src/quantbuild/`-layout, met **nieuwe** duidelijke grenzen:

```text
src/quantbuild/
├── core/                          # (optioneel) engine façade — of behoud app.py als entry
│   └── ...
├── config.py                      # bestaand — uitbreiden voor strategies[] + portfolio
├── models/
│   ├── signal.py                  # bestaand — uitbreiden (strategy_id, metadata)
│   └── trade.py                   # bestaand
├── execution/                     # bestaand — broker, live_runner refactor
│   ├── live_runner.py             # roept alleen orchestrator + engine hooks aan
│   ├── broker_factory.py
│   ├── portfolio_heat.py          # portfolio-laag uitbreiden / laten veto’en
│   └── ...
├── strategies/                    # één module per strategie (plugins)
│   ├── __init__.py
│   ├── base.py                    # Strategy protocol / ABC (zie §5)
│   ├── xau_core_strategy.py       # migratie van huidige SQE/XAU-logica
│   ├── xau_trend_london.py        # voorbeeld tweede strategie (MVP)
│   └── xau_ny_reversal.py
├── strategy_modules/              # bestaand — hergebruik als building blocks
│   ├── base.py                    # BaseModule blijft voor ICT/regime blocks
│   └── ...
├── orchestrator/
│   ├── __init__.py
│   ├── loader.py                  # importlib / entry points: laad strategieën uit config
│   ├── signal_queue.py            # verzamelen, sorteren, dedup
│   └── portfolio_gate.py        # max risk, max trades, correlation guard
└── portfolio/                     # (optioneel apart van orchestrator/)
    └── risk_budget.py
```

**Config-nabijheid:**

```text
configs/
├── accounts/
│   ├── ftmo_challenge_01.yaml
│   └── icmarkets_funded_02.yaml
└── instruments/
    └── ...
```

---

## 5. Strategy interface (contract)

**Doel:** de engine vraagt nooit “sqe_xauusd”, maar: *geef mij signalen voor deze context*.

### 5.1 Context naar de strategie

Minimaal wat de core al heeft of kan bouwen (uitbreidbaar):

- `bar` / recente OHLC (DataFrame of slice)
- `now` (timezone-aware)
- `regime` (string of enum)
- `symbol` / instrument id
- `open_positions` (samenvatting)
- `account_id`
- `config` (strategie-subdict uit account-config)

### 5.2 Strategie → engine

Strategieën retourneren **neutrale signalen** (bestaand model uitbreiden):

- Hergebruik `Signal` / `EntryCandidate` uit `models/signal.py` waar mogelijk.
- Voeg minstens toe: `strategy_id: str` (stabiele id), optioneel `priority: float`, `tags: list[str]`.

### 5.3 Conceptuele interface (Python)

```python
# strategies/base.py — richtinggevend; exacte types afstemmen op jullie models

from abc import ABC, abstractmethod
from typing import Any, List, Sequence

from src.quantbuild.models.signal import Signal  # eventueel uitgebreid model


class StrategyContext:
    """Snapshot van wat de engine aan de strategie geeft (minimaal MVP)."""
    symbol: str
    account_id: str
    config: dict[str, Any]
    # bars, regime, positions: invullen met bestaande types


class Strategy(ABC):
    """Layer-2 plugin: geen broker-calls; alleen signalen."""

    id: str  # uniek, voor logging en portfolio

    @abstractmethod
    def allowed_symbols(self) -> Sequence[str]: ...

    @abstractmethod
    def on_bar(self, ctx: StrategyContext) -> List[Signal]: ...

    def on_tick(self, ctx: StrategyContext) -> List[Signal]:
        return []

    def on_news(self, ctx: StrategyContext) -> List[Signal]:
        return []
```

**Scheiding van verantwoordelijkheid:**

| Component | Mag wel | Mag niet |
|-----------|---------|----------|
| `Strategy` | Signalen, interne indicators, gebruik `strategy_modules` | Orders plaatsen, broker direct |
| `Orchestrator` | Prioriteit, conflict resolution, welke signalen door | Data van broker fetchen |
| `Core engine` | Data, execution, risk validator, sync | `if name == "sqe"` |

---

## 6. Portfolio orchestrator (Layer 3)

**Taken:**

1. **Verzamelen** — alle actieve strategieën: `on_bar` (en later tick/news).
2. **Normaliseren** — zelfde `Signal`-shape; dedup (zelfde richting/symbol binnen één bar).
3. **Ranken** — bv. confidence, strength, vaste priority per strategie-config.
4. **Veto** — `portfolio_heat` / max open trades / max totaal risico / correlation guard.
5. **Output** — 0..N `EntryCandidate`-achtige objecten naar de bestaande execution-pijplijn.

**Belangrijk:** één plek waar “portfolio al vol” wordt afgedwongen — niet per strategie opnieuw.

---

## 7. Account deployment (Layer 4) — voorbeeldconfig

```yaml
account_id: ftmo_challenge_01
mode: challenge   # challenge | funded | demo

broker:
  provider: ctrader
  account_id: "…"

strategies:
  - id: xau_core
    class: src.quantbuild.strategies.xau_core_strategy:XauCoreStrategy
    enabled: true
    config:
      sessions: ["london", "ny"]
  - id: xau_ny_reversal
    class: src.quantbuild.strategies.xau_ny_reversal:XauNyReversalStrategy
    enabled: true
    config: {}

portfolio:
  max_total_risk_pct: 2.0
  max_open_trades: 3
  correlation_guard: true
  max_signals_per_bar: 2
```

**Loader (`orchestrator/loader.py`):**

- Lees `strategies[]`.
- `importlib` of `entry_points` om class te laden.
- Instantieer met strategie-`config`.
- Filter `enabled: false` uit runtime set.

---

## 8. Migratie van de huidige codebase

| Huidig | Actie in v2 |
|--------|-------------|
| `live_runner.py` → direct `run_sqe_conditions` | Vervangen door: bouw `StrategyContext` → roep geregistreerde strategieën → orchestrator → execution |
| `strategies/sqe_xauusd.py` | Opsplitsen/logisch verplaatsen naar `strategies/xau_core_strategy.py` (wrapper die bestaande functies aanroept is oké voor MVP) |
| `strategy_modules/*` | Blijven **libraries**; strategie importeert ze — geen nieuwe if/elif in runner |
| `portfolio_heat.py` | Orchestrator roept dit aan als **veto** vóór order |
| `challenge.yaml` / `funded.yaml` | Uitbreiden met `strategies:` + `portfolio:` secties |

---

## 9. Rollout-plan (fasen)

### Fase 1 — Van bot naar host (MVP kern)

| Stap | Omschrijving | Done-kriterium |
|------|----------------|----------------|
| 1.1 | Introduceer `Strategy` ABC + `StrategyContext` | Unit tests op mock context |
| 1.2 | Implementeer `orchestrator/loader.py` (1 strategie uit config) | Live/paper start met alleen config-wijziging |
| 1.3 | Migreer huidige XAU/SQE naar `xau_core_strategy` | Zelfde gedrag als nu (regressie op dry-run logs) |
| 1.4 | Refactor `live_runner`: geen directe import van `sqe_xauusd` | Runner alleen engine + orchestrator |

### Fase 2 — Van host naar portfolio

| Stap | Omschrijving | Done-kriterium |
|------|----------------|----------------|
| 2.1 | Laad **meerdere** strategieën parallel | Config met 2+ ids |
| 2.2 | `signal_queue` + rank + `max_signals_per_bar` | Twee signalen op één bar: verwachte subset wordt uitgevoerd |
| 2.3 | Portfolio veto (risk, open trades, heat) | Geblokkeerde trades met duidelijke `blocked_reason` in logs |

### Fase 3 — Prop-ready (account)

| Stap | Omschrijving | Done-kriterium |
|------|----------------|----------------|
| 3.1 | `configs/accounts/*.yaml` per deployment | Eén systemd service / proces per account config |
| 3.2 | Mode: challenge vs funded (bestaande lifecycle integreren) | Risk budget verschilt per mode |
| 3.3 | Documentatie deploy (runbook link) | Operators weten welke config waar hoort |

### Fase 4 — Lifecycle & strategische analyse

| Stap | Omschrijving | Done-kriterium |
|------|----------------|----------------|
| 4.1 | Runtime enable/disable (config reload of API — kies één) | Strategie uit zonder redeploy |
| 4.2 | Score per strategie (PnL, hit rate, drawdown per `strategy_id`) | Dashboard of structured logs |
| 4.3 | Kill / promote rules | Automatisch of semi-automatisch uitzetten bij degradatie |

---

## 10. MVP-build volgorde (samenvatting)

1. Strategy base class + context object.  
2. Huidige XAU-logica naar `strategies/xau_core_strategy.py`.  
3. Engine roept alleen de interface aan.  
4. Tweede eenvoudige strategie (trend vs reversal) om conflicts te testen.  
5. Mini portfolio selector: verzamelen → rank → 1–2 toestaan.  
6. Config-based strategy loading per account.

---

## 11. Test- en kwaliteitslat

- **Geen** nieuwe `if strategy_name` in `live_runner` — alleen generieke orchestration.  
- Elke strategie: eigen testfile met vaste OHLC-fixtures.  
- Integratietest: twee strategieën, één bar, assert welke signalen de gate doorlaten.  
- Logging: elke beslissing met `strategy_id`, `account_id`, `blocked_reason`.

---

## 12. Eén zin

**Bouw geen fleet losse bots; bouw één QuantBuild-engine die strategieën als plugins host, met één execution- en risk-pad en portfolio-vetos erboven — en rol dat gefaseerd uit zodat de huidige stabiele flow traceerbaar blijft.**

---

*Documentversie: 1.0 — afgestemd op repo `quantbuild` (o.a. `live_runner`, `sqe_xauusd`, `BaseModule`, `Signal`).*
