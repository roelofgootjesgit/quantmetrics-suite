# Data-overdracht: huidige pad en latere opties

**Doel:** vastleggen hoe event-JSONL van productie naar analyse komt, en welke alternatieven pas zinvol zijn als **correlatievelden en eventkwaliteit** op orde zijn (`run_id`, `session_id`, `trace_id`, `source_seq`, `timestamp_utc`).

**Volledige prioriteitenlijst:** [PLATFORM_ROADMAP.md](PLATFORM_ROADMAP.md).

**Niet bedoeld als tweede waarheid voor codepaden** — die blijven in QuantBuild-config en [VPS_SYNC.md](VPS_SYNC.md).

---

## Huidige werkwijze (voldoende voor nu)

Typische flow:

```text
VPS
  …/quantlog_events/YYYY-MM-DD/*.jsonl
    → tar.gz
    → scp (of vergelijkbaar)
laptop
  → lokale map (bijv. data/imported/)
  → quantlog CLI (validate-events, summarize-day, score-run, …)
```

Stap-voor-stap copy/paste staat in [WEEKLY_ANALYSIS_WORKFLOW.md](WEEKLY_ANALYSIS_WORKFLOW.md).

**Prioriteit eerst:** emitter in QuantBuild (lege `run_id` / `session_id` oplossen), canonieke `NO_ACTION`-reasons, daarna uitbreiden met o.a. `signal_evaluated` en `risk_guard_decision`. Zonder betrouwbare correlatie verliest downstream analyse snel waarde — zie dezelfde discussie in jullie operationele evaluatie.

---

## Latere opties (nog niet nodig)

| Optie | Korte noot |
|-------|------------|
| **rsync (nightly)** | Incrementeel, eenvoudig op VPS + cron; geen extra diensten. |
| **S3 (of vergelijkbare object storage)** | Schaalbaar, lifecycle policies; iets meer setup en IAM. |
| **GitHub Actions artifact** | Handig voor gecontroleerde exports vanuit CI; minder geschikt voor grote continue streams. |
| **Kleine ingest-server** | Push-model, centrale validatie bij binnenkomst; meer beheer. |
| **Parquet-export** | Compacte analytische snapshots naast JSONL; vaak tweede stap. |
| **Postgres / warehouse** | Query’s en dashboards op schaal; pas na stabiel schema en kwaliteitschecks. |

Kies pas als volume, team of compliance dat vraagt — **niet** als vervanging voor eerst data en validatie strak te trekken.

---

## Gerelateerd

- [WEEKLY_ANALYSIS_WORKFLOW.md](WEEKLY_ANALYSIS_WORKFLOW.md) — wekelijkse analyse op de laptop  
- [VPS_SYNC.md](VPS_SYNC.md) — waar QuantLog op de VPS staat en hoe je pull/deploy doet  
- [REPLAY_RUNBOOK.md](REPLAY_RUNBOOK.md) — replay en incidenten
