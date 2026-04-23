# quantlogv1

Observability and truth layer for the Quant stack (`quantbuildv1` → `quantbridgev1` → **`quantlogv1`** JSONL):

- **`quantbuildv1`** generates strategy/risk decisions.
- **`quantbridgev1`** handles broker and execution lifecycle.
- **`quantlogv1`** (this repo) stores canonical events, replays traces, validates contracts, and reports run quality signals.
- **`quantanalyticsv1`** reads the same JSONL for downstream reports (funnel, no-trade reasons, performance slices).

## What this repo does

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

See [docs/EVENT_SCHEMA.md](docs/EVENT_SCHEMA.md) for full schema and examples. **Index:** [docs/README.md](docs/README.md).

## Repository layout

```text
quantlogv1/
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
└── docs/             all Markdown documentation (index: docs/README.md)
```

## Quickstart (Windows PowerShell)

```powershell
cd "c:\Users\Gebruiker\quantlogv1"
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

The JSON output includes `no_action_by_reason` and `trade_action_by_decision` (NO_ACTION histogram) plus `risk_guard_blocks_by_guard` for guard funnel analysis.

`validate-events` also returns `errors_by_code` and `warnings_by_code` (aggregated issue message prefixes).

Check ingest health:

```powershell
python -m quantlog.cli check-ingest-health --path data/events/sample --max-gap-seconds 120
```

Emit `audit_gap_detected` events for detected gaps:

```powershell
python -m quantlog.cli check-ingest-health --path data/events/sample --max-gap-seconds 120 --emit-audit-gap
```

Run quality scorecard:

```powershell
python -m quantlog.cli score-run --path data/events/sample --max-gap-seconds 300 --pass-threshold 95
```

`score-run` includes the same throughput histograms as `summarize-day` (`no_action_by_reason`, `trade_action_by_decision`, `risk_guard_blocks_by_guard`, `trades_attempted`, …) next to the quality score.

Nightly-style chain (same four steps, exit code reflects worst failure):

```powershell
powershell -File scripts/nightly_quantlog_report.ps1 -Path data/events/sample
```

On Linux/VPS:

```bash
bash scripts/nightly_quantlog_report.sh data/events/sample
```

Canonical `NO_ACTION` payload reasons (for **quantbuildv1** emitters):

```powershell
python -m quantlog.cli list-no-action-reasons
```

v1 `event_type` names and required payload keys:

```powershell
python -m quantlog.cli list-event-types
```

Required envelope fields plus allowed `severity` / `environment` / `source_system` (and decision enums):

```powershell
python -m quantlog.cli list-envelope-schema
```

All of the above in one JSON (for docs/codegen):

```powershell
python -m quantlog.cli export-v1-schema
```

`summarize-day` and `score-run` also include `by_severity`, `by_source_system`, `by_source_component`, and `by_environment` next to `by_event_type`.

`non_contract_event_types` counts `event_type` strings that are **not** in the v1 contract (`list-event-types`). The quality score applies a small penalty when any are present.

**quantbuildv1** pipeline (edge decomposition): contract types `signal_detected`, `signal_filtered`, `trade_executed` — see `docs/EVENT_SCHEMA.md`. `summarize-day` adds `signal_filtered_by_reason` (histogram op canonieke `filter_reason`).

`summarize-day` and `score-run` include `count_unique_run_ids`, `count_unique_session_ids`, and `count_unique_trace_ids` (distinct non-empty envelope values) to spot merged folders or multi-run days.

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

Generate expanded scenarios:

```powershell
python scripts/generate_sample_day.py --output-path data/events/generated --date 2026-03-29 --traces 50 --include-session-restart-probe
```

Generate anomaly day for negative quality tests:

```powershell
python scripts/generate_sample_day.py --output-path data/events/generated --date 2026-03-29 --traces 25 --inject-anomalies
python -m quantlog.cli score-run --path data/events/generated/2026-03-29 --pass-threshold 95
```

Contract integration check:

```powershell
python scripts/contract_check.py --contracts-path tests/fixtures/contracts --max-warnings 0
```

Local CI gates:

```powershell
.\scripts\ci_smoke.ps1
```

## GitHub CI

- Workflow: `.github/workflows/ci.yml`
- Runs on push and pull request
- Executes the same smoke gates as local CI script

## Suite repositories (GitHub)

| Repo | Remote |
| --- | --- |
| `quantmetrics_os` | [roelofgootjesgit/quantmetrics_os](https://github.com/roelofgootjesgit/quantmetrics_os) |
| `quantbuildv1` | [roelofgootjesgit/quantbuildv1](https://github.com/roelofgootjesgit/quantbuildv1) |
| `quantbridgev1` | [roelofgootjesgit/quantbridgev1](https://github.com/roelofgootjesgit/quantbridgev1) |
| `quantlogv1` (**this**) | [roelofgootjesgit/quantlogv1](https://github.com/roelofgootjesgit/quantlogv1) |
| `quantanalyticsv1` | [roelofgootjesgit/quantanalyticsv1](https://github.com/roelofgootjesgit/quantanalyticsv1) |

## Documentation

All Markdown files live under **`docs/`**. Start at **[docs/README.md](docs/README.md)** for the full index.

Highlights:

- [docs/QUANTLOG_V1_ARCHITECTURE.md](docs/QUANTLOG_V1_ARCHITECTURE.md) — architecture and MVP boundaries
- [docs/EVENT_SCHEMA.md](docs/EVENT_SCHEMA.md) — canonical schema and payload definitions
- [docs/EVENT_VERSIONING_POLICY.md](docs/EVENT_VERSIONING_POLICY.md) — schema/version compatibility policy
- [docs/QUANTLOG_GUARDRAILS.md](docs/QUANTLOG_GUARDRAILS.md) — scope boundaries and non-negotiables
- [docs/SCHEMA_CHANGE_CHECKLIST.md](docs/SCHEMA_CHANGE_CHECKLIST.md) — checklist for schema changes
- [docs/REPLAY_RUNBOOK.md](docs/REPLAY_RUNBOOK.md) — incident/replay/ops procedures
- [docs/MENTOR_UPDATE.md](docs/MENTOR_UPDATE.md) — engineering status and next-phase direction
- [docs/ROADMAP_EXECUTION_STATUS.md](docs/ROADMAP_EXECUTION_STATUS.md) — roadmap status and completion log
- [docs/QUANTBUILD_QUANTLOG_INTEGRATION_PLAN.md](docs/QUANTBUILD_QUANTLOG_INTEGRATION_PLAN.md) — integration plan (dry-run → full stack)
- [docs/QUANT_STACK_INTEGRATION_ACCEPTANCE.md](docs/QUANT_STACK_INTEGRATION_ACCEPTANCE.md) — stack acceptance dossier (001 / 002)
- [docs/VPS_SYNC.md](docs/VPS_SYNC.md) — VPS: zelfde venv/pull-workflow als **quantbuildv1** (`VPS_MULTI_MODULE` + Operator Cheatsheet), **quantlogv1** als derde repo
- [docs/QUANTLOG_UITLEG.md](docs/QUANTLOG_UITLEG.md) / [docs/QUANTLOG_SOFTWARE.md](docs/QUANTLOG_SOFTWARE.md) — NL / software overview
