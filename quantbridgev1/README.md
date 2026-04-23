# quantbridgev1

Broker-agnostic execution infrastructure for trading bots (**Quant suite**: sibling repos `quantmetrics_os`, `quantbuildv1`, **`quantbridgev1`**, `quantlogv1`, `quantanalyticsv1`).

## Why This Exists

**quantbridgev1** separates strategy logic from broker execution:

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
- prop risk gate (pre-trade limits + breach blocking)
- account state machine + policy-aware account selection
- persistent account governance store + health-aware eligibility checks
- multi-account execution planning (single/primary-backup/fanout)
- structured observability events (JSONL) + summary reporting

Partially implemented:
- cTrader Open API connect/auth + basic request flows

Not yet complete:
- multi-account fanout runner
- full monitoring dashboard and metrics backend

## Repository Structure

```text
configs/
  ctrader_icmarkets_demo.yaml
  accounts_baseline.yaml
  suite_profiles.yaml
docs/
  ROADMAP.md
  PAPER_ROLLOUT.md
scripts/
  ctrader_smoke.py
  recover_execution_state.py
  run_runtime_control.py
  run_order_lifecycle_check.py
  run_account_orchestration_check.py
  run_multi_account_execution_check.py
  run_vps_paper_cycle.py
  validate_account_env.py
  account_control.py
  rotate_observability_events.py
  summarize_observability.py
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
  risk/
    account_limits.py
    risk_engine.py
    prop_guard.py
  accounts/
    account_policy.py
    account_state_store.py
    account_state_machine.py
  router/
    account_selector.py
    execution_plan_builder.py
    execution_orchestrator.py
  ops/
    observability.py
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

Optional risk-gate flags (recommended for prop style checks):
- `--daily-dd-limit-pct 5`
- `--total-dd-limit-pct 10`
- `--max-open-risk-pct 3`
- `--max-risk-per-trade-pct 1`
- `--max-concurrent-positions 3`

OpenAPI note:
- if your broker/account rejects SL/TP values on market submit, run lifecycle check without `--sl/--tp` and keep runtime failsafe active.

8) Run account-orchestration selection check:

```bash
python scripts/run_account_orchestration_check.py --config configs/accounts_baseline.yaml --instrument XAUUSD
```

Health/persistence simulation examples:
- pause primary account and force backup selection:
  `python scripts/run_account_orchestration_check.py --config configs/accounts_baseline.yaml --pause-account DEMO_A`
- simulate missing credentials:
  `python scripts/run_account_orchestration_check.py --config configs/accounts_baseline.yaml --missing-creds-account DEMO_A`
- simulate max positions reached:
  `python scripts/run_account_orchestration_check.py --config configs/accounts_baseline.yaml --open-positions DEMO_A:3`

9) Run multi-account execution policy check:

```bash
python scripts/run_multi_account_execution_check.py --config configs/accounts_baseline.yaml --instrument XAUUSD --routing-mode primary_backup --units 100
```

Other routing modes:
- `--routing-mode single`
- `--routing-mode fanout --max-fanout-accounts 2`
- `--events-file logs/events.jsonl`

Observability summary:

```bash
python scripts/summarize_observability.py --events-file logs/events.jsonl
```

10) Run full mock regression suite (all core layers):

```bash
python scripts/run_regression_suite.py
```

This runs:
- smoke
- recovery
- runtime loop (single iteration)
- order lifecycle check
- account orchestration check
- multi-account execution checks (single / primary_backup / fanout)

11) Run VPS paper cycle profile (startup gate + suite + runtime probe):

```bash
python scripts/run_vps_paper_cycle.py --profile vps_paper --report-file logs/vps_paper_cycle_report.json
```

12) Validate account policy to ENV linking before runtime:

```bash
python scripts/validate_account_env.py --config configs/accounts_baseline.yaml --env-file local.env --require-secrets
```

13) Control account governance state:

```bash
python scripts/account_control.py status --accounts-config configs/accounts_baseline.yaml
python scripts/account_control.py pause --account-id DEMO_A --reason "manual risk hold"
python scripts/account_control.py resume --account-id DEMO_A --mode demo --reason "manual clear"
```

14) Rotate and summarize observability logs:

```bash
python scripts/rotate_observability_events.py --events-file logs/events.jsonl --archive-dir logs/archive
python scripts/summarize_observability.py --events-file logs/events.jsonl --since-minutes 60
```

15) VPS scheduler artifacts:
- cron example: `ops/vps/quantbridge_paper.cron`
- systemd service example: `ops/vps/quantbridge-paper.service`
- install helper: `ops/vps/install_paper_service.sh`

Install service on VPS:

```bash
sudo bash ops/vps/install_paper_service.sh
```

Auth help:
- `docs/AUTH_SETUP.md`
- `docs/PAPER_ROLLOUT.md`

Expected output:

```json
{
  "connect": true,
  "price": true,
  "place_order": true,
  "close_order": true
}
```

## Suite repositories (GitHub)

| Repo | Remote |
| --- | --- |
| `quantmetrics_os` | [roelofgootjesgit/quantmetrics_os](https://github.com/roelofgootjesgit/quantmetrics_os) |
| `quantbuildv1` | [roelofgootjesgit/quantbuildv1](https://github.com/roelofgootjesgit/quantbuildv1) |
| `quantbridgev1` (**this**) | [roelofgootjesgit/quantbridgev1](https://github.com/roelofgootjesgit/quantbridgev1) |
| `quantlogv1` | [roelofgootjesgit/quantlogv1](https://github.com/roelofgootjesgit/quantlogv1) |
| `quantanalyticsv1` | [roelofgootjesgit/quantanalyticsv1](https://github.com/roelofgootjesgit/quantanalyticsv1) |

## Milestones

- Milestone A: mock abstraction (done)
- Milestone B: real cTrader demo execution (done baseline)
- Milestone C: reconciliation + restart safety (done)
- Milestone D: runtime control + lifecycle safety (done baseline)
- Milestone E: account orchestration baseline (done baseline)
- Milestone F: persistent governance + health-aware routing (done baseline)
- Milestone G: multi-account routing + execution planning (done baseline)
- Milestone H: multi-account scaling + production observability (in progress, observability baseline done)

## Engineering Rules

- strategy code contains no broker API calls
- broker differences stay in adapter + transport layers
- broker responses are normalized into internal models
- health and error codes are first-class data
