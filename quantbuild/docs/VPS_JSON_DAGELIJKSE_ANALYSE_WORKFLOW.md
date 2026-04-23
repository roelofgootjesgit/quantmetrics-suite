# Dagelijkse JSON van de VPS: workflow, opslag en analyse (voor mentor)

**Doel van dit document:** korte briefing zodat we samen kunnen kiezen *waar* runtime-JSON terechtkomt, *hoe* die dagelijks beschikbaar wordt voor analyse, en *welke* tooling past bij jullie risico- en compliance-eisen.

**Huidige situatie:** QuantBuild draait op een Linux-VPS; ontwikkelaar heeft SSH-toegang via VS Code (Remote SSH). Er is behoefte om JSON-output **automatisch** (idealiter elke dag) te verzamelen en te analyseren — eventueel deels op de VPS, eventueel elders.

---

## 1. Welke “JSON” bedoelen we concreet?

In deze codebase komen minstens twee patronen voor:

| Type | Vorm | Typisch gebruik |
|------|------|-----------------|
| **QuantLog-events** | JSON Lines (`.jsonl`), per UTC-dag een map + append-file | Audit trail, beslissingen, tracering (`QuantLogEmitter` schrijft o.a. `…/YYYY-MM-DD/quantbuild.jsonl`) |
| **Samenvattende snapshots** | Eén JSON per run/dag (bijv. scoreboard) | Snelle KPI’s, vergelijking dag-op-dag |
| **Research / batch scripts** | JSON in `reports/` of vergelijkbaar | Backtests, robustness — minder vaak “dagelijks productie” |

Voor **operationele dagelijkse monitoring** zijn vooral **JSONL + compacte dag-samenvatting** interessant: JSONL voor detail, één klein “daily summary” JSON voor dashboards en mentor-review.

---

## 2. Wat wil je bereiken? (functionele eisen)

Zonder voorschrift, wel helder maken:

1. **Betrouwbaarheid:** geen handmatige copy-paste; herstart VPS mag geen “gat” geven als dat te voorkomen is.
2. **Tijd:** dagelijks (of elk uur) een **bekend venster** — bijv. “na NY close” of “06:00 UTC”.
3. **Analyse:** mentor kan trends zien (latency, fouten, block-reasons, fill quality, nieuws/LLM-paden) zonder op de VPS te moeten inloggen — *tenzij* jullie bewust alles on-prem op de VPS houden.
4. **Privacy & veiligheid:** geen API-keys of wachtwoorden in JSON; keys horen in de **OS-omgeving** (zie `docs/CREDENTIALS_AND_ENVIRONMENT.md`). Eventueel account-id’s pseudonimiseren in exports.
5. **Reproduceerbaarheid:** vaste paden, vaste schema’s (event_version), zodat analyse-scripts niet elke week breken.

---

## 3. Drie hoofdarchitecturen (kort vergelijken)

### Optie A — Alles op de VPS (“data lake light”)

- **Wat:** vaste map bijv. `/opt/quantbuild/data/quantlog/` en `/opt/quantbuild/data/daily/`; `cron` of `systemd timer` draait na runtime een klein script: roteert/comprimeert, bouwt `daily_summary_YYYY-MM-DD.json`.
- **Analyse:** op de VPS Jupyter/Lab, of `duckdb` CLI over geparquetteerde kopieën, of sync alleen het summary-bestand naar buiten.
- **Plus:** simpel, geen cloud-account nodig; data verlaat de server niet.
- **Min:** mentor heeft dan óók SSH nodig, of jij exporteert alsnog handmatig — tenzij je een **read-only** S3/Blob-sync *vanaf* de VPS toevoegt.

### Optie B — “Pull” vanaf je eigen machine (VS Code / script)

- **Wat:** dagelijks (Windows Task Scheduler of `cron` op een thuis-NAS) `rsync`/`scp` vanaf VPS naar lokale map `~/quantbuild_vps_mirror/`.
- **Analyse:** lokaal Python, DuckDB, Excel, Power BI — wat jullie kennen.
- **Plus:** geen extra server; data staat waar je al werkt.
- **Min:** machine moet op het juiste moment aan staan; sleutelbeheer op de client.

### Optie C — Centrale object storage (aanbevolen op termijn voor teams)

- **Wat:** VPS-upload via `rclone`/`aws s3 sync` naar een bucket met lifecycle rules (bijv. 90 dagen raw JSONL, daarna alleen aggregates).
- **Analyse:** query in de cloud (Athena, BigQuery externe tabel), of download subset voor notebooks.
- **Plus:** mentor krijgt **gedeelde** toegang zonder SSH; audit en backup zijn inrichtbaar.
- **Min:** cloud-account, IAM, kosten (meestal laag voor kleine JSONL).

**Praktische hybride (vaak het beste MVP):** **A + dunne export** — op de VPS dagelijks één **geanonimiseerde** `daily_summary.json` + gecomprimeerde `quantlog_YYYY-MM-DD.jsonl.gz` naar **één** bestemming (lokaal pull *of* bucket). Detail-JSONL alleen waar nodig.

---

## 4. Automatisering op de VPS (concrete bouwstenen)

- **`systemd` timer** of **cron** op vaste tijd, bv. `OnCalendar=*-*-* 06:00:00 UTC` (pas aan op sessie).
- **Stap 1 — valideren:** bestaan de verwachte paden? Is de service die dag gelopen?
- **Stap 2 — packen:** `tar` of `gzip` per dag (JSONL comprimeert goed).
- **Stap 3 — summary genereren:** klein Python-script dat uit JSONL telt: `event_type`, `severity`, fouten, unieke `trace_id`, eenvoudige latency- of cycle-statistieken *als* die in `payload` zitten.
- **Stap 4 — verzenden:** `rclone copy` naar bucket, of `scp` naar vaste host, of alleen e-mail bij alarm (zie §6).

Geen nieuwe dependencies nodig voor een MVP: `python3`, `gzip`, `systemd`, eventueel `rclone`.

---

## 5. Opslag en ordening (naamgeving)

Aanbevolen layout (concept):

```text
/opt/quantbuild/data/
  quantlog/raw/YYYY-MM-DD/quantbuild.jsonl
  export/daily/YYYY-MM-DD/
    manifest.json          # hashes, byte counts, git commit van deploy
    daily_summary.json     # klein, mentor-vriendelijk
    quantbuild.jsonl.gz    # optioneel, detail
```

**Manifest** helpt bij: “welke build draaide er?” en integriteit (checksum).

---

## 6. Analyse-ideeën (wat de mentor kan laten beoordelen)

| Laag | Tooling | Voor wie | Opmerking |
|------|---------|----------|-----------|
| **Snelle KPI’s** | Excel / Google Sheets op `daily_summary.json` | mentor, PM | laagdrempelig |
| **SQL over logs** | [DuckDB](https://duckdb.org/) direct op `.jsonl` of geparquet | developer | weinig infra |
| **Notebook** | Jupyter op VPS of lokaal op gespiegelde data | research | goed voor plots |
| **Dashboard** | Grafana + Loki *of* metrics uit summary naar Prometheus | operations | meer werk, sterk voor alerts |
| **Data warehouse** | BigQuery / Athena op bucket | team schaalt op | pas bij groei |

**Inhoudelijke vragen voor analyse (voorbeelden):** trend in `ERROR` vs `INFO`, pieken in “block reasons”, nieuws/LLM budgetten, cyclustijd per uur, correlatie met spread/sessie (als die in payload zit).

---

## 7. Alerts vs rapportage

- **Dagelijks rapport:** altijd het summary-bestand (geen paging).
- **Alleen bij probleem:** script dat `grep`/JSON-parse doet op drempels (bijv. > N errors, geen events > X uur) en dan e-mail/Slack/webhook — *zonder* secrets in de webhook-URL in repo; gebruik env vars.

---

## 8. Security-checklist (kort)

- Geen secrets in export; scrub `payload` indien nodig.
- Bucket of SSH: **least privilege** (alleen append/upload map).
- Versleuteling at rest (cloud standaard) en TLS bij upload.
- Retentie afspreken (AVG/broker policies als van toepassing).

---

## 9. Voorgestelde fasering

| Fase | Doel | Oplevering |
|------|------|------------|
| **0** | Inzicht | Vaste exportmap + documenteer exacte paden op VPS |
| **1** | Automatisering | `systemd` timer + `daily_summary.json` + gzip van JSONL |
| **2** | Delen | `rclone`/sync naar gedeelde locatie óf geplande pull naar laptop |
| **3** | Analyse** | DuckDB-queries + 1 notebook-template voor mentor |
| **4** | Schaal** | warehouse/dashboard + alerts op drempels |

\*Fase 3–4 alleen als de datavolumes of het team dat rechtvaardigen.

---

## 10. Open vragen aan de mentor

1. Moeten ruwe logs de VPS verlaten, of alleen geaggregeerde/schoongemaakte JSON?
2. Welke KPI’s zijn “must-have” op dagbasis voor go/no-go op strategie?
3. Is er een voorkeur voor cloud (S3-compatible) vs. alles binnen eigen infrastructuur?
4. Hoe lang moeten ruwe JSONL bewaard blijven (compliance / debug)?
5. Wie krijgt toegang tot exports (alleen developer + mentor, breder team)?

---

## 11. Referenties in deze repo

- VPS-deploy en paden: `docs/VPS_DEPLOYMENT_RUNBOOK.md`
- SSH / VS Code: `docs/VPS_SSH_VSCODE_SETUP.md`
- Optionele multi-module (QuantLog): `docs/VPS_MULTI_MODULE_DEPLOYMENT.md` (indien aanwezig)

---

*Document versie: concept voor discussie met mentor — geen implementatieverplichting; keuzes hangen af van teamgrootte, budget en privacy.*
