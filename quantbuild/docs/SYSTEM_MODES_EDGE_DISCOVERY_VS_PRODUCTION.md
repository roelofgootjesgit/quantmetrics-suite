# System modes: `PRODUCTION` vs `EDGE_DISCOVERY`

Korte operator‑samenvatting. Uitgebreide context: `docs/2 operating modes for my XAUUSD.md`.

## Intent

- **`PRODUCTION`**: alle policy‑filters aan (regime, sessie, cooldown, nieuws, positielimiet, dagelijks verlies‑cap, spread) — gelijk aan eerdere default `filters:` alles `true`.
- **`EDGE_DISCOVERY`**: throughput voor expectancy‑analyse; zelfde SQE‑logica, maar **minder vetos** buiten catastrofaal risico. Standaard: regime/sessie/cooldown/news/position_limit uit; **H1‑structure gate uit in backtest** (`structure_h1_gate`); `daily_loss` en `spread` aan; `research_raw_first` aan (live: SQE vóór regime‑poort).

## YAML

```yaml
system_mode: PRODUCTION   # of EDGE_DISCOVERY

# Optioneel: per‑key overrides bovenop de modus‑defaults
filters:
  regime: true
```

## Module

- `src/quantbuild/policy/system_mode.py` — `resolve_effective_filters(cfg)` levert effectieve booleans voor `LiveRunner` en backtest.

## Snel vergelijken (backtest)

```text
python -m src.quantbuild.app backtest --config configs/strict_prod_v2.yaml
python -m src.quantbuild.app backtest --config configs/system_mode_edge_discovery.yaml
```

## Risico

`EDGE_DISCOVERY` is bedoeld voor **research/demo/paper**, niet als permanente live‑instelling zonder governance.
