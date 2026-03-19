# QuantBridge v1

Broker-agnostic execution infrastructure for trading bots.

## Why This Exists

QuantBridge separates strategy logic from broker execution:

bot -> risk -> routing -> broker adapter -> broker API -> execution result

This enables:
- faster broker switching
- multi-account deployment
- centralized risk enforcement
- execution resilience for propfirm workflows

## Current Status

This repository is a clean execution-focused codebase.

Implemented now:
- broker contract (canonical interface)
- cTrader adapter layer
- transport split (mock client + openapi client)
- symbol registry (mapping, precision, pip size, volume rules)
- error taxonomy
- health model
- smoke test flow (connect, price, place, close)
- startup recovery + state registry
- state validator + reconciliation actions
- runtime control loop (continuous sync + failsafe pause)
- order lifecycle manager (submit/fill/protection validation)

Partially implemented:
- cTrader Open API connect/auth + basic request flows

Not yet complete:
- multi-account routing engine
- execution confirmation after each order fill
- full monitoring dashboard and metrics backend

## Repository Structure

```text
configs/
  ctrader_icmarkets_demo.yaml
docs/
  ROADMAP.md
scripts/
  ctrader_smoke.py
  recover_execution_state.py
  run_runtime_control.py
  run_order_lifecycle_check.py
src/quantbridge/
  execution/
    broker_contract.py
    errors.py
    health.py
    models.py
    symbol_registry.py
    brokers/
      ctrader_broker.py
    clients/
      ctrader_mock_client.py
      ctrader_openapi_client.py
```

## Quick Start

1) Create and activate a virtual environment.
2) Fill `.env` from `.env.example`, then keep machine-specific secrets in `local.env` (preferred at runtime).
3) Run smoke test in mock mode:

```bash
python scripts/ctrader_smoke.py --config configs/ctrader_icmarkets_demo.yaml
```

4) Run smoke test in Open API mode:

```bash
python scripts/ctrader_smoke.py --config configs/ctrader_icmarkets_demo.yaml --mode openapi
```

5) Run startup reconnect + state recovery before launching bots:

```bash
python scripts/recover_execution_state.py --config configs/ctrader_icmarkets_demo.yaml --mode openapi --registry-path state/positions.json --strategy OCLW
```

6) Run runtime control loop (continuous sync + failsafe):

```bash
python scripts/run_runtime_control.py --config configs/ctrader_icmarkets_demo.yaml --mode openapi --registry-path state/positions.json --strategy OCLW
```

Optional dry run (single poll loop):

```bash
python scripts/run_runtime_control.py --config configs/ctrader_icmarkets_demo.yaml --mode openapi --max-iterations 1
```

Optional Telegram alerts:
- set `TELEGRAM_BOT_TOKEN`
- set `TELEGRAM_CHAT_ID`

7) Run order lifecycle validation (submit -> confirm fill -> protection check):

```bash
python scripts/run_order_lifecycle_check.py --config configs/ctrader_icmarkets_demo.yaml --mode mock --direction BUY --sl 2495 --tp 2510 --close-after
```

OpenAPI note:
- if your broker/account rejects SL/TP values on market submit, run lifecycle check without `--sl/--tp` and keep runtime failsafe active.

Auth help:
- `docs/AUTH_SETUP.md`

Expected output:

```json
{
  "connect": true,
  "price": true,
  "place_order": true,
  "close_order": true
}
```

## Milestones

- Milestone A: mock abstraction (done)
- Milestone B: real cTrader demo execution (in progress)
- Milestone C: reconciliation + restart safety
- Milestone D: prop-risk above broker layer
- Milestone E: multi-account scaling

## Engineering Rules

- strategy code contains no broker API calls
- broker differences stay in adapter + transport layers
- broker responses are normalized into internal models
- health and error codes are first-class data
