# Paper Rollout Runbook

This runbook defines the 24h paper rollout path and go-live gates.

## Scope

- VPS-first operation
- Hybrid checks (CI + VPS runtime gates)
- Paper execution only (no live capital)

## Required Commands

1) Account credential gate:

```bash
python scripts/validate_account_env.py --config configs/accounts_baseline.yaml --env-file local.env --require-secrets
```

2) Full regression suite:

```bash
python scripts/run_regression_suite.py
```

3) VPS cycle:

```bash
python scripts/run_vps_paper_cycle.py --profile vps_paper --report-file logs/vps_paper_cycle_report.json
```

4) Runtime loop with events:

```bash
python scripts/run_runtime_control.py --config configs/ctrader_icmarkets_demo.yaml --mode openapi --strategy OCLW --events-file logs/events.jsonl
```

5) Event summary (last hour):

```bash
python scripts/summarize_observability.py --events-file logs/events.jsonl --since-minutes 60
```

## 24h Paper Checklist

- [ ] `validate_account_env` is green for all enabled accounts.
- [ ] `run_regression_suite` passes fully.
- [ ] VPS scheduler runs `run_vps_paper_cycle.py` every 5 minutes.
- [ ] Runtime loop stays up for 24h with no unhandled crashes.
- [ ] No order attempts on paused or breached accounts.
- [ ] No unexplained failsafe pauses.
- [ ] Event logs rotate successfully and archive files are created.
- [ ] Hourly summaries show stable event/error ratios.

## Go-Live Gates

All gates must be true before moving beyond paper:

1. **Governance Gate**
   - account states persist across restart
   - pause/breach status always respected by routing

2. **Execution Gate**
   - order lifecycle checks confirm fill/protection behavior
   - primary/backup and fanout policies behave deterministically

3. **Observability Gate**
   - JSONL event stream present
   - summaries can be produced for last 15/60 minutes
   - error spikes are detectable in summaries

4. **Operational Gate**
   - scheduler auto-recovers cycle checks
   - runtime process restarts automatically on failure

## Recommended Rollout Sequence

1) One account-group in paper.
2) Validate 24h checklist.
3) Add second account-group.
4) Re-run 24h checklist.
5) Only then discuss restricted live rollout.
