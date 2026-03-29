# QuantLog v1

QuantLog is the observability and truth layer for the Quant stack:

- `QuantBuild` generates strategy/risk decisions.
- `QuantBridge` handles broker and execution lifecycle.
- `QuantLog` stores canonical events, replays traces, validates contracts, and reports run quality signals.

## What QuantLog does

- Canonical event envelope across systems.
- Append-only JSONL event store.
- Deterministic trace replay.
- Schema and payload contract validation.
- Daily metrics summary.
- Ingest health checks with `audit_gap_detected` support.

This repo is intentionally scoped as an event spine, not a full BI platform.

## Core contracts

- **Required envelope fields**: `event_id`, `event_type`, `event_version`, `timestamp_utc`, `ingested_at_utc`, `source_system`, `source_component`, `environment`, `run_id`, `session_id`, `source_seq`, `trace_id`, `severity`, `payload`
- **Environment enum**: `paper|dry_run|live|shadow`
- **Decision semantics**
  - `risk_guard_decision.decision`: `ALLOW|BLOCK|REDUCE|DELAY`
  - `trade_action.decision`: `ENTER|EXIT|REVERSE|NO_ACTION`
- **Replay ordering**: `timestamp_utc` -> `source_seq` -> `ingested_at_utc`

See `EVENT_SCHEMA.md` for full schema and examples.

## Repository layout

```text
quantlog-v1/
├── src/quantlog/
│   ├── events/       schema + io
│   ├── ingest/       emitters + health checks
│   ├── validate/     contract validator
│   ├── replay/       trace replay service
│   ├── summarize/    daily summary service
│   └── cli.py
├── scripts/          smoke + synthetic data + ci runner
├── tests/            unit tests
├── data/events/      sample/generated event files
├── configs/          schema registry
└── docs (*.md)       architecture/runbook/mentor updates
```

## Quickstart (Windows PowerShell)

```powershell
cd "c:\Users\Gebruiker\quantLog v.1"
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
```

## CLI commands

Validate events:

```powershell
python -m quantlog.cli validate-events --path data/events/sample
```

Replay one trace:

```powershell
python -m quantlog.cli replay-trace --path data/events/sample --trace-id trace_demo_1
```

Summarize event day/folder:

```powershell
python -m quantlog.cli summarize-day --path data/events/sample
```

Check ingest health:

```powershell
python -m quantlog.cli check-ingest-health --path data/events/sample --max-gap-seconds 120
```

Emit `audit_gap_detected` events for detected gaps:

```powershell
python -m quantlog.cli check-ingest-health --path data/events/sample --max-gap-seconds 120 --emit-audit-gap
```

## Build and test workflows

Unit tests:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

End-to-end acceptance smoke:

```powershell
python scripts/smoke_end_to_end.py
```

Generate synthetic sample day:

```powershell
python scripts/generate_sample_day.py --output-path data/events/generated --date 2026-03-29 --traces 25
python -m quantlog.cli validate-events --path data/events/generated/2026-03-29
python -m quantlog.cli summarize-day --path data/events/generated/2026-03-29
```

Local CI gates:

```powershell
.\scripts\ci_smoke.ps1
```

## GitHub CI

- Workflow: `.github/workflows/ci.yml`
- Runs on push and pull request
- Executes the same smoke gates as local CI script

## Additional docs

- `QUANTLOG_V1_ARCHITECTURE.md` - architecture and MVP boundaries
- `EVENT_SCHEMA.md` - canonical schema and payload definitions
- `REPLAY_RUNBOOK.md` - incident/replay/ops procedures
- `MENTOR_UPDATE.md` - engineering status and next-phase direction
